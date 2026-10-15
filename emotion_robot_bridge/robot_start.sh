#!/usr/bin/env bash
#
# 一键启动机器人：加载 ROS 环境 → 启动主控(roslaunch) → 打开电机供电
#
# 用法：
#   ./robot_start.sh          # 启动主控 + 开电机
#   ./robot_start.sh stop     # 急停（电机失力，需人扶）
#   ./robot_start.sh off      # 关闭电机电源（不杀主控）
#
# 注意顺序：必须先 roslaunch（起 roscore 和 power_node），
# 然后才能 rostopic pub 开电源。

set -e

ROS_SETUP="/home/nvidia/sim2real/install/setup.bash"
LAUNCH_LOG="/tmp/sim2real_launch.log"
MODE="${1:-start}"

# ---------- 加载 ROS 环境 ----------
source "$ROS_SETUP"

# ---------- 急停 ----------
if [ "$MODE" = "stop" ]; then
    echo "=== 急停（保护关机，电机失力，请扶住机器人）==="
    rostopic pub -1 /joy_msg sim2real_msg/Joy \
      '{l_horizontal: 0.0, l_vertical: 0.0, lt: -1.0, r_horizontal: 0.0, r_vertical: 0.0, rt: -1.0, dpad_horizontal: 0.0, dpad_vertical: 0.0, a: 0.0, b: 1.0, x: 0.0, y: 0.0, lb: 0.0, rb: 0.0, back: 0.0, start: 0.0, center: 0.0, L: 0.0, R: 0.0}'
    exit 0
fi

# ---------- 关电机电源 ----------
if [ "$MODE" = "off" ]; then
    echo "=== 关闭电机电源 ==="
    rostopic pub -1 /power_switch_control livelybot_power/Power_switch "{control_switch: 0, power_switch: 0}"
    exit 0
fi

# ---------- 启动主控 ----------
echo "=== 1. 加载 ROS 环境 ==="
echo "    已 source: $ROS_SETUP"

echo "=== 2. 启动机器人主控（roslaunch，后台运行）==="
if rosnode list >/dev/null 2>&1; then
    echo "    ROS master 已在运行，跳过 roslaunch"
else
    nohup roslaunch sim2real_master joy_control_pi_plus_orin.launch > "$LAUNCH_LOG" 2>&1 &
    echo "    roslaunch 已后台启动，日志: $LAUNCH_LOG"
fi

echo "=== 3. 等待 power_node 就绪 ==="
READY=0
for i in $(seq 1 60); do
    if rosnode list 2>/dev/null | grep -q "/power_node"; then
        echo "    power_node 已就绪（约 ${i}s）"
        READY=1
        break
    fi
    sleep 1
done

if [ "$READY" -ne 1 ]; then
    echo "    ⚠️ 等待超时，power_node 未出现。请查看日志: tail -f $LAUNCH_LOG"
    exit 1
fi

echo "=== 4. 打开电机供电 ==="
rostopic pub -1 /power_switch_control livelybot_power/Power_switch "{control_switch: 1, power_switch: 1}"
sleep 1
rostopic pub -1 /com_power_control std_msgs/UInt8 "data: 1"

echo "=== 5. 验证 ==="
sleep 3
echo "--- power_switch_state ---"
timeout 3 rostopic echo -n 1 /power_switch_state 2>/dev/null || echo "(未获取到)"
echo "--- fsm_state ---"
timeout 3 rostopic echo -n 1 /fsm_state 2>/dev/null | grep -oE "data: -?[0-9]+" || echo "(未获取到)"

echo ""
echo "✅ 机器人启动完成"
echo "   主控日志: tail -f $LAUNCH_LOG"
echo "   开桥接:   cd /home/nvidia/Desktop/companion-agent-memory/emotion_robot_bridge && ./start_bridge.sh"
