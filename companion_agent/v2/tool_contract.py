"""
Tool Contract

工具系统正规化定义。
每个工具统一返回：
- intent: 工具意图
- inputs: 输入参数
- result: 执行结果
- confidence: 置信度
- user_visible_summary: 用户可见摘要
- follow_up_options: 后续选项

工具分类：
- reasoning tools: 排序、分析、建议
- lookup tools: 天气、课程、地图、店铺
- action tools: 下单、提醒、日历、消息草稿
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolResult:
    """工具执行结果规范。"""
    
    # 工具信息
    tool_name: str
    tool_type: Literal["reasoning", "lookup", "action"]
    
    # 执行状态
    success: bool
    confidence: float  # 0-1
    
    # 结果数据
    result: dict[str, Any] = field(default_factory=dict)
    
    # 用户可见摘要（简洁、口语化）
    user_visible_summary: str = ""
    
    # 后续选项
    follow_up_options: list[str] = field(default_factory=list)
    
    # 是否需要确认（action 工具必须）
    requires_confirmation: bool = False
    
    # 错误信息
    error: str = ""
    
    # 原始查询
    original_query: str = ""


@dataclass
class ToolContract:
    """工具契约定义。"""
    
    name: str
    description: str
    tool_type: Literal["reasoning", "lookup", "action"]
    
    # 输入参数定义
    input_schema: dict[str, Any] = field(default_factory=dict)
    
    # 输出格式
    output_schema: dict[str, Any] = field(default_factory=dict)
    
    # 是否需要用户确认（action 工具）
    requires_confirmation: bool = False
    
    # 示例用法
    examples: list[dict[str, Any]] = field(default_factory=list)


# === 预定义工具契约 ===

DIET_RECOMMEND_TOOL = ToolContract(
    name="diet_recommend",
    description="推荐当前时段吃什么",
    tool_type="reasoning",
    input_schema={
        "time_of_day": {"type": "string", "enum": ["早餐", "午餐", "晚餐", "夜宵"]},
        "mood": {"type": "string", "enum": ["happy", "sad", "tired", "neutral"]},
        "budget_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "location": {"type": "string"},
    },
    output_schema={
        "recommendation": {"type": "string"},
        "reason": {"type": "string"},
        "search_keywords": {"type": "string"},
        "alternatives": {"type": "array"},
        "estimated_price": {"type": "number"},
    },
)

STUDY_PLAN_TOOL = ToolContract(
    name="study_plan",
    description="制定学习计划或排序任务",
    tool_type="reasoning",
    input_schema={
        "tasks": {"type": "array", "items": {"type": "string"}},
        "days_left": {"type": "number"},
        "time_available": {"type": "number"},
    },
    output_schema={
        "sorted_tasks": {"type": "array"},
        "priority_scores": {"type": "object"},
        "next_action": {"type": "string"},
    },
)

REPLY_ADVICE_TOOL = ToolContract(
    name="reply_advice",
    description="给聊天回复建议",
    tool_type="reasoning",
    input_schema={
        "message": {"type": "string"},
        "relationship_stage": {"type": "string", "enum": ["crush", "dating", "friend", "ex"]},
    },
    output_schema={
        "options": {"type": "array"},
        "explanations": {"type": "array"},
        "stage_guidance": {"type": "string"},
    },
)

# Action 工具示例（未来接入真实服务）
ORDER_FOOD_TOOL = ToolContract(
    name="order_food",
    description="生成外卖搜索词和下单清单",
    tool_type="action",
    requires_confirmation=True,
    input_schema={
        "food_name": {"type": "string"},
        "budget": {"type": "number"},
        "location": {"type": "string"},
    },
    output_schema={
        "search_keywords": {"type": "string"},
        "platform_link": {"type": "string"},
        "order_list": {"type": "array"},
    },
)

SCHEDULE_REMINDER_TOOL = ToolContract(
    name="schedule_reminder",
    description="设置提醒",
    tool_type="action",
    requires_confirmation=True,
    input_schema={
        "task": {"type": "string"},
        "time": {"type": "string"},
    },
    output_schema={
        "reminder_set": {"type": "boolean"},
        "reminder_time": {"type": "string"},
    },
)


class ToolRegistry:
    """工具注册表。"""
    
    def __init__(self):
        self._tools: dict[str, ToolContract] = {}
        self._register_builtin_tools()
    
    def _register_builtin_tools(self) -> None:
        """注册内置工具。"""
        self.register(DIET_RECOMMEND_TOOL)
        self.register(STUDY_PLAN_TOOL)
        self.register(REPLY_ADVICE_TOOL)
        self.register(ORDER_FOOD_TOOL)
        self.register(SCHEDULE_REMINDER_TOOL)
    
    def register(self, tool: ToolContract) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> ToolContract | None:
        """获取工具定义。"""
        return self._tools.get(name)
    
    def list_tools(self, tool_type: str | None = None) -> list[ToolContract]:
        """列出工具。"""
        tools = list(self._tools.values())
        if tool_type:
            tools = [t for t in tools if t.tool_type == tool_type]
        return tools
    
    def validate_input(self, tool_name: str, inputs: dict[str, Any]) -> tuple[bool, str]:
        """验证工具输入。"""
        tool = self._tools.get(tool_name)
        if not tool:
            return False, f"Tool '{tool_name}' not found"
        
        schema = tool.input_schema
        for key, config in schema.items():
            if key not in inputs:
                return False, f"Missing required field: {key}"
            
            # 类型检查
            if "enum" in config and inputs[key] not in config["enum"]:
                return False, f"Invalid value for {key}: {inputs[key]}"
        
        return True, ""


# 全局工具注册表
_global_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表。"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry
