# 情感标签驱动机器人动作：LLM–Robot 连接程序

> 将对话系统产出的情绪标签转换为机器人动作的桥接程序

---

## 一、程序概述

本程序实现了从对话情绪到机器人动作的完整链路：

```
用户说话（文字/语音）
    ↓
companion-agent-memory 对话服务
    ↓ 每轮自动写入
current_emotion.json
    ↓ 轮询读取 + 去重 + 全量投递
emotion_watcher.py（监听器）
    ↓ HTTP POST（127.0.0.1:8790）
robot_gateway.py（网关+状态机）
    ↓ 白名单/执行状态机：不抢占·最新情绪优先
robot_action_client.py（动作触发）
    ↓ ROS topic/service
Sim2Real 机器人系统
    ↓
机器人执行动作
```

**核心特性**：
- ✅ 零侵入：不修改对话系统和机器人系统的任何现有文件
- ✅ 安全可控：白名单机制、动作不可抢占、同动作抑制
- ✅ 易于回退：停掉两个进程即可恢复原状
- ✅ 完全可配置：通过 `bridge_config.json` 调整所有参数

---

## 二、系统要求

- Python 3.10+
- 机器人系统：Mini Pi Plus Pro（Orin），运行 Sim2Real
- 对话服务：companion-agent-memory

---

## 三、部署前准备

### 3.1 阅读顺序建议

1. 先阅读本文的第1、2、4节，建立全局认识
2. 按照3.2节对两侧系统进行备份
3. 执行3.3节的 Phase 0 探测，获取ROS接口信息
4. 根据3.4节调整配置文件
5. 启动程序并按第4节进行测试验收

### 3.2 系统备份（必须执行）

**对话侧备份**：

```bash
# 如果在 git 仓库中
cd /home/nvidia/Desktop/companion-agent-memory
git status  # 确认工作区干净
git tag backup-before-emotion-bridge-$(date +%Y%m%d)

# 如果不在 git 仓库中
tar czf companion_backup_$(date +%Y%m%d_%H%M%S).tar.gz .
```

**机器人侧备份**：

```bash
# 备份动作配置文件
cd /home/nvidia/sim2real
cp install/share/sim2real/action_config/config/pi_plus_26dof/custom_action.yaml \
   install/share/sim2real/action_config/config/pi_plus_26dof/custom_action.yaml.bak_$(date +%Y%m%d_%H%M%S)

cp install/share/sim2real/config/pi_plus_26dof_config/pi_plus_26dof_rl_config_custom.yaml \
   install/share/sim2real/config/pi_plus_26dof_config/pi_plus_26dof_rl_config_custom.yaml.bak_$(date +%Y%m%d_%H%M%S)
```

### 3.3 Phase 0：机器人触发接口探测

**在真机上执行以下步骤（只读操作，不修改任何文件）**：

1. **启动机器人主控**（如果未启动）：
   ```bash
   cd /home/nvidia/sim2real && source ./install/setup.bash
   roslaunch sim2real_master joy_control_pi_plus_orin.launch
   ```

2. **确认动作触发配置**：
   ```bash
   cat /home/nvidia/sim2real/install/share/sim2real/action_config/config/pi_plus_26dof/custom_action.yaml
   ```
   确认 `hello` 对应的按键组合（已知：`rt+x`）

3. **抓包 Joy 消息**：
   ```bash
   rostopic echo /joy
   ```
   按 `rt+x` 触发一次 hello 动作，记录按钮序列与时间间隔

4. **查找真实触发接口**：
   ```bash
   rosnode list
   rqt_graph
   grep -R "custom_action\|hello\|policy" \
     /home/nvidia/sim2real/src --include=*.cpp --include=*.h --include=*.py | head -50
   ```

5. **记录主控节点名** → 填入配置文件的 `robot.robot_node_keyword`

6. **找到接口后**，修改 `robot_action_client.py` 中的 `DirectSwitchClient.trigger_action` 方法，填入真实的 topic/service 信息

**⚠️ 待 Phase 0 回填的占位点**：
- `robot_action_client.py` 第 95-105 行：`DirectSwitchClient.trigger_action` 方法
- `bridge_config.json` 第 17 行：`robot_node_keyword` 字段

### 3.4 配置文件调整

编辑 `bridge_config.json`：

```json
{
  "watcher": {
    "emotion_file": "/home/nvidia/Desktop/companion-agent-memory/prototype_demo/.run/current_emotion.json",
    "poll_interval": 0.5,
    "gateway_url": "http://127.0.0.1:8790",
    "request_timeout": 3.0,
    "dry_run": false
  },
  "gateway": {
    "listen_host": "127.0.0.1",
    "listen_port": 8790,
    "auth_token": "",
    "settle_gap": 2.0,
    "dry_run": false
  },
  "robot": {
    "trigger_impl": "A",
    "action_duration": 5.44,
    "robot_check_cmd": "rosnode list",
    "robot_node_keyword": "【待Phase 0填入】",
    "joy_topic": "/joy",
    "joy_button_sequence": []
  },
  "actions": {
    "hello": { "duration": 5.44 },
    "cheer": { "duration": 3.0 },
    "whitelist": ["hello", "cheer"]
  },
  "emotion_map": {
    "开心": "cheer",
    "难过": "hello"
  },
  "log_dir": "logs"
}
```

**配置说明**：
- `emotion_file`：情绪文件的绝对路径（机器人上可见的路径）
- `emotion_map`：情绪标签到动作的映射
- `actions.whitelist`：允许执行的动作白名单
- `dry_run`：设为 `true` 进入测试模式（不真正触发机器人）

---

## 四、启动与测试

### 4.1 启动步骤

1. **确认机器人主控已启动**（3.3节第1步）

2. **启动网关服务**：
   ```bash
   cd /path/to/emotion_robot_bridge
   # 先用 dry-run 模式测试
   python3 robot_gateway.py --dry-run
   ```

3. **启动监听器**（新终端）：
   ```bash
   cd /path/to/emotion_robot_bridge
   python3 emotion_watcher.py --dry-run
   ```

### 4.2 T1 离线单测

测试情绪解析和映射逻辑：

```bash
# 测试各种情绪标签
python3 simulate_emotion.py --label None --print
python3 simulate_emotion.py --label 开心 --print
python3 simulate_emotion.py --label 难过 --print
```

**通过标准**：生成的 JSON 符合 schema，标签正确

### 4.3 T2 Watcher Dry-run 测试

```bash
# 在 watcher 终端，观察日志
# 使用模拟工具写入情绪
python3 simulate_emotion.py --label 开心
python3 simulate_emotion.py --label 难过
python3 simulate_emotion.py --label None
```

**通过标准**：
- 日志显示每次写入产生一次投递（包括 None）
- 重复写入相同内容不重复投递
- 日志显示 `[DRY-RUN] Would send:`

### 4.4 T3 Gateway Dry-run 测试

```bash
# 测试健康检查
curl http://127.0.0.1:8790/health

# 测试情绪触发
curl -X POST http://127.0.0.1:8790/emotion \
  -H "Content-Type: application/json" \
  -d '{"label":"开心","intensity":0.7,"confidence":0.85,"updated_at":"2026-08-16T15:30:12+0800"}'

# 测试busy状态（快速发送两次）
curl -X POST http://127.0.0.1:8790/emotion \
  -H "Content-Type: application/json" \
  -d '{"label":"开心","intensity":0.7,"confidence":0.85,"updated_at":"2026-08-16T15:30:12+0800"}'
```

**通过标准**：
- `/health` 返回 200 和状态信息
- 情绪请求返回 200 和 `status: triggered/queued_latest/skipped_same_action/reset`
- 白名单外动作返回 400

### 4.5 T4 真机 Dry-run 测试

在机器人上以 dry-run 模式运行全链路：

```bash
# 停止之前的进程，重新启动
python3 robot_gateway.py --dry-run
python3 emotion_watcher.py --dry-run
```

**通过标准**：
- 日志显示 `DRY-RUN: 将触发 hello`
- `/health` 返回 `mode: dry-run`

### 4.6 T5 真机 Real 模式测试

1. **去掉 dry-run**：
   ```bash
   python3 robot_gateway.py
   python3 emotion_watcher.py
   ```

2. **触发一次开心**：
   ```bash
   python3 simulate_emotion.py --label 开心
   ```

**通过标准**：机器人完整执行一次挥手动作（约 5.44 秒），回到默认模式

### 4.7 T6 全链路测试

使用真实对话服务：

```bash
# 启动对话服务（如果未启动）
cd /home/nvidia/Desktop/companion-agent-memory
python3 prototype_demo/server.py
```

**测试场景**：

1. **三标签行为**：
   - "我太开心了！" → 机器人挥手
   - "今天好难过" → 机器人挥手
   - "今天天气不错" → 机器人不动作

2. **不抢占**：挥手期间再说"开心"，动作不中断

3. **同动作抑制**：连续说多次"开心"，只执行一次挥手

4. **平静期重置**：说几句中性话后再说"开心"，再次挥手

---

## 五、验收清单

- [ ] None 不动作、开心挥手、难过挥手
- [ ] 内容指纹去重：文件未变不重复触发
- [ ] 不抢占：动作执行中的更新不中断当前动作
- [ ] 最新情绪优先：busy 期间多次更新只保留最后一条
- [ ] 同动作抑制：连续同情绪只执行一次
- [ ] 经历 None 后同情绪可再次执行
- [ ] 白名单：未授权动作返回 400
- [ ] 对话服务崩溃/文件被删：watcher 不退出
- [ ] gateway 掉线：watcher 记错误继续运行
- [ ] 所有参数可经配置文件调整

---

## 六、回退步骤

**完全回退**（恢复正常运行）：

1. **停止两个进程**：
   ```bash
   # 在各自终端按 Ctrl+C，或
   pkill -f emotion_watcher.py
   pkill -f robot_gateway.py
   ```

2. **验证对话服务**：
   - 启动对话服务，确认 `current_emotion.json` 正常更新

3. **验证手柄控制**：
   - 用手柄触发 `hello` 动作，确认机器人正常响应

**正常情况下回退不需要恢复任何文件**，因为连接程序是零侵入的纯新增进程。

---

## 七、安全要求

1. **真机测试环境**：开阔防滑地面、周边无人和障碍物、有人值守、手柄急停可用
2. **首次测试不要站在机器人正前方**
3. **不要以 root 运行**本程序
4. **默认只绑定 127.0.0.1**，远程调试时必须配置 `auth_token`
5. **禁止在代码中高危命令**如 `kill -9` 清理进程
6. **白名单之外的动作一律拒绝**

---

## 八、扩展指南

### 8.1 新增动作

1. 在机器人侧添加新动作（修改 Sim2Real 配置）
2. 在 `bridge_config.json` 中：
   - 添加到 `actions.whitelist`
   - 添加动作时长信息 `actions.<动作名>.duration`
   - 在 `emotion_map` 中添加情绪映射

### 8.2 新增情绪标签

1. 在对话侧修改情绪识别逻辑
2. 在 `bridge_config.json` 的 `emotion_map` 中添加映射

---

## 九、日志与调试

日志文件位置：`logs/watcher_YYYYMMDD.log` 和 `logs/gateway_YYYYMMDD.log`

**重要日志关键字**：
- `UPDATE triggered`：已开始执行动作
- `UPDATE queued_latest`：执行中，已记入待执行槽
- `UPDATE skipped_same_action`：同动作且无平静期，跳过
- `UPDATE reset`：情绪平复，清空待执行槽

---

## 十、常见问题

**Q: watcher 提示文件不存在？**
A: 确认 `emotion_file` 路径正确，对话服务已启动

**Q: 机器人没有动作？**
A: 检查是否在 dry-run 模式；检查 ROS master 是否在线；检查白名单

**Q: 动作执行不完？**
A: 检查 `settle_gap` 和动作时长配置是否合理

**Q: 跨机器部署？**
A: 将对话服务的 `.run` 目录通过 NFS/SSHFS 挂载到机器人，或修改 `emotion_file` 为挂载路径

---

## 十一、文件清单

```
emotion_robot_bridge/
├── README.md              # 本文档
├── bridge_config.json     # 配置文件
├── emotion_watcher.py     # 情绪文件监听器
├── robot_gateway.py       # 机器人网关服务
├── robot_action_client.py # 动作触发客户端
├── simulate_emotion.py    # 测试工具
└── logs/                  # 日志目录
    ├── watcher_YYYYMMDD.log
    └── gateway_YYYYMMDD.log
```

---

## 十二、技术架构

**部署拓扑**：
```
┌─────────────────────┐
│ 对话服务器           │
│ server.py (8787)    │
│ 每轮写入             │
│ current_emotion.json│
└─────────────────────┘
         ↓ 挂载/本机
┌────────────────────────────────┐
│ 机器人 Orin                    │
│                                │
│  emotion_watcher.py            │
│      ↓ HTTP POST               │
│  robot_gateway.py              │
│      ↓ 状态机决策               │
│  robot_action_client.py        │
│      ↓ ROS topic/service       │
│  Sim2Real（预启动）            │
└────────────────────────────────┘
```

---

## 十三、维护说明

**重启服务**：
```bash
# 停止
pkill -f emotion_watcher.py
pkill -f robot_gateway.py

# 启动
cd /path/to/emotion_robot_bridge
nohup python3 robot_gateway.py > gateway.out 2>&1 &
nohup python3 emotion_watcher.py > watcher.out 2>&1 &
```

**查看日志**：
```bash
tail -f logs/gateway_$(date +%Y%m%d).log
tail -f logs/watcher_$(date +%Y%m%d).log
```

**健康检查**：
```bash
curl http://127.0.0.1:8790/health
```

---

## 十四、联系方式

如有问题，请查看日志文件或联系开发团队。

**文档版本**：1.0
**最后更新**：2026-08-16
