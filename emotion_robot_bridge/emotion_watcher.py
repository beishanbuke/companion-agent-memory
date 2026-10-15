#!/usr/bin/env python3
"""
情绪文件监听器

负责：
1. 轮询读取 current_emotion.json
2. 计算SHA-256指纹进行去重
3. 将每个新结果（含None）通过HTTP POST发送给robot_gateway
4. 容错处理：文件不存在/JSON错误/网络错误都只记日志，继续运行
"""

import json
import time
import hashlib
import argparse
import sys
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from logging import (
    getLogger, Logger, Formatter, StreamHandler,
    INFO, WARNING, ERROR, DEBUG
)
from logging.handlers import TimedRotatingFileHandler


class WatcherConfig:
    """监听器配置"""

    def __init__(self, config_dict: Dict[str, Any]):
        watcher_cfg = config_dict.get("watcher", {})

        self.emotion_file = watcher_cfg.get("emotion_file", "")
        self.poll_interval = watcher_cfg.get("poll_interval", 0.5)
        self.gateway_url = watcher_cfg.get("gateway_url", "http://127.0.0.1:8790")
        self.request_timeout = watcher_cfg.get("request_timeout", 3.0)
        self.dry_run = watcher_cfg.get("dry_run", False)
        self.auth_token = config_dict.get("gateway", {}).get("auth_token", "")


class EmotionWatcher:
    """情绪文件监听器"""

    def __init__(self, config: WatcherConfig, logger: Logger):
        self.config = config
        self.logger = logger

        # 去重状态
        self.last_hash: Optional[str] = None
        self.file_path = Path(config.emotion_file)

        # 统计
        self.poll_count = 0
        self.update_count = 0
        self.label_counts: Dict[str, int] = {}
        self.start_time = datetime.now()

    def _calculate_hash(self, content: bytes) -> str:
        """计算内容的SHA-256哈希"""
        return hashlib.sha256(content).hexdigest()

    def _read_emotion_file(self) -> Optional[Dict[str, Any]]:
        """读取情绪文件"""
        try:
            if not self.file_path.exists():
                self.logger.info(f"Emotion file does not exist yet: {self.file_path}")
                return None

            raw = self.file_path.read_bytes()
            if not raw:
                self.logger.warning("Emotion file is empty")
                return None

            data = json.loads(raw.decode("utf-8"))
            return data

        except json.JSONDecodeError as e:
            self.logger.warning(f"JSON decode error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error reading emotion file: {e}")
            return None

    def _send_to_gateway(self, emotion_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """发送情绪数据到网关"""
        if self.config.dry_run:
            self.logger.info(
                f"[DRY-RUN] Would send: label={emotion_data.get('label')} "
                f"intensity={emotion_data.get('intensity', 0):.2f}"
            )
            return {"status": "dry_run"}

        url = f"{self.config.gateway_url}/emotion"
        payload = json.dumps(emotion_data, ensure_ascii=False).encode("utf-8")

        try:
            request = Request(url, data=payload, method="POST")
            request.add_header("Content-Type", "application/json; charset=utf-8")

            if self.config.auth_token:
                request.add_header("X-Bridge-Token", self.config.auth_token)

            response = urlopen(request, timeout=self.config.request_timeout)
            response_data = json.loads(response.read().decode("utf-8"))
            return response_data

        except HTTPError as e:
            self.logger.error(f"HTTP error: {e.code} - {e.reason}")
            return None
        except URLError as e:
            self.logger.error(f"URL error: {e.reason}")
            return None
        except Exception as e:
            self.logger.error(f"Request error: {e}")
            return None

    def _process_update(self, data: Dict[str, Any]):
        """处理情绪更新"""
        emotion = data.get("emotion", {})
        label = emotion.get("label", "None")
        intensity = emotion.get("intensity", 0)
        confidence = emotion.get("confidence", 0)
        updated_at = data.get("updated_at", "")

        # 构造发送给网关的数据
        gateway_data = {
            "label": label,
            "intensity": intensity,
            "confidence": confidence,
            "updated_at": updated_at,
            "user_message": data.get("user_message", "")
        }

        # 发送到网关
        response = self._send_to_gateway(gateway_data)

        # 记录日志
        if response:
            status = response.get("status", "unknown")
            action = response.get("last_action", "")
            self.logger.info(
                f"Delivered: label={label} status={status} action={action} "
                f"intensity={intensity:.2f} updated_at={updated_at}"
            )
        else:
            self.logger.warning(f"Failed to deliver: label={label}")

        # 更新统计
        self.update_count += 1
        self.label_counts[label] = self.label_counts.get(label, 0) + 1

    def watch_once(self) -> bool:
        """执行一次监听（返回是否发现新内容）"""
        self.poll_count += 1

        try:
            # 读取文件
            data = self._read_emotion_file()
            if data is None:
                return False

            # 计算哈希
            raw = self.file_path.read_bytes()
            current_hash = self._calculate_hash(raw)

            # 去重
            if current_hash == self.last_hash:
                return False

            # 发现新内容
            self.last_hash = current_hash
            self._process_update(data)
            return True

        except Exception as e:
            self.logger.error(f"Error in watch loop: {e}")
            return False

    def run(self):
        """运行监听循环"""
        # 初始化：读取现有文件内容，避免触发启动前的旧结果
        if self.file_path.exists():
            try:
                raw = self.file_path.read_bytes()
                self.last_hash = self._calculate_hash(raw)
                self.logger.info(f"Initialized with existing file, hash: {self.last_hash[:16]}...")
            except Exception as e:
                self.logger.warning(f"Failed to initialize hash: {e}")

        # 打印启动信息
        self.logger.info("=" * 60)
        self.logger.info("Emotion Watcher started")
        self.logger.info(f"Watching: {self.config.emotion_file}")
        self.logger.info(f"Gateway: {self.config.gateway_url}")
        self.logger.info(f"Poll interval: {self.config.poll_interval}s")
        self.logger.info(f"Mode: {'dry-run' if self.config.dry_run else 'real'}")
        self.logger.info("=" * 60)

        # 主循环
        try:
            while True:
                self.watch_once()
                time.sleep(self.config.poll_interval)
        except KeyboardInterrupt:
            self._print_summary()

    def _print_summary(self):
        """打印统计摘要"""
        duration = datetime.now() - self.start_time
        self.logger.info("=" * 60)
        self.logger.info("Emotion Watcher stopped")
        self.logger.info(f"Duration: {duration}")
        self.logger.info(f"Total polls: {self.poll_count}")
        self.logger.info(f"Updates delivered: {self.update_count}")
        self.logger.info(f"Label distribution: {self.label_counts}")
        self.logger.info("=" * 60)


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
    watcher_cfg = config.get("watcher", {})

    # 检查必填项
    if not watcher_cfg.get("emotion_file"):
        raise ValueError("Missing 'watcher.emotion_file' in config")

    # 检查poll_interval
    poll_interval = watcher_cfg.get("poll_interval", 0.5)
    if not isinstance(poll_interval, (int, float)) or poll_interval <= 0:
        raise ValueError(f"Invalid poll_interval: {poll_interval}")

    # 检查timeout
    timeout = watcher_cfg.get("request_timeout", 3.0)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError(f"Invalid request_timeout: {timeout}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Emotion File Watcher")
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

    # 命令行dry-run优先
    if args.dry_run:
        config["watcher"]["dry_run"] = True

    watcher_config = WatcherConfig(config)

    # 创建日志
    log_dir = config.get("log_dir", "logs")
    logger = setup_logger(log_dir, "watcher")

    # 打印启动横幅
    if watcher_config.dry_run:
        print("=" * 60)
        print("=== DRY-RUN 模式，不会真正发送请求 ===")
        print("=" * 60)

    # 创建监听器
    watcher = EmotionWatcher(watcher_config, logger)

    # 运行
    try:
        watcher.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
