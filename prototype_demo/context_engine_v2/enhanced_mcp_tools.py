"""Enhanced MCP Tools - 增强版工具层

不是假数据，是半自动工具：
1. 外卖：生成搜索词 + 推荐 + 下单清单（用户复制到外卖 APP）
2. 课表：管理 + 提醒 + 冲突检测
3. 消费：记录 + 分析 + 预算建议
4. 音乐：保留原有歌单功能

设计原则：
- 做不到真实下单，但做到"帮用户准备好一切，只剩付款"
- 所有工具输出要自然融入对话，不是冷冰冰的列表
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Any

from prototype_demo.llm_client import get_llm_client


# ============ 外卖工具 ============

FOOD_DB = {
    "麻辣烫": {"type": "热食", "budget": "15-25", "calories": "500-700", "speed": "15min"},
    "螺蛳粉": {"type": "热食", "budget": "15-20", "calories": "600-800", "speed": "20min"},
    "奶茶": {"type": "饮品", "budget": "12-20", "calories": "300-500", "speed": "10min"},
    "炸鸡": {"type": "炸物", "budget": "20-35", "calories": "800-1200", "speed": "25min"},
    "汉堡": {"type": "快餐", "budget": "15-30", "calories": "600-900", "speed": "20min"},
    "披萨": {"type": "西餐", "budget": "30-60", "calories": "1000-1500", "speed": "30min"},
    "寿司": {"type": "日料", "budget": "25-50", "calories": "400-700", "speed": "25min"},
    "沙拉": {"type": "轻食", "budget": "20-35", "calories": "300-500", "speed": "15min"},
    "粥": {"type": "热食", "budget": "10-18", "calories": "200-400", "speed": "15min"},
    "烧烤": {"type": "夜宵", "budget": "30-80", "calories": "1000+", "speed": "35min"},
    "面条": {"type": "面食", "budget": "12-20", "calories": "500-700", "speed": "15min"},
    "饺子": {"type": "面食", "budget": "15-25", "calories": "500-800", "speed": "20min"},
}


def generate_food_order(
    user_message: str,
    budget: str = "",
    preference: str = "",
    time_constraint: str = "",
) -> dict[str, Any]:
    """生成外卖推荐和下单清单"""
    
    # 解析用户需求
    msg_lower = user_message.lower()
    
    # 检测食物类型
    detected_foods = []
    for food, info in FOOD_DB.items():
        if food in msg_lower:
            detected_foods.append((food, info))
    
    # 如果没有明确提到，根据时间/情境推荐
    if not detected_foods:
        hour = datetime.now().hour
        if 6 <;= hour <; 10:
            detected_foods = [("粥", FOOD_DB["粥"]), ("面条", FOOD_DB["面条"])]
        elif 10 <;= hour <; 14:
            detected_foods = [("麻辣烫", FOOD_DB["麻辣烫"]), ("汉堡", FOOD_DB["汉堡"])]
        elif 14 <;= hour <; 18:
            detected_foods = [("奶茶", FOOD_DB["奶茶"]), ("沙拉", FOOD_DB["沙拉"])]
        elif 18 <;= hour <; 22:
            detected_foods = [("螺蛳粉", FOOD_DB["螺蛳粉"]), ("炸鸡", FOOD_DB["炸鸡"])]
        else:
            detected_foods = [("烧烤", FOOD_DB["烧烤"]), ("炸鸡", FOOD_DB["炸鸡"])]
    
    # 生成推荐
    recommendations = []
    for food, info in detected_foods[:3]:
        rec = {
            "name": food,
            "budget": info["budget"],
            "calories": info["calories"],
            "speed": info["speed"],
            "search_terms": f"{food} 外卖",
            "order_tips": _generate_order_tips(food),
        }
        recommendations.append(rec)
    
    # 生成下单清单模板
    primary = recommendations[0] if recommendations else {"name": "外卖"}
    order_list = _generate_order_list(primary["name"])
    
    return {
        "tool": "food_recommendation",
        "recommendations": recommendations,
        "primary_choice": primary,
        "search_terms": f"{primary['name']} 外卖 {budget or ''}",
        "order_list": order_list,
        "platforms": ["美团外卖", "饿了么"],
        "formatted_context": _format_food_result(recommendations, primary, order_list),
    }


def _generate_order_tips(food: str) -> str:
    """生成点餐技巧"""
    tips = {
        "麻辣烫": "多选蔬菜少选丸子，粉条选一种就行",
        "螺蛳粉": "微辣起步，加炸蛋是灵魂",
        "奶茶": "三分糖+去冰，不容易腻",
        "炸鸡": "选套餐比单点划算，配可乐解腻",
        "汉堡": "双层肉堡容易腻，单层+小食更好",
        "披萨": "8寸够1人，12寸够2-3人，别点多",
        "沙拉": "选有鸡胸肉的，纯菜不饱",
        "粥": "咸粥比甜粥顶饱，配个小菜",
        "烧烤": "肉素搭配，别全点肉容易腻",
        "面条": "选有配菜的，光面不饱",
        "饺子": "15-20个够吃，蘸醋解腻",
    }
    return tips.get(food, "看评分选店，4.5分以上比较稳")


def _generate_order_list(food: str) -> list[dict[str, str]]:
    """生成示例下单清单"""
    lists = {
        "麻辣烫": [
            {"item": "蔬菜拼盘", "quantity": "1份", "note": "菠菜+生菜+金针菇"},
            {"item": "土豆片", "quantity": "1份", "note": ""},
            {"item": "粉丝/红薯粉", "quantity": "1份", "note": "二选一"},
            {"item": "午餐肉", "quantity": "2片", "note": ""},
            {"item": "微辣汤底", "quantity": "1份", "note": ""},
        ],
        "螺蛳粉": [
            {"item": "招牌螺蛳粉", "quantity": "1份", "note": "微辣"},
            {"item": "炸蛋", "quantity": "1个", "note": "必加"},
            {"item": "腐竹", "quantity": "1份", "note": ""},
        ],
        "奶茶": [
            {"item": "珍珠奶茶", "quantity": "1杯", "note": "三分糖去冰"},
            {"item": "芋圆", "quantity": "1份", "note": "加料"},
        ],
        "炸鸡": [
            {"item": "炸鸡套餐", "quantity": "1份", "note": "选鸡翅+鸡腿组合"},
            {"item": "可乐", "quantity": "1杯", "note": "中杯就行"},
            {"item": "薯条", "quantity": "1份", "note": "小份"},
        ],
    }
    return lists.get(food, [{"item": f"{food}套餐", "quantity": "1份", "note": "看评价选"}])


def _format_food_result(recommendations: list[dict], primary: dict, order_list: list[dict]) -> str:
    """格式化食物推荐结果"""
    result = f"""【外卖推荐】

给你选了几个：
"""
    for i, rec in enumerate(recommendations[:2], 1):
        result += f"{i}. {rec['name']}（{rec['budget']}元，{rec['speed']}）\n"
    
    result += f"""
建议选：{primary['name']}
点餐技巧：{_generate_order_tips(primary['name'])}

搜索词："{primary['name']} 外卖"

下单清单：
"""
    for item in order_list:
        result += f"- {item['item']} x {item['quantity']}"
        if item.get("note"):
            result += f" （{item['note']}）"
        result += "\n"
    
    result += "\n复制搜索词到美团/饿了么就行。"
    return result


# ============ 课表工具 ============

class ScheduleManager:
    """课表管理器（内存存储）"""
    
    _schedules: dict[str, list[dict[str, Any]]] = {}
    
    @classmethod
    def add_course(cls, user_id: str, course: dict[str, Any]):
        """添加课程"""
        if user_id not in cls._schedules:
            cls._schedules[user_id] = []
        cls._schedules[user_id].append(course)
    
    @classmethod
    def get_today_courses(cls, user_id: str) -> list[dict[str, Any]]:
        """获取今日课程"""
        courses = cls._schedules.get(user_id, [])
        today = datetime.now().strftime("%A")
        day_map = {
            "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三",
            "Thursday": "周四", "Friday": "周五", "Saturday": "周六", "Sunday": "周日",
        }
        today_cn = day_map.get(today, "今天")
        
        return [c for c in courses if today_cn in c.get("days", [])]
    
    @classmethod
    def check_conflicts(cls, user_id: str) -> list[dict[str, Any]]:
        """检查时间冲突"""
        courses = cls._schedules.get(user_id, [])
        conflicts = []
        
        for i, c1 in enumerate(courses):
            for c2 in courses[i+1:]:
                # 简单检查：同一天且时间重叠
                days1 = set(c1.get("days", []))
                days2 = set(c2.get("days", []))
                if days1 & days2:
                    # 时间重叠检查（简化版）
                    time1 = c1.get("time", "")
                    time2 = c2.get("time", "")
                    if time1 and time2 and time1 == time2:
                        conflicts.append({
                            "course1": c1.get("name", ""),
                            "course2": c2.get("name", ""),
                            "day": list(days1 & days2)[0],
                            "time": time1,
                        })
        
        return conflicts


def manage_schedule(
    action: str,
    user_id: str,
    course_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """管理课表"""
    
    if action == "add":
        if course_data:
            ScheduleManager.add_course(user_id, course_data)
            return {
                "tool": "schedule",
                "action": "add",
                "success": True,
                "formatted_context": f"已添加课程：{course_data.get('name', '')} ({course_data.get('time', '')})",
            }
    
    elif action == "today":
        courses = ScheduleManager.get_today_courses(user_id)
        if courses:
            result = "今天有：\n"
            for c in courses:
                result += f"- {c.get('time', '')} {c.get('name', '')} @ {c.get('location', '待定')}\n"
        else:
            result = "今天没课，自由安排。"
        
        return {
            "tool": "schedule",
            "action": "today",
            "courses": courses,
            "formatted_context": result,
        }
    
    elif action == "conflicts":
        conflicts = ScheduleManager.check_conflicts(user_id)
        if conflicts:
            result = "发现时间冲突：\n"
            for c in conflicts:
                result += f"- {c['day']} {c['time']}: {c['course1']} vs {c['course2']}\n"
        else:
            result = "没时间冲突，课表 OK。"
        
        return {
            "tool": "schedule",
            "action": "conflicts",
            "conflicts": conflicts,
            "formatted_context": result,
        }
    
    return {"tool": "schedule", "action": action, "formatted_context": ""}


# ============ 消费工具 ============

class ExpenseTracker:
    """消费追踪器"""
    
    _expenses: dict[str, list[dict[str, Any]]] = {}
    
    @classmethod
    def add_expense(cls, user_id: str, amount: float, category: str, note: str = ""):
        """记录消费"""
        if user_id not in cls._expenses:
            cls._expenses[user_id] = []
        
        cls._expenses[user_id].append({
            "amount": amount,
            "category": category,
            "note": note,
            "date": datetime.now().isoformat(),
        })
    
    @classmethod
    def get_summary(cls, user_id: str, days: int = 7) -> dict[str, Any]:
        """获取消费摘要"""
        expenses = cls._expenses.get(user_id, [])
        cutoff = datetime.now() - timedelta(days=days)
        
        recent = [e for e in expenses if datetime.fromisoformat(e["date"]) >; cutoff]
        
        if not recent:
            return {"total": 0, "by_category": {}, "formatted_context": "最近没记录消费。"}
        
        total = sum(e["amount"] for e in recent)
        by_category: dict[str, float] = {}
        for e in recent:
            cat = e["category"]
            by_category[cat] = by_category.get(cat, 0) + e["amount"]
        
        # 生成分析
        result = f"""最近{days}天消费：
总支出：{total:.0f}元

分类：
"""
        for cat, amt in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
            pct = amt / total * 100
            result += f"- {cat}: {amt:.0f}元（{pct:.0f}%）\n"
        
        # 简单建议
        if by_category.get("餐饮", 0) > total * 0.5:
            result += "\n餐饮占比过半，可以考虑自己做饭或吃食堂。"
        elif by_category.get("娱乐", 0) > total * 0.3:
            result += "\n娱乐支出不少，注意预算哦。"
        
        return {
            "total": total,
            "by_category": by_category,
            "formatted_context": result,
        }


def track_expense(
    user_id: str,
    action: str,
    amount: float = 0,
    category: str = "",
    note: str = "",
) -> dict[str, Any]:
    """追踪消费"""
    
    if action == "add":
        ExpenseTracker.add_expense(user_id, amount, category, note)
        return {
            "tool": "expense",
            "action": "add",
            "formatted_context": f"记录了：{category} {amount}元 ({note})",
        }
    
    elif action == "summary":
        summary = ExpenseTracker.get_summary(user_id)
        return {
            "tool": "expense",
            "action": "summary",
            "summary": summary,
            "formatted_context": summary["formatted_context"],
        }
    
    return {"tool": "expense", "action": action, "formatted_context": ""}


# ============ 主入口 ============

def execute_skill_mcp(skill_id: str, user_message: str, memory_context: dict[str, Any]) -> dict[str, Any]:
    """执行 MCP 工具"""
    
    user_id = memory_context.get("user_id", "demo-user")
    
    # 音乐相关（保留原有功能）
    if skill_id in ("radio_dj", "playlist_builder"):
        return _execute_music_skill(skill_id, user_message, memory_context)
    
    # 外卖
    if skill_id == "food_picker" or any(kw in user_message for kw in ["外卖", "吃什么", "饿了", "订餐"]):
        return generate_food_order(user_message)
    
    # 课表
    if skill_id == "campus_schedule" or any(kw in user_message for kw in ["课表", "今天有什么课", "课程"]):
        return manage_schedule("today", user_id)
    
    # 消费
    if skill_id == "expense_tracker" or any(kw in user_message for kw in ["花了", "消费", "记账", "预算"]):
        return track_expense(user_id, "summary")
    
    return {"tool_calls": [], "tool_results": [], "formatted_context": ""}


def _execute_music_skill(skill_id: str, user_message: str, memory_context: dict[str, Any]) -> dict[str, Any]:
    """执行音乐技能（保留原有逻辑）"""
    # 这里导入原有逻辑
    import sys
    sys.path.insert(0, '/Users/niuniu/Downloads/quickstart/prototype_demo')
    from mcp_tools import execute_skill_mcp as old_execute
    return old_execute(skill_id, user_message, memory_context)
