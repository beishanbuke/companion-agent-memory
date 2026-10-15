# Phase 0：机器人触发接口探测指南

> **重要提示**：本指南需要在机器人 Orin 上执行，且机器人主控系统必须已启动。

## 📋 探测目标

找到 Sim2Real 系统中用于触发动作切换的真实 ROS 接口，填入以下占位符：
- `robot_action_client.py` 中的 `DirectSwitchClient.trigger_action` 方法
- `bridge_config.json` 中的 `robot_node_keyword` 字段

## 🔧 探测前准备

### 1. 确保机器人主控已启动

```bash
cd /home/nvidia/sim2real
source ./install/setup.bash
roslaunch sim2real_master joy_control_pi_plus_orin.launch
```

**保持此终端运行**，不要关闭。

### 2. 打开新终端用于探测

```bash
# SSH 到机器人 Orin
ssh nvidia@<机器人IP>

# Source ROS 环境
cd /home/nvidia/sim2real
source ./install/setup.bash
```

## 🕵️ Phase 0 探测步骤

### 步骤 1：确认动作触发配置

```bash
cat /home/nvidia/sim2real/install/share/sim2real/action_config/config/pi_plus_26dof/custom_action.yaml
```

**预期输出**：
```yaml
# 示例内容（实际内容可能不同）
actions:
  hello:
    buttons: [7, 0]  # rt+x: 右扳机(7) + X键(0)
    mode: "custom"
  cheer:
    buttons: [7, 1]  # rt+a: 右扳机(7) + A键(1)
    mode: "custom"
```

**记录信息**：
- `hello` 对应的按键组合：`rt+x` (buttons: [7, 0])
- `cheer` 对应的按键组合：`rt+a` (buttons: [7, 1])

---

### 步骤 2：抓包 Joy 消息（为实现 B 准备）

```bash
# 监听 joy topic
rostopic echo /joy
```

**操作**：用手柄按 `rt+x` 触发一次 hello 动作。

**记录信息**：
- 按钮按下时的消息格式
- 按钮序列的时间间隔
- axes 和 buttons 数组的长度

**示例输出**：
```
buttons: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # 11个按钮
axes: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # 8个轴
---
# 按下 rt+x 时
buttons: [1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0]  # X键(0)=1, rt键(7)=1
...
```

**按 Ctrl+C 退出监听**

---

### 步骤 3：查找真实触发接口（实现 A 的目标）

#### 3.1 列出所有 ROS 节点

```bash
rosnode list
```

**预期输出示例**：
```
/robot_controller
/joy_node
/motion_policy_node
/state_machine
/rosout
```

**记录主控节点名**（通常包含 `robot`、`control`、`policy` 等关键字）：
- 主控节点：`_____________` （填入 bridge_config.json 的 robot_node_keyword）

#### 3.2 查看 ROS 计算图

```bash
rqt_graph &
```

在打开的图形界面中：
1. 找到 `/joy` 节点
2. 追踪它的连接：`/joy` → `哪个节点` → `哪个 topic/service`
3. 截图保存，便于分析

#### 3.3 搜索源代码中的触发逻辑

```bash
# 搜索动作切换相关代码
cd /home/nvidia/sim2real

grep -r "custom_action\|hello\|policy\|trigger" \
  src/ install/ \
  --include=*.cpp --include=*.h --include=*.py \
  | grep -v "Binary" | head -50
```

**重点关注**：
- 包含 `custom_action.yaml` 配置读取的代码
- 包含 Joy 消息处理的代码
- 包含 policy 切换逻辑的代码

#### 3.4 检查可用 topics

```bash
rostopic list
```

**查找可能的触发接口**：
```
/action_trigger
/switch_action
/motion_command
/policy_switch
/custom_action
```

#### 3.5 检查可用 services

```bash
rosservice list
```

**查找可能的触发服务**：
```
/robot/trigger_action
/switch_motion
/execute_action
```

#### 3.6 检查 topic 详情（如果找到候选接口）

```bash
# 假设找到 /action_trigger topic
rostopic info /action_trigger

# 查看消息类型
rostopic echo /action_trigger -n 1
```

#### 3.7 检查 service 详情（如果找到候选接口）

```bash
# 假设找到 /trigger_action service
rosservice info /trigger_action

# 查看服务类型定义
rossrv show <ServiceType>
```

---

### 步骤 4：测试触发接口

#### 方法 A：通过 Topic 触发

```bash
# 假设接口是 /action_trigger，消息类型是 std_msgs/String
rostopic pub /action_trigger std_msgs/String "data: 'hello'" --once
```

**观察机器人**：是否执行 hello 动作

#### 方法 B：通过 Service 触发

```bash
# 假设接口是 /trigger_action service
rosservice call /trigger_action "action_name: 'hello'"
```

**观察机器人**：是否执行 hello 动作

---

### 步骤 5：记录探测结果

**找到真实接口后，填写以下信息**：

#### 📝 填写 `robot_action_client.py`

**位置**：`emotion_robot_bridge/robot_action_client.py` 第 95-105 行

```python
def trigger_action(self, action_name: str) -> bool:
    """触发指定动作"""

    # === Phase 0 探测结果填写区域 ===

    # 方式1: 通过 ROS Topic（请填写真实接口）
    ROS_TOPIC_NAME = "【填写真实的 topic 名称】"  # 如 /action_trigger
    ROS_MSG_TYPE = "【填写消息类型】"            # 如 std_msgs/String

    # 方式2: 通过 ROS Service（请填写真实接口）
    ROS_SERVICE_NAME = "【填写真实的 service 名称】"  # 如 /trigger_action
    ROS_SRV_TYPE = "【填写服务类型】"                   # 如 sim2real_msgs/Trigger

    # 选择使用哪种方式：True=Service, False=Topic
    USE_SERVICE = False  # 根据实际情况修改
```

#### 📝 填写 `bridge_config.json`

**位置**：`emotion_robot_bridge/bridge_config.json` 第 17 行

```json
{
  "robot": {
    "robot_node_keyword": "【填写主控节点名关键字】"
  }
}
```

---

## 🔍 如果找不到真实接口

如果经过步骤 3-4 仍未找到合适的触发接口，使用实现 B（模拟手柄按键）：

### 填写 Joy 按键序列

**位置**：`emotion_robot_bridge/bridge_config.json`

```json
{
  "robot": {
    "trigger_impl": "B",  // 改为 "B"
    "joy_button_sequence": [
      {"buttons": [7, 0], "hold_time": 0.1}  // rt+x: 右扳机(7) + X键(0)
    ]
  }
}
```

### 修改 `robot_action_client.py`

确保 `JoyEmulatorClient` 类中的按键映射正确：

```python
action_button_map = {
    "hello": [{"buttons": [7, 0], "hold_time": 0.1}],  # rt+x
    "cheer": [{"buttons": [7, 1], "hold_time": 0.1}],  # rt+a
}
```

---

## ✅ 探测完成检查清单

- [ ] 确认动作触发配置（hello = rt+x）
- [ ] 抓包 Joy 消息成功
- [ ] 列出所有 ROS 节点
- [ ] 查看 ROS 计算图
- [ ] 搜索源代码找到触发逻辑
- [ ] 检查 topics 和 services
- [ ] 测试触发接口成功
- [ ] 填写 `robot_action_client.py` 探测结果
- [ ] 填写 `bridge_config.json` robot_node_keyword
- [ ] 保存探测截图和日志

---

## 🚨 注意事项

1. **只读操作**：本指南所有命令均为只读或探测性质，不会修改机器人系统
2. **备份重要**：探测前确保已按 README.md 要求备份配置文件
3. **安全第一**：保持手柄急停可用，机器人周围无人
4. **记录详细**：详细记录每一步的输出和发现

---

## 📞 探测支持

如果探测过程中遇到问题：
1. 检查 ROS Master 是否正常运行：`rosnode list`
2. 检查主控是否已启动：查看启动终端输出
3. 检查网络连接：确保能连接到机器人 Orin

---

**探测完成后，请更新相应配置文件并测试。**
