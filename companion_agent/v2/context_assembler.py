"""
Context Assembler

渐进式上下文加载器，根据当前状态和策略动态装配上下文块。

Context block 类型：
- identity_block: 角色身份
- relationship_block: 关系画像
- active_thread_block: 前台主线
- background_thread_block: 后台主线摘要
- state_policy_block: 状态机 + 策略
- task_context_block: 任务上下文
- memory_recall_block: 记忆召回
- tool_result_block: 工具结果

装配规则（按状态）：
- support_crisis: identity + active_thread + state_policy
- task_execution: identity + active_thread + task_context + memory
- light_chat: identity + relationship + active_thread摘要
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextBlock:
    """上下文块。"""
    block_type: str
    content: str
    priority: int = 50  # 0-100，越高越重要
    required: bool = True


class ContextAssembler:
    """上下文装配器。"""
    
    # 各状态对应的上下文块配置
    STATE_BLOCK_CONFIG = {
        "support_crisis": {
            "required": ["identity", "active_thread", "state_policy"],
            "optional": ["relationship"],
            "excluded": ["task_context", "background_thread", "tool_result"],
        },
        "support_soft": {
            "required": ["identity", "active_thread", "state_policy", "relationship"],
            "optional": ["memory_recall"],
            "excluded": ["task_context", "tool_result"],
        },
        "pushable_low_energy": {
            "required": ["identity", "active_thread", "state_policy"],
            "optional": ["task_context", "memory_recall"],
            "excluded": ["background_thread"],
        },
        "task_execution": {
            "required": ["identity", "active_thread", "task_context"],
            "optional": ["memory_recall", "tool_result", "background_thread"],
            "excluded": [],
        },
        "planning": {
            "required": ["identity", "active_thread", "task_context", "state_policy"],
            "optional": ["memory_recall"],
            "excluded": [],
        },
        "review_reflection": {
            "required": ["identity", "active_thread", "relationship"],
            "optional": ["memory_recall", "background_thread"],
            "excluded": ["task_context"],
        },
        "light_chat": {
            "required": ["identity", "relationship"],
            "optional": ["active_thread", "memory_recall"],
            "excluded": ["task_context", "tool_result"],
        },
        "banter": {
            "required": ["identity", "relationship"],
            "optional": ["active_thread"],
            "excluded": ["task_context", "tool_result", "state_policy"],
        },
    }
    
    def assemble(
        self,
        state: str,
        policy: Any,
        persona: str,
        relationship: dict[str, Any],
        active_thread: dict[str, Any],
        background_threads: list[dict[str, Any]],
        memory_context: str,
        task_context: str,
        tool_results: list[str],
    ) -> list[ContextBlock]:
        """装配上下文块。
        
        Args:
            state: 当前状态机状态
            policy: 策略决策
            persona: 角色提示词
            relationship: 关系画像
            active_thread: 前台主线
            background_threads: 后台主线列表
            memory_context: 记忆上下文
            task_context: 任务上下文
            tool_results: 工具结果列表
        """
        
        blocks = []
        config = self.STATE_BLOCK_CONFIG.get(state, self.STATE_BLOCK_CONFIG["light_chat"])
        
        # === 1. Identity Block (所有状态都需要) ===
        blocks.append(ContextBlock(
            block_type="identity",
            content=persona,
            priority=90,
            required=True,
        ))
        
        # === 2. State Policy Block ===
        if "state_policy" in config["required"] or "state_policy" in config["optional"]:
            policy_text = self._build_policy_text(policy)
            if policy_text:
                blocks.append(ContextBlock(
                    block_type="state_policy",
                    content=policy_text,
                    priority=85,
                    required="state_policy" in config["required"],
                ))
        
        # === 3. Relationship Block ===
        if "relationship" in config["required"] or "relationship" in config["optional"]:
            rel_text = self._build_relationship_text(relationship)
            if rel_text:
                blocks.append(ContextBlock(
                    block_type="relationship",
                    content=rel_text,
                    priority=70,
                    required="relationship" in config["required"],
                ))
        
        # === 4. Active Thread Block ===
        if "active_thread" in config["required"] or "active_thread" in config["optional"]:
            thread_text = self._build_thread_text(active_thread, is_active=True)
            if thread_text:
                blocks.append(ContextBlock(
                    block_type="active_thread",
                    content=thread_text,
                    priority=80,
                    required="active_thread" in config["required"],
                ))
        
        # === 5. Background Thread Block ===
        if "background_thread" in config["required"] or "background_thread" in config["optional"]:
            if background_threads and len(background_threads) > 0:
                # 只保留最多2个后台主线
                bg_text = self._build_background_threads_text(background_threads[:2])
                blocks.append(ContextBlock(
                    block_type="background_thread",
                    content=bg_text,
                    priority=40,
                    required="background_thread" in config["required"],
                ))
        
        # === 6. Task Context Block ===
        if "task_context" in config["required"] or "task_context" in config["optional"]:
            if task_context:
                blocks.append(ContextBlock(
                    block_type="task_context",
                    content=task_context,
                    priority=75,
                    required="task_context" in config["required"],
                ))
        
        # === 7. Memory Recall Block ===
        if "memory_recall" in config["required"] or "memory_recall" in config["optional"]:
            if memory_context:
                blocks.append(ContextBlock(
                    block_type="memory_recall",
                    content=memory_context,
                    priority=60,
                    required="memory_recall" in config["required"],
                ))
        
        # === 8. Tool Result Block ===
        if "tool_result" in config["required"] or "tool_result" in config["optional"]:
            if tool_results:
                tool_text = "\n\n".join(tool_results)
                blocks.append(ContextBlock(
                    block_type="tool_result",
                    content=tool_text,
                    priority=65,
                    required="tool_result" in config["required"],
                ))
        
        # 按优先级排序
        blocks.sort(key=lambda b: b.priority, reverse=True)
        
        return blocks
    
    def build_messages(
        self,
        blocks: list[ContextBlock],
        history: list[dict[str, str]],
        user_message: str,
        max_tokens: int = 4000,
    ) -> list[dict[str, str]]:
        """将上下文块转换为 LLM 消息列表。
        
        策略：
        - 先放 required blocks
        - 再放 optional blocks（按优先级）
        - 最后放 history + user_message
        """
        messages = []
        current_tokens = 0
        
        # 系统提示词（合并所有 block）
        system_parts = []
        
        # 先加 required
        for block in blocks:
            if block.required:
                system_parts.append(block.content)
        
        # 再加 optional（如果空间允许）
        for block in blocks:
            if not block.required:
                system_parts.append(block.content)
        
        system_content = "\n\n".join(system_parts)
        if system_content:
            messages.append({
                "role": "system",
                "content": system_content,
            })
        
        # 对话历史（最近 8 轮）
        for msg in history[-8:]:
            messages.append(msg)
        
        # 当前用户消息
        messages.append({
            "role": "user",
            "content": user_message,
        })
        
        return messages
    
    def _build_policy_text(self, policy: Any) -> str:
        """构建策略文本。"""
        if not policy:
            return ""
        
        parts = ["【本轮策略】"]
        parts.append(f"目标：{policy.goal}")
        
        if policy.pull_main_thread:
            parts.append(f"注意：建议拉回主线 {policy.main_thread_id}")
        
        if not policy.allow_humor:
            parts.append("语气：认真，不玩梗")
        
        if not policy.allow_advice:
            parts.append("策略：先陪伴，不给建议")
        
        if policy.max_questions == 0:
            parts.append("限制：不要提问")
        
        if policy.response_length == "short":
            parts.append("长度：简短回复")
        
        return "\n".join(parts)
    
    def _build_relationship_text(self, relationship: dict[str, Any]) -> str:
        """构建关系画像文本。"""
        if not relationship:
            return ""
        
        parts = ["【关系画像】"]
        
        comfort = relationship.get("comfort_style", "balanced")
        parts.append(f"接话风格：{comfort}")
        
        humor = relationship.get("humor_mode", "light")
        parts.append(f"梗感：{humor}")
        
        advice = relationship.get("advice_threshold", 0.5)
        parts.append(f"建议接受度：{advice:.1f}")
        
        return "\n".join(parts)
    
    def _build_thread_text(self, thread: dict[str, Any], is_active: bool = True) -> str:
        """构建主线文本。"""
        if not thread:
            return ""
        
        prefix = "【当前主线】" if is_active else "【后台主线】"
        name = thread.get("name", "未知")
        urgency = thread.get("urgency", 0.5)
        resume = thread.get("resume_tokens", "")
        
        parts = [prefix]
        parts.append(f"主题：{name}")
        if urgency > 0.7:
            parts.append(f"紧急度：高")
        elif urgency > 0.4:
            parts.append(f"紧急度：中")
        
        if resume:
            parts.append(f"背景：{resume[:100]}")
        
        return "\n".join(parts)
    
    def _build_background_threads_text(self, threads: list[dict[str, Any]]) -> str:
        """构建后台主线文本。"""
        if not threads:
            return ""
        
        parts = ["【后台主线】"]
        for thread in threads:
            name = thread.get("name", "未知")
            urgency = thread.get("urgency", 0)
            parts.append(f"- {name}(紧急度:{urgency:.1f})")
        
        return "\n".join(parts)