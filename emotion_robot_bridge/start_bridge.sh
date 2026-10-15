#!/bin/bash
echo "=== 启动情绪-机器人桥接服务 ==="

cd /home/nvidia/Desktop/companion-agent-memory/emotion_robot_bridge

# 加载 ROS 环境（供 robot_action_client 的 rospy 快速发布路径使用）
source /home/nvidia/sim2real/install/setup.bash 2>/dev/null

# 停止旧服务
pkill -f robot_gateway 2>/dev/null
pkill -f emotion_watcher 2>/dev/null
sleep 2

# 启动新服务
echo "启动网关服务..."
python3 robot_gateway.py > gateway.log 2>&1 &
echo "网关 PID: $!"

sleep 2

echo "启动监听服务..."
python3 emotion_watcher.py > watcher.log 2>&1 &
echo "监听器 PID: $!"

sleep 2

echo ""
echo "✅ 桥接服务已启动"
echo "健康检查: curl http://127.0.0.1:8790/health"
