# Phase 0 最终调查结果（机器人动作触发机制）

> 调查日期：2026-08-16，机器人已通电、电机已连接

---

## 一、已确认的事实

| 项目 | 结果 |
|------|------|
| 机器人硬件 | ✅ 26个电机全部连接（v4.7.3/v4.9.3）|
| 电机供电 | ✅ 48W 正常 |
| FSM 状态 | ExecDefault (5) 行走模式 |
| 动作配置 | cheer=rt+a, hello=rt+x, small_kick=x |
| Joy 消息 | ✅ 正确流向 /joy_msg |
| 情绪检测 | ✅ happy→开心 正确 |

## 二、关键发现

### 1. 动作触发机制（从源码分析）

机器人有**两级**控制系统：

```
FSM 状态机（模式选择）
  ├── ExecDefault（行走模式）- 默认
  ├── ExecCustom（自定义动作模式）- cheer/hello 在此执行
  └── 菜单导航（NextOption/Confirm 按键切换模式）
```

### 2. 直接发布 rt+a 不触发动作

- 发布 `rt=1.0, a=1.0` 到 /joy_msg ✅ 消息正确到达
- 机器人日志出现 `cheer:amp`（识别到 cheer 动作）
- 但手臂位置不变（动作**未执行**）
- 原因：机器人需先进入 **ExecCustom** 模式

### 3. FSM 菜单导航

```
Init → NextOption → CandidateDefault
CandidateDefault → NextOption → CandidateCustom
CandidateCustom → Confirm → ExecCustom ← 在此执行 cheer
```

但机器人当前在 ExecDefault，**无法**通过已知 joy 事件切换到 Candidate 状态。

## 三、剩余问题

**需要确定：从 ExecDefault 切换到 ExecCustom 的正确按键序列**

可能的菜单导航按键（待验证）：
- NextOption = dpad 右键（dpad_horizontal = -1）
- LastOption = dpad 左键（dpad_horizontal = 1）
- Confirm = A 键（a = 1.0）

## 四、推荐下一步（二选一）

### 方案 A：物理手柄抓包（最可靠）

```bash
# 1. 连接物理手柄
# 2. 监听 /joy_msg
rostopic echo /joy_msg > joy_capture.txt

# 3. 用手柄触发 cheer（按 rt+a）
# 4. 按 Ctrl+C 停止监听
# 5. 分析抓包结果，找到确切的按键序列
```

### 方案 B：联系机器人厂商

向 Mini Pi Plus Pro 厂商（乐聚）索取：
- FSM 模式切换的按键映射
- 或直接的动作触发 ROS 接口

## 五、桥接程序状态

桥接程序**完全就绪**，只差填入正确的 joy 触发序列：

```python
# robot_action_client.py 的 JoyEmulatorClient.trigger_action
# 目前：直接发布 rt=1.0, a=1.0（不触发）
# 需要：先切换到 ExecCustom 模式，再发布 rt+a
```

一旦确定菜单导航序列，只需更新 `action_button_map` 即可。
