#!/usr/bin/env python3
"""
机器人网关服务

负责：
1. 接收来自emotion_watcher的情绪更新（HTTP POST /emotion）
2. 执行状态机决策：不抢占 + 最新情绪优先
3. 调用RobotActionClient触发机器人动作
4. 提供健康检查接口（GET /health）
"""

import json
import time
import threading
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from logging import (
    getLogger, Logger, Formatter, StreamHandler,
    INFO, WARNING, ERROR, DEBUG
)
from logging.handlers import TimedRotatingFileHandler

# 导入机器人客户端
from robot_action_client import create_robot_client, RobotActionClient


# 状态常量
STATE_IDLE = "idle"
STATE_BUSY = "busy"


class GatewayConfig:
    """网关配置"""

    def __init__(self, config_dict: Dict[str, Any]):
        gateway_cfg = config_dict.get("gateway", {})
        robot_cfg = config_dict.get("robot", {})
        actions_cfg = config_dict.get("actions", {})
        emotion_map = config_dict.get("emotion_map", {})

        self.listen_host = gateway_cfg.get("listen_host", "127.0.0.1")
        self.listen_port = gateway_cfg.get("listen_port", 8790)
        self.auth_token = gateway_cfg.get("auth_token", "")
        self.settle_gap = gateway_cfg.get("settle_gap", 2.0)
        self.dry_run = gateway_cfg.get("dry_run", False)

        # 动作执行与归位
        self.action_run_duration = robot_cfg.get("action_run_duration", 20.0)
        self.recover_to_stand = robot_cfg.get("recover_to_stand", True)
        self.recover_duration = robot_cfg.get("recover_duration", 3.5)

        self.robot_config = robot_cfg
        self.actions_config = actions_cfg
        self.emotion_map = emotion_map


class ActionStateMachine:
    """
    动作执行状态机

    核心规则（需求方指定）：
    1. 动作绝不被打断（硬性）
    2. 执行中收到更新：写入pending槽，后来的覆盖先来的（latest-wins）
    3. 动作结束后消费pending：
       - 槽为空 → 回到idle
       - 槽内标签无映射 → 不动作，置emotion_reset=true
       - 槽内标签映射的动作 == last_executed_action 且 emotion_reset==false → 跳过
       - 否则 → 执行该动作
    4. None的作用：情绪回到平静，清空pending并置位emotion_reset
    5. idle时收到更新：直接按消费规则即时决策
    6. 比较基准是动作而非标签
    """

    def __init__(self, config: GatewayConfig, robot_client: RobotActionClient, logger: Logger):
        self.config = config
        self.robot_client = robot_client
        self.logger = logger

        # 状态
        self.state = STATE_IDLE
        self.lock = threading.Lock()

        # 待执行槽（latest-wins，至多一条）
        self.pending: Optional[Dict[str, Any]] = None

        # 辅助量
        self.last_executed_action: Optional[str] = None
        self.emotion_reset = True  # 初始为True，允许第一次触发

        # 统计
        self.total_triggers = 0
        self.last_trigger_at: Optional[str] = None

    def handle_update(self, emotion_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理情绪更新

        Args:
            emotion_data: {"label": str, "intensity": float, ...}

        Returns:
            响应字典 {"status": str, "state": str, "last_action": str}
        """
        label = emotion_data.get("label")
        intensity = emotion_data.get("intensity", 0)
        confidence = emotion_data.get("confidence", 0)
        updated_at = emotion_data.get("updated_at", "")

        with self.lock:
            # 标签映射到动作
            action_name = self.config.emotion_map.get(label)

            if label == "None" or action_name is None:
                # 情绪平复或无映射标签
                self.pending = None
                self.emotion_reset = True

                self.logger.info(
                    f"UPDATE reset label={label} updated_at={updated_at}"
                )
                return {
                    "status": "reset",
                    "state": self.state,
                    "last_action": self.last_executed_action or ""
                }

            # 检查动作是否在白名单中
            whitelist = self.config.actions_config.get("whitelist", [])
            if action_name not in whitelist:
                self.logger.warning(
                    f"Action '{action_name}' not in whitelist: {whitelist}"
                )
                return {
                    "status": "rejected",
                    "reason": f"Action '{action_name}' not in whitelist"
                }

            if self.state == STATE_IDLE:
                # idle时即时决策
                return self._consume_immediate(
                    label, action_name, intensity, confidence, updated_at
                )
            else:
                # busy时记入pending槽（latest-wins）
                self.pending = {
                    "label": label,
                    "action": action_name,
                    "intensity": intensity,
                    "confidence": confidence,
                    "updated_at": updated_at
                }

                self.logger.info(
                    f"UPDATE queued_latest emotion={label} action={action_name} "
                    f"state={self.state}（已记入待执行槽）"
                )
                return {
                    "status": "queued_latest",
                    "state": self.state,
                    "last_action": self.last_executed_action or ""
                }

    def _consume_immediate(
        self, label: str, action_name: str,
        intensity: float, confidence: float, updated_at: str
    ) -> Dict[str, Any]:
        """即时消费决策（idle时和完成后共用）"""
        # 同动作且无平静期 → 跳过
        if (action_name == self.last_executed_action and
                not self.emotion_reset):
            self.logger.info(
                f"UPDATE skipped_same_action emotion={label} action={action_name} "
                f"updated_at={updated_at} intensity={intensity:.2f}（同动作且无平静期）"
            )
            return {
                "status": "skipped_same_action",
                "state": self.state,
                "last_action": self.last_executed_action or ""
            }

        # 执行动作
        return self._execute_action(label, action_name, updated_at, intensity, confidence)

    def _execute_action(
        self, label: str, action_name: str, updated_at: str,
        intensity: float, confidence: float
    ) -> Dict[str, Any]:
        """执行动作"""
        # 动作运行时长（结束后归位到站立）
        duration = self.config.action_run_duration

        # 检查机器人是否在线
        if not self.robot_client.is_robot_online():
            self.logger.warning("Robot is offline, cannot trigger action")
            return {
                "status": "robot_offline",
                "state": self.state,
                "last_action": self.last_executed_action or ""
            }

        # 更新状态
        self.state = STATE_BUSY
        self.last_executed_action = action_name
        self.emotion_reset = False
        self.total_triggers += 1
        self.last_trigger_at = datetime.now().isoformat()

        self.logger.info(
            f"UPDATE triggered emotion={label} action={action_name} "
            f"updated_at={updated_at} intensity={intensity:.2f} confidence={confidence:.2f}"
        )

        # 在执行线程中执行动作
        threading.Thread(
            target=self._execute_action_thread,
            args=(action_name, duration),
            daemon=True
        ).start()

        return {
            "status": "triggered",
            "state": self.state,
            "last_action": action_name
        }

    def _execute_action_thread(self, action_name: str, duration: float):
        """动作执行线程"""
        try:
            success = True
            if self.config.dry_run:
                self.logger.info(
                    f"=== DRY-RUN: 将触发 {action_name}（运行 {duration}s 后归位） ==="
                )
            else:
                success = self.robot_client.trigger_action(action_name)
                if not success:
                    self.logger.error(f"Failed to trigger action: {action_name}")

            # 动作运行 duration 秒
            time.sleep(duration)

            # 动作结束后归位到站立（LT+RT+start，"zero" 轨迹）
            if success and self.config.recover_to_stand:
                if self.config.dry_run:
                    self.logger.info(
                        f"=== DRY-RUN: 归位到站立（LT+RT+start），等待 {self.config.recover_duration}s ==="
                    )
                else:
                    recover = getattr(self.robot_client, "recover_to_stand", None)
                    if recover is not None:
                        recover()
                    else:
                        self.logger.warning("Robot client has no recover_to_stand; skipping")
                time.sleep(self.config.recover_duration)
        except Exception as e:
            self.logger.error(f"Action execution error: {e}")
        finally:
            self._action_completed()

    def _action_completed(self):
        """动作完成后处理"""
        with self.lock:
            # 等待 settle_gap 让机器人回到默认姿态
            settle_gap = self.config.settle_gap

            self.logger.info(
                f"Action completed, waiting {settle_gap}s for settle gap"
            )
            time.sleep(settle_gap)

            # 消费pending槽
            if self.pending is None:
                self.state = STATE_IDLE
                self.logger.info("Action completed, no pending, back to idle")
            else:
                pending_data = self.pending
                self.pending = None

                # 使用相同的消费决策
                self.logger.info(
                    f"Action completed, consuming pending: emotion={pending_data['label']} "
                    f"action={pending_data['action']}"
                )

                # 临时设为idle以便可以执行新动作
                self.state = STATE_IDLE

                # 消费pending（与idle时的即时决策走同一逻辑）
                result = self._consume_immediate(
                    pending_data["label"],
                    pending_data["action"],
                    pending_data["intensity"],
                    pending_data["confidence"],
                    pending_data["updated_at"]
                )

                self.logger.info(f"Pending consumed: status={result['status']}")

    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        with self.lock:
            return {
                "status": "ok",
                "mode": "dry-run" if self.config.dry_run else "real",
                "busy": (self.state == STATE_BUSY),
                "robot_online": self.robot_client.is_robot_online(),
                "last_action": self.last_executed_action or "",
                "last_trigger_at": self.last_trigger_at or "",
                "total_triggers": self.total_triggers
            }


class BridgeHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP请求处理器"""

    # 状态机实例（由服务器设置）
    state_machine: Optional[ActionStateMachine] = None
    auth_token: str = ""
    logger: Optional[Logger] = None

    def log_message(self, format, *args):
        """覆盖默认的日志输出"""
        if self.logger:
            self.logger.info(f"{self.address_string()} - {format % args}")

    def _send_json_response(self, status_code: int, data: Dict[str, Any]):
        """发送JSON响应"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_error(self, status_code: int, message: str):
        """发送错误响应"""
        self._send_json_response(status_code, {"status": "error", "reason": message})

    def verify_auth(self) -> bool:
        """验证鉴权token"""
        if not self.auth_token:
            return True
        token = self.headers.get("X-Bridge-Token", "")
        return token == self.auth_token

    def do_GET(self):
        """处理GET请求"""
        if self.path == "/health":
            if not self.verify_auth():
                self._send_error(401, "Unauthorized")
                return

            if self.state_machine:
                status = self.state_machine.get_health_status()
                self._send_json_response(200, status)
            else:
                self._send_error(503, "State machine not initialized")
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        """处理POST请求"""
        if not self.verify_auth():
            self._send_error(401, "Unauthorized")
            return

        if self.path == "/emotion":
            if self.state_machine is None:
                self._send_error(503, "State machine not initialized")
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                emotion_data = json.loads(body.decode("utf-8"))

                # 验证必填字段
                if "label" not in emotion_data:
                    self._send_error(400, "Missing 'label' field")
                    return

                # 处理更新
                result = self.state_machine.handle_update(emotion_data)
                self._send_json_response(200, result)

            except json.JSONDecodeError:
                self._send_error(400, "Invalid JSON")
            except Exception as e:
                self.logger.error(f"Error handling emotion update: {e}")
                self._send_error(500, str(e))
        else:
            self._send_error(404, "Not found")


def setup_logger(log_dir: str, component: str) -> Logger:
    """设置日志"""
    logger = getLogger(component)
    logger.setLevel(INFO)

    # 确保日志目录存在
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 文件handler（按天滚动）
    log_file = log_path / f"{component}_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.suffix = "%Y%m%d"
    file_handler.setFormatter(
        Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(file_handler)

    # 控制台handler
    console_handler = StreamHandler(sys.stdout)
    console_handler.setFormatter(
        Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(console_handler)

    return logger


def load_config(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_config(config: Dict[str, Any]):
    """验证配置"""
    gateway_cfg = config.get("gateway", {})

    # 检查gateway配置
    port = gateway_cfg.get("listen_port", 8790)
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError(f"Invalid listen_port: {port}")

    # 检查trigger_impl
    robot_cfg = config.get("robot", {})
    trigger_impl = robot_cfg.get("trigger_impl", "A")
    if trigger_impl not in ["A", "B"]:
        raise ValueError(f"Invalid trigger_impl: {trigger_impl}")

    # 检查emotion_map的值是否在whitelist中
    emotion_map = config.get("emotion_map", {})
    actions_cfg = config.get("actions", {})
    whitelist = actions_cfg.get("whitelist", [])

    for emotion, action in emotion_map.items():
        if action not in whitelist:
            raise ValueError(
                f"Action '{action}' for emotion '{emotion}' not in whitelist: {whitelist}"
            )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Robot Gateway Service")
    parser.add_argument(
        "--config", "-c",
        default="bridge_config.json",
        help="Path to config file (default: bridge_config.json)"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Override config and run in dry-run mode"
    )
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    validate_config(config)

    # 创建日志
    log_dir = config.get("log_dir", "logs")
    logger = setup_logger(log_dir, "gateway")

    # 命令行dry-run优先
    if args.dry_run:
        config["gateway"]["dry_run"] = True

    gateway_config = GatewayConfig(config)

    # 打印启动横幅
    if gateway_config.dry_run:
        print("=" * 60)
        print("=== DRY-RUN 模式，不会真正触发机器人 ===")
        print("=" * 60)

    logger.info("=" * 60)
    logger.info("Robot Gateway starting")
    logger.info(f"Listen: {gateway_config.listen_host}:{gateway_config.listen_port}")
    logger.info(f"Mode: {'dry-run' if gateway_config.dry_run else 'real'}")
    logger.info(f"Settle gap: {gateway_config.settle_gap}s")
    logger.info(f"Emotion map: {gateway_config.emotion_map}")
    logger.info(f"Action whitelist: {gateway_config.actions_config.get('whitelist', [])}")
    logger.info("=" * 60)

    # 创建机器人客户端
    try:
        robot_client = create_robot_client(config["robot"])
    except Exception as e:
        logger.error(f"Failed to create robot client: {e}")
        sys.exit(1)

    # 创建状态机
    state_machine = ActionStateMachine(gateway_config, robot_client, logger)

    # 设置HTTP处理器属性
    BridgeHTTPRequestHandler.state_machine = state_machine
    BridgeHTTPRequestHandler.auth_token = gateway_config.auth_token
    BridgeHTTPRequestHandler.logger = logger

    # 启动HTTP服务器
    server = ThreadingHTTPServer(
        (gateway_config.listen_host, gateway_config.listen_port),
        BridgeHTTPRequestHandler
    )

    logger.info(f"Server started on http://{gateway_config.listen_host}:{gateway_config.listen_port}")
    logger.info("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
