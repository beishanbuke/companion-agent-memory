#!/usr/bin/env python3
"""Companion Agent v2 场景测试脚本

测试4个核心场景：
1. 高压切闲聊 -> 再回主线
2. 今日复盘
3. 本周复盘
4. 倾诉后轻推一步

每个场景运行多轮对话，输出：
- 每轮的意图分析
- 状态转移
- 策略决策
- Agent回复
- 关系记忆变化
"""

import json
import requests
import uuid
import sys
from typing import Any

BASE_URL = "http://127.0.0.1:8765"

class SessionTester:
    def __init__(self, name: str):
        self.name = name
        self.session_id = str(uuid.uuid4())
        self.user_id = f"test-{name}"
        self.messages = []
        self.turn = 0
        
    def send(self, message: str, description: str = "") -> dict:
        """发送消息并返回完整响应"""
        self.turn += 1
        print(f"\n{'='*60}")
        print(f"【{self.name}】第{self.turn}轮: {description}")
        print(f"{'='*60}")
        print(f"用户: {message}")
        print(f"-"*60)
        
        payload = {
            "message": message,
            "memory_enabled": True,
            "use_v2_brain": True,
            "session_id": self.session_id,
            "user_id": self.user_id,
        }
        
        try:
            resp = requests.post(
                f"{BASE_URL}/api/chat",
                json=payload,
                timeout=60
            )
            data = resp.json()
            
            if "error" in data:
                print(f"❌ 错误: {data['error']}")
                return data
            
            # 打印关键信息
            self._print_turn_analysis(data)
            
            # 保存消息
            self.messages.append({"role": "user", "content": message})
            self.messages.append({"role": "assistant", "content": data.get("reply", "")})
            
            return data
            
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            return {"error": str(e)}
    
    def _print_turn_analysis(self, data: dict):
        """打印回合分析"""
        # Agent回复
        reply = data.get("reply", "")
        print(f"Agent: {reply[:200]}{'...' if len(reply) > 200 else ''}")
        print(f"-"*60)
        
        # v2调试信息
        v2 = data.get("v2", {})
        if v2:
            print(f"\n📊 意图分析:")
            intent = v2.get("intent", {})
            print(f"  主要意图: {intent.get('primary_intent', 'N/A')}")
            print(f"  情绪强度: {intent.get('emotional_intensity', 'N/A')}")
            print(f"  对话节奏: {intent.get('conversation_rhythm', 'N/A')}")
            print(f"  行动接受度: {intent.get('action_receptivity', 'N/A')}")
            print(f"  压力信号: {intent.get('pressure_signal', 'N/A')}")
            print(f"  话题切换: {intent.get('topic_shift_type', 'N/A')}")
            
            print(f"\n🎯 状态与策略:")
            print(f"  当前状态: {v2.get('current_state', 'N/A')}")
            print(f"  策略目标: {v2.get('policy_goal', 'N/A')}")
            print(f"  允许建议: {v2.get('allow_advice', 'N/A')}")
            print(f"  允许幽默: {v2.get('allow_humor', 'N/A')}")
            print(f"  拉回主线: {v2.get('pull_main_thread', 'N/A')}")
            
            print(f"\n💝 关系记忆:")
            rel = v2.get("relationship", {})
            if rel:
                print(f"  亲密度: {rel.get('intimacy_level', 'N/A')}")
                print(f"  画像变化: {rel.get('profile_changed', False)}")
        
        # Legacy信息
        legacy = data.get("legacy", {})
        if legacy:
            print(f"\n📌 情境: {legacy.get('situation', 'N/A')}")
        
        print(f"\n{'='*60}")


def test_scenario_1_high_pressure_switch():
    """场景1: 高压切闲聊 -> 再回主线"""
    print("\n" + "🔄"*30)
    print("场景1: 高压切闲聊 -> 再回主线")
    print("🔄"*30)
    
    s = SessionTester("高压切闲聊")
    
    # 轮1: 用户表达高压
    s.send(
        "我明天要交论文初稿，现在只写了500字，根本写不完，我要崩溃了。",
        "用户高压倾诉"
    )
    
    # 轮2: 用户主动切到闲聊
    s.send(
        "算了不想说这个了，你最近有看什么好玩的剧吗？",
        "用户主动切到闲聊（逃避压力）"
    )
    
    # 轮3: 在闲聊中agent尝试轻推回主线
    # 此时应该是 stay_light 或尝试 pull_main_thread
    
    # 轮4: 用户情绪稳定，可以回主线
    s.send(
        "其实还是有点焦虑... 你觉得我现在应该先做哪部分？",
        "用户情绪回落，自然回到主线"
    )
    
    # 轮5: 推进主线
    s.send(
        "好的，那我先把文献综述整理出来。",
        "用户接受建议，回到任务执行"
    )
    
    return s


def test_scenario_2_daily_review():
    """场景2: 今日复盘"""
    print("\n" + "📋"*30)
    print("场景2: 今日复盘")
    print("📋"*30)
    
    s = SessionTester("今日复盘")
    
    # 轮1: 用户主动要求复盘
    s.send(
        "今天过得有点乱，帮我复盘一下今天发生了什么。",
        "用户主动要求今日复盘"
    )
    
    # 轮2: 补充细节
    s.send(
        "早上去了图书馆但效率很低，下午一直在刷手机，晚上吃了外卖现在有点后悔。",
        "用户补充今日细节"
    )
    
    # 轮3: 用户询问建议
    s.send(
        "嗯，确实是刷手机太久了。明天怎么改善？",
        "用户在复盘后寻求建议"
    )
    
    return s


def test_scenario_3_weekly_review():
    """场景3: 本周复盘"""
    print("\n" + "📅"*30)
    print("场景3: 本周复盘")
    print("📅"*30)
    
    s = SessionTester("本周复盘")
    
    # 轮1: 用户主动要求周复盘
    s.send(
        "这周感觉过得好快，但又好像没做几件事，帮我梳理一下这周。",
        "用户主动要求本周复盘"
    )
    
    # 轮2: 补充细节
    s.send(
        "周一到周三在赶项目，周四周五有点松懈，周末基本在睡觉。",
        "用户补充本周细节"
    )
    
    # 轮3: 用户询问下周建议
    s.send(
        "对，周四开始就没状态了。下周怎么避免这种情况？",
        "用户复盘后寻求改进建议"
    )
    
    return s


def test_scenario_4_vent_then_push():
    """场景4: 倾诉后轻推一步"""
    print("\n" + "💬"*30)
    print("场景4: 倾诉后轻推一步")
    print("💬"*30)
    
    s = SessionTester("倾诉后轻推")
    
    # 轮1: 用户深度倾诉
    s.send(
        "我觉得我最近好失败，什么都做不好，真的好累。",
        "用户深度倾诉情绪"
    )
    
    # 轮2: 用户继续倾诉
    s.send(
        "就是实习被拒了，论文也被导师打回来重写，感觉事事不顺。",
        "用户继续展开倾诉内容"
    )
    
    # 轮3: Agent应该在此轮轻推一步
    # 检查是否给出小而具体的建议
    
    # 轮4: 用户回应轻推
    s.send(
        "嗯，你说得对，我现在可能想得太大了。",
        "用户接受轻推，情绪开始回落"
    )
    
    # 轮5: 具体行动
    s.send(
        "那我明天先改论文的前两章吧，其他的先不想。",
        "用户提出具体行动"
    )
    
    return s


def main():
    print("="*60)
    print("Companion Agent v2 核心场景测试")
    print("="*60)
    
    # 检查服务状态
    try:
        resp = requests.post(f"{BASE_URL}/api/companion/status", json={}, timeout=5)
        print(f"\n✅ 服务状态: {resp.status_code}")
    except Exception as e:
        print(f"\n❌ 服务未启动: {e}")
        print("请先运行: ./start_prototype_demo.sh")
        sys.exit(1)
    
    # 运行4个场景
    results = {}
    
    try:
        results["高压切闲聊"] = test_scenario_1_high_pressure_switch()
    except Exception as e:
        print(f"\n❌ 场景1失败: {e}")
    
    try:
        results["今日复盘"] = test_scenario_2_daily_review()
    except Exception as e:
        print(f"\n❌ 场景2失败: {e}")
    
    try:
        results["本周复盘"] = test_scenario_3_weekly_review()
    except Exception as e:
        print(f"\n❌ 场景3失败: {e}")
    
    try:
        results["倾诉后轻推"] = test_scenario_4_vent_then_push()
    except Exception as e:
        print(f"\n❌ 场景4失败: {e}")
    
    # 总结报告
    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)
    for name, session in results.items():
        if session:
            print(f"\n{name}:")
            print(f"  会话ID: {session.session_id}")
            print(f"  总轮数: {session.turn}")
            print(f"  消息数: {len(session.messages)}")


if __name__ == "__main__":
    main()
