#!/usr/bin/env python3
"""
情绪文件模拟工具

用于生成测试用的 current_emotion.json 文件
支持命令行参数指定情绪标签、消息强度等
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


# 情绪标签常量
EMOTION_NONE = "None"
EMOTION_HAPPY = "开心"
EMOTION_SAD = "难过"


def generate_emotion_data(
    label: str,
    message: Optional[str] = None,
    intensity: Optional[float] = None,
    confidence: Optional[float] = None
) -> Dict[str, Any]:
    """
    生成符合schema的情绪数据

    Args:
        label: 情绪标签（None/开心/难过）
        message: 用户消息
        intensity: 情绪强度（0-1）
        confidence: 置信度（0-1）

    Returns:
        符合schema的字典
    """
    # 生成合理的默认值
    if intensity is None:
        if label == EMOTION_HAPPY:
            intensity = 0.7
        elif label == EMOTION_SAD:
            intensity = 0.6
        else:
            intensity = 0.0

    if confidence is None:
        if label == EMOTION_NONE:
            confidence = 0.5
        else:
            confidence = 0.85

    # 根据情绪生成合理的信号和趋势
    signals = []
    trend = "新出现"

    if label == EMOTION_HAPPY:
        signals = ["开心", "llm_judge"]
        trend = "新出现"
    elif label == EMOTION_SAD:
        signals = ["难过", "llm_judge"]
        trend = "新出现"
    else:
        signals = ["中性"]
        trend = "趋于平稳"

    # 生成时间戳
    updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+0800")

    # 默认消息
    if message is None:
        if label == EMOTION_HAPPY:
            message = "今天面试通过了，太开心了！"
        elif label == EMOTION_SAD:
            message = "今天好累，有点难过..."
        else:
            message = "今天天气不错"

    return {
        "updated_at": updated_at,
        "user_message": message,
        "emotion": {
            "label": label,
            "intensity": intensity,
            "confidence": confidence,
            "reason": f"用户表达情绪;llm_judge",
            "signals": signals,
            "trend": trend,
            "context_turns": 1
        }
    }


def write_emotion_file(file_path: Path, data: Dict[str, Any]):
    """
    原子写入情绪文件

    先写.tmp临时文件，再replace覆盖，确保读取方不会读到半个JSON

    Args:
        file_path: 目标文件路径
        data: 要写入的数据
    """
    temp_path = file_path.with_suffix(".json.tmp")

    # 写入临时文件
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 原子替换
    temp_path.replace(file_path)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="模拟生成 current_emotion.json 文件用于测试"
    )
    parser.add_argument(
        "--label", "-l",
        choices=["None", "开心", "难过"],
        default="开心",
        help="情绪标签（默认: 开心）"
    )
    parser.add_argument(
        "--message", "-m",
        help="用户消息内容"
    )
    parser.add_argument(
        "--intensity", "-i",
        type=float,
        help="情绪强度（0-1）"
    )
    parser.add_argument(
        "--confidence", "-c",
        type=float,
        help="置信度（0-1）"
    )
    parser.add_argument(
        "--file", "-f",
        help="输出文件路径（默认: prototype_demo/.run/current_emotion.json）"
    )
    parser.add_argument(
        "--print", "-p",
        action="store_true",
        help="只打印JSON不写入文件"
    )
    args = parser.parse_args()

    # 生成数据
    data = generate_emotion_data(
        label=args.label,
        message=args.message,
        intensity=args.intensity,
        confidence=args.confidence
    )

    # 只打印
    if args.print:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    # 确定输出路径
    if args.file:
        output_path = Path(args.file)
    else:
        # 默认路径
        base_dir = Path(__file__).resolve().parent.parent
        output_path = base_dir / "prototype_demo" / ".run" / "current_emotion.json"

    # 确保目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入文件
    write_emotion_file(output_path, data)

    print(f"✓ 已写入: {output_path}")
    print(f"  标签: {data['emotion']['label']}")
    print(f"  消息: {data['user_message']}")
    print(f"  强度: {data['emotion']['intensity']}")
    print(f"  置信度: {data['emotion']['confidence']}")


if __name__ == "__main__":
    main()
