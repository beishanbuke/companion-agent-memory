# Phase 0 探测结果报告

## 📋 代码分析结果（已完成）

从 sim2real 源代码分析得出以下信息：

### ✅ 已确认的信息

| 项目 | 值 | 来源 |
|------|-----|------|
| 主控节点名 | `masternode` | main.cpp 第77行 `ros::init(argc, argv, "masternode")` |
| Joy消息类型 | `sim2real_msg::Joy` | master_node.h 第52行 |
| 消息订阅接口 | `joyCommandTopic_` | master_node.h 第107行 |
| 处理函数 | `joyMsgCallback` | master_node.h 第54行 |
| 动作配置文件 | `pi_plus_26dof/custom_action.yaml` | custom_action.yaml |

### 🔍 按键映射配置

从 `custom_action.yaml` 确认的按键映射：

| 动作名称 | 按键组合 | 说明 |
|----------|----------|------|
| `hello` | `rt+x` | 单手打招呼 |
| `cheer` | `rt+a` | 双手欢呼 |
| `small_kick` | `x` | 小脚踢球 |

### 📝 已更新的配置

已将 `bridge_config.json` 中的 `robot_node_keyword` 填写为 `masternode`：

```json
{
  "robot": {
    "robot_node_keyword": "masternode"
  }
}
```

## ⏳ 待完成步骤（需启动机器人主控）

以下步骤需要在启动机器人主控系统后完成：

### 1. 确认 ROS 系统可用

```bash
cd /home/nvidia/sim2real
source ./install/setup.bash
roslaunch sim2real_master joy_control_pi_plus_orin.launch
```

### 2. 确认 Joy Topic 名称

```bash
rostopic list | grep -i joy
```

**预期结果**: `/joy` 或类似名称

### 3. 确认 Joy 消息格式

```bash
rostopic info /joy
rostopic echo /joy -n 1
```

### 4. 测试动作触发（实现 B 准备）

**手动触发一次 hello 动作并抓包**：
```bash
rostopic echo /joy > joy_capture.txt
```
然后按 `rt+x`，停止抓包 (Ctrl+C)，分析消息格式。

### 5. 查找可能的直接触发接口（实现 A 目标）

```bash
# 检查所有 topics
rostopic list

# 检查所有 services
rosservice list

# 检查节点信息
rosnode info masternode
```

## 🎯 推荐实现方案

基于代码分析，推荐使用**实现 B（模拟手柄按键）**：

### 理由
1. 代码中确认了使用 `sim2real_msg::Joy` 消息类型
2. 按键映射已明确（rt+x = hello）
3. 不需要深入查找内部触发接口

### 实现步骤

#### 1. 更新 `bridge_config.json`

```json
{
  "robot": {
    "trigger_impl": "B",
    "joy_topic": "/joy",
    "joy_button_sequence": [
      {
        "name": "hello",
        "buttons": [7, 0],
        "hold_time": 0.1,
        "description": "rt+x: 右扳机(7) + X键(0)"
      },
      {
        "name": "cheer",
        "buttons": [7, 1],
        "hold_time": 0.1,
        "description": "rt+a: 右扳机(7) + A键(1)"
      }
    ]
  }
}
```

#### 2. 更新 `robot_action_client.py`

确保 `JoyEmulatorClient` 类正确实现按钮序列发送。

## ✅ 完成状态

- [x] 代码分析完成
- [x] 主控节点名确认
- [x] 按键映射确认
- [x] 消息类型确认
- [x] 配置文件更新
- [ ] ROS 系统测试（需启动机器人）
- [ ] Joy 消息抓包（需启动机器人）
- [ ] 动作触发测试（需启动机器人）

## 📞 下一步操作

1. **启动机器人主控系统**（如果尚未启动）
2. **执行上述待完成步骤**
3. **根据抓包结果更新配置**
4. **测试完整链路**

---

**探测日期**: 2026-08-16
**探测环境**: sim2real 代码分析（机器人主控未启动）
