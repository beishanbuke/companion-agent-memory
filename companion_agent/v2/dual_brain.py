"""
Dual Brain Router v2

双脑模式路由器：
- Chat Mode（左脑）：纯陪伴、闲聊、情绪承接、玩梗、接话
- Task Mode（右脑）：学习规划、饮食建议、工具调用、信息查询

决策逻辑：
1. 先看意图分析，判断用户是要陪伴还是要做事
2. 再看对话状态，如果用户在情绪中，优先chat mode
3. 如果用户明确要执行某事，切task mode
4. 如果task不急且对话已连续多轮，保持chat mode
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BrainMode:
    """双脑模式决策结果。"""
    mode: str  # "chat" or "task"
    confidence: float
    reason: str
    task_type: str  # 如果mode=task，具体是什么任务
    
    # 混合模式指示
    chat_priority: float  # 0-1，chat成分的权重
    task_priority: float  # 0-1，task成分的权重
    
    # 执行策略
    should_use_tools: bool
    should_use_memory: bool
    response_style: str  # 最终回复风格指导


class DualBrainRouter:
    """双脑模式路由器。"""
    
    # 任务类型分类
    TASK_TYPES = {
        "food": {"name": "饮食", "urgency_default": 0.5},
        "study": {"name": "学习", "urgency_default": 0.7},
        "social": {"name": "社交", "urgency_default": 0.4},
        "campus": {"name": "校园", "urgency_default": 0.4},
        "music": {"name": "音乐", "urgency_default": 0.3},
        "outfit": {"name": "穿搭", "urgency_default": 0.3},
        "tool": {"name": "工具", "urgency_default": 0.6},
    }
    
    def route(
        self,
        intent_analysis: Any,
        conversation_state: Any,
    ) -> BrainMode:
        """决定使用哪种模式。"""
        
        primary = intent_analysis.primary_intent
        task_cat = intent_analysis.task_category
        urgency = intent_analysis.task_urgency
        emotion_intensity = intent_analysis.emotional_intensity
        rhythm = intent_analysis.conversation_rhythm
        
        # === 规则1：情绪高强度时，优先chat mode ===
        if emotion_intensity > 0.7 and primary in ("companion", "vent", "share", "quiet"):
            return BrainMode(
                mode="chat",
                confidence=0.85,
                reason=f"用户情绪强度高({emotion_intensity:.1f})，需要陪伴优先",
                task_type="none",
                chat_priority=0.9,
                task_priority=0.1,
                should_use_tools=False,
                should_use_memory=True,
                response_style="empathetic",
            )
        
        # === 规则2：用户明确想安静 ===
        if primary == "quiet":
            return BrainMode(
                mode="chat",
                confidence=0.9,
                reason="用户想安静",
                task_type="none",
                chat_priority=1.0,
                task_priority=0.0,
                should_use_tools=False,
                should_use_memory=False,
                response_style="gentle",
            )
        
        # === 规则3：用户在吐槽/犯贱，保持chat mode ===
        if rhythm in ("venting", "bantering"):
            return BrainMode(
                mode="chat",
                confidence=0.8,
                reason=f"用户在{rhythm}模式，不适合切入任务",
                task_type="none",
                chat_priority=0.85,
                task_priority=0.15,
                should_use_tools=False,
                should_use_memory=True,
                response_style="casual",
            )
        
        # === 规则4：明确要执行任务 ===
        if primary == "execute" and task_cat != "none":
            return BrainMode(
                mode="task",
                confidence=0.85,
                reason=f"用户明确要求执行任务：{task_cat}",
                task_type=task_cat,
                chat_priority=0.2,
                task_priority=0.8,
                should_use_tools=True,
                should_use_memory=True,
                response_style="direct",
            )
        
        # === 规则5：需要建议但任务不急 ===
        if primary == "advice" and urgency < 0.5:
            # 如果在连续对话中，保持chat mode但带轻微task
            if conversation_state.mode_duration > 2 and conversation_state.mode != "planning":
                return BrainMode(
                    mode="chat",
                    confidence=0.7,
                    reason="任务不急，且在连续对话中，保持陪伴感",
                    task_type=task_cat,
                    chat_priority=0.7,
                    task_priority=0.3,
                    should_use_tools=False,
                    should_use_memory=True,
                    response_style="casual",
                )
            else:
                return BrainMode(
                    mode="task",
                    confidence=0.7,
                    reason=f"用户需要建议：{task_cat}",
                    task_type=task_cat,
                    chat_priority=0.4,
                    task_priority=0.6,
                    should_use_tools=False,
                    should_use_memory=True,
                    response_style="helpful",
                )
        
        # === 规则6：需要建议且任务较急 ===
        if primary == "advice" and urgency >= 0.5:
            return BrainMode(
                mode="task",
                confidence=0.8,
                reason=f"用户需要较急的建议：{task_cat}(urgency={urgency:.1f})",
                task_type=task_cat,
                chat_priority=0.3,
                task_priority=0.7,
                should_use_tools=True if urgency > 0.7 else False,
                should_use_memory=True,
                response_style="helpful",
            )
        
        # === 规则7：倾诉模式 ===
        if rhythm == "confiding":
            return BrainMode(
                mode="chat",
                confidence=0.85,
                reason="用户在倾诉心事",
                task_type="none",
                chat_priority=0.95,
                task_priority=0.05,
                should_use_tools=False,
                should_use_memory=True,
                response_style="empathetic",
            )
        
        # === 默认：普通闲聊 ===
        return BrainMode(
            mode="chat",
            confidence=0.6,
            reason="普通对话，默认陪伴模式",
            task_type=task_cat if task_cat != "none" else "none",
            chat_priority=0.8,
            task_priority=0.2,
            should_use_tools=False,
            should_use_memory=True,
            response_style="casual",
        )
    
    def blend_system_prompt(
        self,
        base_prompt: str,
        brain_mode: BrainMode,
        state_guidance: str,
    ) -> str:
        """根据双脑模式混合系统提示词。"""
        
        if brain_mode.mode == "chat":
            mode_prompt = f"""【当前模式：陪伴模式】
{state_guidance}

回复原则：
- 优先接话、承接情绪、延续话题
- 像朋友一样自然，不要像助手
- 允许废话、跑偏、轻微玩梗
- 不要每轮都试图"解决问题"
- 如果用户只是吐槽，就给情绪价值，不要给方案
- 单轮回复 2-4 句话，保持呼吸感
"""
        else:
            mode_prompt = f"""【当前模式：任务模式】
任务类型：{brain_mode.task_type}

回复原则：
- 先确认需求，再给方案
- 保持朋友口吻，不要变成客服或说明书
- 给出具体、可执行的建议
- 不要一次给太多信息，分步来
- 做完任务后，自然回到闲聊节奏
- 单轮回复 3-5 句话
"""
        
        return f"{base_prompt}\n\n{mode_prompt}"
