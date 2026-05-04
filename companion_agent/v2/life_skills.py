"""
Life Skills v2 - 本科生生活能力包

提供真实有用的生活工具能力：
- 饮食分析：吃饭规律、热量粗估、预算建议
- 学习规划：考试前微计划、DDL排序
- 社交恋爱：聊天回复建议、邀约判断、边界感
- 校园生活：食堂选择、通勤、选课
- 情绪陪伴：不强行建议，先陪再转行动

注意：这些不是真实API调用，而是结构化推理+实用建议。
如果未来接入真实API，只需替换实现层。
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from dataclasses import dataclass, field
from typing import Any

from .skill_contracts import SkillInput, SkillOutput


@dataclass
@dataclass
class LifeAdvice:
    """生活建议结果。"""
    category: str
    advice: str
    action_items: list[str]
    tools_used: list[str]


class DietSkill:
    """饮食建议技能（做深版）。"""
    
    CAMPUS_FOODS = {
        "早餐": [
            {"name": "包子+豆浆", "reason": "经典搭配，热乎顶饱", "price": 8, "search": "包子豆浆"},
            {"name": "煎饼果子", "reason": "碳水炸弹，吃完有劲", "price": 10, "search": "煎饼果子"},
            {"name": "粥+鸡蛋", "reason": "清淡好消化", "price": 7, "search": "粥 鸡蛋"},
            {"name": "面包+牛奶", "reason": "边走边吃，不耽误上课", "price": 12, "search": "面包牛奶"},
        ],
        "午餐": [
            {"name": "食堂二楼自选", "reason": "便宜管饱，种类多", "price": 15, "search": "食堂自选"},
            {"name": "麻辣香锅", "reason": "辣得爽，米饭管够", "price": 25, "search": "麻辣香锅"},
            {"name": "牛肉面", "reason": "汤面热乎，冬天首选", "price": 18, "search": "牛肉面"},
            {"name": "黄焖鸡", "reason": "肉多下饭", "price": 22, "search": "黄焖鸡"},
            {"name": "轻食沙拉", "reason": "如果最近吃太油", "price": 28, "search": "轻食沙拉"},
        ],
        "晚餐": [
            {"name": "螺蛳粉", "reason": "想吃点有味的", "price": 20, "search": "螺蛳粉"},
            {"name": "烧烤", "reason": "和朋友一起", "price": 40, "search": "烧烤"},
            {"name": "火锅", "reason": "犒劳自己", "price": 60, "search": "火锅"},
            {"name": "炸鸡", "reason": "罪恶但快乐", "price": 25, "search": "炸鸡"},
            {"name": "炒饭", "reason": "简单省事", "price": 15, "search": "炒饭"},
            {"name": "粥+小菜", "reason": "胃不舒服时", "price": 12, "search": "粥"},
        ],
        "夜宵": [
            {"name": "烤串", "reason": "深夜罪恶", "price": 30, "search": "烤串"},
            {"name": "炸鸡", "reason": "追剧标配", "price": 25, "search": "炸鸡"},
            {"name": "奶茶", "reason": "甜的解压", "price": 18, "search": "奶茶"},
            {"name": "泡面", "reason": "最便宜最快", "price": 5, "search": "泡面"},
        ],
    }
    
    BUDGET_LEVELS = {
        "low": {"range": "15-25元/天", "style": "食堂为主，偶尔外卖"},
        "medium": {"range": "25-40元/天", "style": "食堂+外卖混合"},
        "high": {"range": "40-60元/天", "style": "经常吃好的"},
    }
    
    # 克制干预触发词
    RESTRAINT_TRIGGERS = {
        "奶茶": {"limit": "一周最多2杯", "reason": "糖分高，晚上喝容易失眠"},
        "夜宵": {"limit": "一周最多2次", "reason": "睡前吃影响睡眠和消化"},
        "炸鸡": {"limit": "一周最多1次", "reason": "油腻，皮肤和胃会抗议"},
        "烧烤": {"limit": "一周最多1次", "reason": "重油重盐，吃完多喝水"},
    }
    
    async def recommend(
        self,
        time_of_day: str,
        preferences: dict[str, Any],
        budget_level: str = "medium",
        mood: str = "neutral",
        location: str = "",  # 食堂/宿舍/外面
    ) -> LifeAdvice:
        """推荐吃什么（带推荐理由和搜索词）。"""
        
        time_key = time_of_day if time_of_day in self.CAMPUS_FOODS else "午餐"
        options = self.CAMPUS_FOODS[time_key]
        
        # 根据预算过滤
        budget_map = {"low": 20, "medium": 30, "high": 100}
        max_price = budget_map.get(budget_level, 30)
        options = [o for o in options if o["price"] <= max_price] or options
        
        # 根据心情调整
        if mood in ("sad", "tired"):
            comfort_names = ["麻辣香锅", "螺蛳粉", "炸鸡", "火锅", "烧烤", "奶茶"]
            comfort_options = [o for o in options if any(cf in o["name"] for cf in comfort_names)]
            if comfort_options:
                options = comfort_options
        
        # 根据地点调整
        if "宿舍" in location or "外卖" in location:
            # 优先外卖友好的
            options = [o for o in options if o["price"] >= 15] or options
        elif "食堂" in location:
            # 优先食堂有的
            options = [o for o in options if "食堂" in o["name"] or o["price"] < 20] or options
        
        # 选择主推荐 + 备选项
        if len(options) >= 2:
            selected = random.sample(options, min(3, len(options)))
        else:
            selected = options
        
        main = selected[0]
        alternatives = selected[1:]
        
        # 构建建议
        advice = f"""{time_key}推荐：{main['name']}
理由：{main['reason']}
预估：{main['price']}元

搜索词：{main['search']}
"""
        
        if alternatives:
            advice += "\n如果不想吃这个：\n"
            for alt in alternatives:
                advice += f"- {alt['name']}（{alt['reason']}，{alt['price']}元）\n"
        
        advice += f"\n预算参考：{self.BUDGET_LEVELS.get(budget_level, self.BUDGET_LEVELS['medium'])['range']}"
        
        return LifeAdvice(
            category="diet",
            advice=advice,
            action_items=[f"搜索：{main['search']}", "想吃就点，别纠结"],
            tools_used=["campus_food_db"],
        )
    
    async def analyze_routine(
        self,
        meal_history: list[dict[str, Any]],
    ) -> LifeAdvice:
        """分析饮食习惯（智能版）。"""
        
        if not meal_history:
            return LifeAdvice(
                category="diet_routine",
                advice="还没记录过饮食，先随便吃几天，我帮你看看规律。",
                action_items=["记录3天饮食"],
                tools_used=[],
            )
        
        # 分析最近7天
        recent = meal_history[-7:]
        
        # 统计
        breakfast_count = sum(1 for m in recent if "早" in m.get("time", ""))
        late_night_count = sum(1 for m in recent if "夜" in m.get("time", "") or "晚" in m.get("time", ""))
        takeout_count = sum(1 for m in recent if "外卖" in m.get("content", ""))
        
        # 识别高频食物
        food_keywords = ["奶茶", "炸鸡", "烧烤", "麻辣", "泡面"]
        food_counts = {}
        for m in recent:
            content = m.get("content", "")
            for food in food_keywords:
                if food in content:
                    food_counts[food] = food_counts.get(food, 0) + 1
        
        issues = []
        if breakfast_count < 3:
            issues.append("早餐吃得少，容易低血糖")
        if late_night_count > 3:
            issues.append("夜宵太频繁，影响睡眠")
        if takeout_count > 5:
            issues.append("外卖太多，钱包和胃都吃不消")
        
        # 识别过量食物
        over_consumed = [f for f, c in food_counts.items() if c >= 3]
        
        if issues or over_consumed:
            advice = "最近饮食观察：\n"
            for issue in issues:
                advice += f"- {issue}\n"
            if over_consumed:
                advice += f"- {', '.join(over_consumed)} 吃太多了\n"
            advice += "\n不用立刻改，下周注意一下就好。"
        else:
            advice = "最近饮食还挺规律的，继续保持。"
        
        return LifeAdvice(
            category="diet_routine",
            advice=advice,
            action_items=["包里常备小零食", "下周试试少点外卖"],
            tools_used=["meal_history_analysis"],
        )
    
    async def restraint_check(
        self,
        user_message: str,
        recent_meals: list[dict[str, Any]] = None,
    ) -> LifeAdvice:
        """克制干预：奶茶/夜宵/暴食场景的温和提醒。"""
        
        triggered = None
        for trigger, info in self.RESTRAINT_TRIGGERS.items():
            if trigger in user_message:
                triggered = (trigger, info)
                break
        
        if not triggered:
            return LifeAdvice(
                category="diet_restraint",
                advice="",
                action_items=[],
                tools_used=[],
            )
        
        food, info = triggered
        
        # 检查最近是否吃过
        recent_count = 0
        if recent_meals:
            recent_count = sum(1 for m in recent_meals[-7:] if food in m.get("content", ""))
        
        if recent_count >= 2:
            advice = f"""这周已经吃过{recent_count}次{food}了。

{info['limit']}。{info['reason']}。

这次想吃的话可以吃，但下次记得控制一下。不用愧疚，但要知情。"""
        else:
            advice = f"""想吃{food}？

{info['reason']}。

这次可以吃，但记住{info['limit']}。"""
        
        return LifeAdvice(
            category="diet_restraint",
            advice=advice,
            action_items=[f"如果点{food}，选小份", "吃完多喝水"],
            tools_used=["restraint_checker"],
        )


class StudySkill:
    """学习规划技能（微执行版）。"""
    
    async def plan_exam(
        self,
        days_left: int,
        subjects: list[str],
        energy_level: str = "medium",
    ) -> LifeAdvice:
        """考前规划。"""
        
        if days_left <= 0:
            return LifeAdvice(
                category="study",
                advice="今天就要考了？现在什么都别看新的，把之前的错题翻一遍，然后睡觉。",
                action_items=["看错题", "睡觉"],
                tools_used=[],
            )
        
        if days_left == 1:
            advice = """明天考，今天策略：
1. 只看重点和错题，不看新内容
2. 每科2小时，中间休息
3. 晚上11点前睡
4. 早餐吃好
"""
        elif days_left <= 3:
            advice = f"""还有{days_left}天，来得及：
1. 先抓分最多的章节（老师划的重点）
2. 每天每科3小时，不熬夜
3. 做两套往年题
4. 最后一天只看错题
"""
        elif days_left <= 7:
            advice = f"""还有{days_left}天，可以好好准备：
1. 列提纲，每天完成2-3章
2. 周末做模拟
3. 平时课后复习当天的
4. 不要堆到最后两天
"""
        else:
            advice = "时间充裕，先列个计划表，每周复习2-3次，考前一周密集。"
        
        return LifeAdvice(
            category="study",
            advice=advice,
            action_items=["列出重点章节", "找往年题"],
            tools_used=["study_planner"],
        )
    
    async def micro_plan(
        self,
        task: str,
        time_available: int,  # 分钟
    ) -> LifeAdvice:
        """微计划：用户说学不进去时的25分钟启动计划。"""
        
        if time_available < 25:
            advice = f"""只有{time_available}分钟？那只做一件事：
打开书/电脑，看5分钟。看不进去就算了，至少开了个头。
"""
        else:
            cycles = time_available // 30  # 25分钟工作 + 5分钟休息
            advice = f"""{time_available}分钟，分{cycles}轮：
- 每轮25分钟只做最简单的事（降低启动门槛）
- 休息5分钟：刷手机、喝水、站起来
- 重点是"开始"，不是"完成"

如果第一轮结束不想继续，今天就到这，你已经赢了。
"""
        
        return LifeAdvice(
            category="study",
            advice=advice,
            action_items=[
                "设25分钟闹钟",
                "找出任务中最简单的那部分",
                "只做那部分，别想结果"
            ],
            tools_used=["pomodoro_adapter"],
        )
    
    def _parse_natural_task(self, text: str) -> dict[str, Any]:
        """从自然语言解析结构化任务。"""
        import re
        
        task = {"name": text, "deadline_days": 7, "difficulty": 3, "estimated_hours": 2}
        
        # 解析DDL
        ddl_patterns = [
            (r'(\d+)天后', lambda m: int(m.group(1))),
            (r'下周[一二三四五六日]', lambda m: 7),
            (r'明天', lambda m: 1),
            (r'后天', lambda m: 2),
            (r'这周末', lambda m: 5),
        ]
        for pattern, extractor in ddl_patterns:
            match = re.search(pattern, text)
            if match:
                task["deadline_days"] = extractor(match)
                break
        
        # 解析难度关键词
        if any(kw in text for kw in ["难", "复杂", "大", "项目", "论文"]):
            task["difficulty"] = 4
        elif any(kw in text for kw in ["简单", "小", "轻松", "快"]):
            task["difficulty"] = 2
        
        # 解析预估时间
        time_patterns = [
            (r'(\d+)小时', lambda m: int(m.group(1))),
            (r'(\d+)分钟', lambda m: max(1, int(m.group(1)) / 60)),
        ]
        for pattern, extractor in time_patterns:
            match = re.search(pattern, text)
            if match:
                task["estimated_hours"] = extractor(match)
                break
        
        # 清理任务名
        task["name"] = text[:30]  # 截取前30字
        
        return task
    
    async def parse_and_sort_tasks(
        self,
        user_message: str,
    ) -> LifeAdvice:
        """解析自然语言中的多个任务并排序。"""
        
        # 简单解析：按行分割，每行一个任务
        lines = [line.strip() for line in user_message.split('\n') if line.strip()]
        lines = [line for line in lines if any(kw in line for kw in ["ddl", "deadline", "截止", "交", "做", "写", "考"])]
        
        if not lines:
            return LifeAdvice(
                category="study",
                advice="我没找到明确的任务，你可以列出来，比如：\n- 明天交高数作业\n- 下周三presentation\n- 这周末复习物理",
                action_items=["列出任务和截止时间"],
                tools_used=[],
            )
        
        # 解析每个任务
        tasks = [self._parse_natural_task(line) for line in lines]
        
        # 排序算法：紧急度 × 重要度
        # 紧急度 = 1 / (deadline_days + 1)
        # 重要度 = difficulty × estimated_hours
        for task in tasks:
            urgency = 1.0 / (task["deadline_days"] + 1)
            importance = task["difficulty"] * task["estimated_hours"]
            task["priority_score"] = urgency * importance * 10
        
        sorted_tasks = sorted(tasks, key=lambda t: -t["priority_score"])
        
        # 构建输出
        advice = "按优先级排序：\n\n"
        for i, task in enumerate(sorted_tasks[:5], 1):
            days = task["deadline_days"]
            hours = task["estimated_hours"]
            diff = "⭐" * task["difficulty"]
            advice += f"{i}. {task['name']}\n"
            advice += f"   还有{days}天 | 预估{hours}小时 | 难度{diff}\n"
            if i == 1:
                advice += f"   → 建议先做这个，最急\n"
            advice += "\n"
        
        advice += "现在这一小时：只做排第一的那个任务的最简单部分。"
        
        return LifeAdvice(
            category="study",
            advice=advice,
            action_items=[
                f"开始做：{sorted_tasks[0]['name']}",
                "设25分钟闹钟",
                "完成后再看下一个"
            ],
            tools_used=["task_parser", "ddl_sorter"],
        )
    
    async def sort_ddl(
        self,
        tasks: list[dict[str, Any]],
    ) -> LifeAdvice:
        """DDL排序（兼容旧接口）。"""
        
        if not tasks:
            return LifeAdvice(
                category="study",
                advice="没有待办事项，享受这片刻的自由。",
                action_items=[],
                tools_used=[],
            )
        
        # 按紧急度和难度排序
        sorted_tasks = sorted(tasks, key=lambda t: (
            t.get("deadline_days", 999),
            -t.get("difficulty", 3),
        ))
        
        advice = "按这个顺序做：\n"
        for i, task in enumerate(sorted_tasks[:5], 1):
            name = task.get("name", "未知任务")
            days = task.get("deadline_days", "?")
            advice += f"{i}. {name}（还有{days}天）\n"
        
        advice += "\n先做最急的那个，做完一个再说下一个。"
        
        return LifeAdvice(
            category="study",
            advice=advice,
            action_items=[f"开始做{sorted_tasks[0].get('name', '第一个任务')}"],
            tools_used=["ddl_sorter"],
        )


class SocialSkill:
    """社交恋爱建议技能（做细版）。"""
    
    # 回复策略库（带解释）
    REPLY_STRATEGIES = {
        "在干嘛": {
            "options": [
                {"text": "在刷题，但被你消息打断了", "why": "暗示对方重要到能打断你，略带暧昧"},
                {"text": "刚在发呆，现在在想怎么回你", "why": "真诚但不卑微，把对方拉进你的思绪"},
                {"text": "在忙，但看到你的消息就停下来了", "why": "表达重视，但不显得一直在等"},
            ],
            "tip": "不要秒回，等几分钟再回"
        },
        "吃了吗": {
            "options": [
                {"text": "还没，正纠结吃什么", "why": "抛出话题，自然延续对话"},
                {"text": "吃了，但看到你消息又饿了", "why": "轻微撩，但不过度"},
                {"text": "刚吃完，你呢", "why": "简单接话，适合关系初期"},
            ],
            "tip": "如果想约，可以说'要不要一起'"
        },
        "晚安": {
            "options": [
                {"text": "晚安，好梦", "why": "温暖但不越界，适合任何阶段"},
                {"text": "这么早？我还想再聊会儿", "why": "表达不舍，但要对方也感兴趣才用"},
                {"text": "嗯，明天聊", "why": "简洁收尾，不过度热情"},
            ],
            "tip": "如果对方主动说晚安，不要追问"
        },
        "？": {
            "options": [
                {"text": "你猜？", "why": "调皮，拉近距离"},
                {"text": "这是个好问题，容我想想", "why": "认真但不敷衍"},
                {"text": "你觉得呢？", "why": "把话题抛回去，适合不想答的时候"},
            ],
            "tip": "问号太多时，选最简短的那个"
        },
    }
    
    async def reply_advice(
        self,
        message_from_other: str,
        context: str = "",
        relationship_stage: str = "crush",
    ) -> LifeAdvice:
        """给聊天回复建议（带解释）。"""
        
        msg = message_from_other.lower()
        
        # 匹配场景
        strategy = None
        for key, val in self.REPLY_STRATEGIES.items():
            if key in msg:
                strategy = val
                break
        
        if not strategy:
            # 通用策略
            strategy = {
                "options": [
                    {"text": "继续这个话题，分享一个相关的事", "why": "延续对话，展示你的经历"},
                    {"text": "轻微调侃一下", "why": "增加趣味性，拉近距离"},
                    {"text": "问一个相关问题", "why": "表现兴趣，但不查户口"},
                ],
                "tip": "不要只回表情包，至少带一句文字"
            }
        
        # 根据关系阶段调整建议
        stage_guidance = {
            "crush": "不要秒回，不要发小作文，保持神秘",
            "dating": "可以稍微甜一点，但不要油腻",
            "friend": "随意就好，不要过度解读",
            "ex": "简短礼貌，不要回忆过去",
        }
        
        advice = f"""对方说：{message_from_other}

你可以选：
"""
        for i, opt in enumerate(strategy["options"], 1):
            advice += f"{i}. {opt['text']}\n"
            advice += f"   → 为什么：{opt['why']}\n\n"
        
        advice += f"【阶段提示】{stage_guidance.get(relationship_stage, '自然就好')}\n"
        advice += f"【通用技巧】{strategy['tip']}"
        
        return LifeAdvice(
            category="social",
            advice=advice,
            action_items=["选一条回复", "等几分钟再回"],
            tools_used=["reply_suggester"],
        )
    
    async def date_judgment(
        self,
        situation: str,
    ) -> LifeAdvice:
        """邀约判断。"""
        
        advice = ""
        if "第一次" in situation or "刚认识" in situation:
            advice = """第一次邀约：
- 选白天、公共场所（咖啡馆、图书馆、食堂）
- 不要太正式，"一起去xx"比"约你出去"轻松
- 给对方留退路，"你要是忙就算了"
- 时间控制在2小时内
"""
        elif "表白" in situation or "喜欢" in situation:
            advice = """表白前：
- 先确认对方对你有好感（会主动找你、回消息快、愿意单独出来）
- 不要在微信上表白
- 准备接受任何答案
- 如果被拒，给自己一周缓冲，不要追问为什么
"""
        else:
            advice = "具体情况具体分析，你先说说更多细节？"
        
        return LifeAdvice(
            category="social",
            advice=advice,
            action_items=["评估对方信号"],
            tools_used=["date_advisor"],
        )
    
    async def rejection_advice(
        self,
        situation: str,
        relationship_stage: str = "crush",
    ) -> LifeAdvice:
        """拒绝话术建议。"""
        
        # 拒绝话术库
        rejections = {
            "邀约": {
                "soft": [
                    {"text": "这周有点忙，下次吧", "why": "留有余地，不直接拒绝"},
                    {"text": "已经有安排了，不好意思", "why": "给出理由，不显得敷衍"},
                    {"text": "我不太想出门，改天？", "why": "直接但不伤人，适合关系好的"},
                ],
                "direct": [
                    {"text": "谢谢，但我不想", "why": "明确但礼貌"},
                    {"text": "不太方便", "why": "简短有力"},
                ]
            },
            "表白": {
                "soft": [
                    {"text": "我觉得我们还是做朋友比较好", "why": "温和但明确"},
                    {"text": "现在不想谈恋爱", "why": "不针对个人"},
                ],
                "direct": [
                    {"text": "对不起，我不喜欢你", "why": "虽然伤人但最清楚"},
                ]
            },
            "借钱": {
                "soft": [
                    {"text": "最近手头紧，不好意思", "why": "用经济状况做理由"},
                ],
                "direct": [
                    {"text": "我不太借钱的", "why": "立规矩"},
                ]
            }
        }
        
        # 识别场景
        triggered = None
        for key in rejections:
            if key in situation:
                triggered = key
                break
        
        if not triggered:
            triggered = "邀约"  # 默认
        
        advice = f"""拒绝{triggered}的话术：

委婉版（留有余地）：
"""
        for opt in rejections[triggered]["soft"]:
            advice += f"- {opt['text']}\n  → {opt['why']}\n"
        
        advice += "\n直接版（明确界限）：\n"
        for opt in rejections[triggered]["direct"]:
            advice += f"- {opt['text']}\n  → {opt['why']}\n"
        
        advice += "\n【关键】拒绝后如果对方追问，不要解释太多，解释就是留余地。"
        
        return LifeAdvice(
            category="social",
            advice=advice,
            action_items=["选一条话术", "说完就停，不解释"],
            tools_used=["rejection_advisor"],
        )
    
    async def boundary_check(
        self,
        user_message: str,
        assistant_reply: str,
    ) -> LifeAdvice:
        """关系边界判断。
        
        检测回复是否越界：
        - 太热情（让对方有压力）
        - 太冷淡（让对方觉得被敷衍）
        - 太主动（降低自身价值）
        """
        
        issues = []
        
        # 检测过度热情
        if "!" in assistant_reply or "！" in assistant_reply:
            count = assistant_reply.count("!") + assistant_reply.count("！")
            if count >= 2:
                issues.append("感叹号太多，显得过于热情")
        
        # 检测小作文
        if len(assistant_reply) > 100 and "\n" in assistant_reply:
            issues.append("回复太长，像小作文，给对方压力")
        
        # 检测秒回暗示
        if "一直在等" in assistant_reply or "终于" in assistant_reply:
            issues.append("暗示一直在等，显得太主动")
        
        # 检测敷衍
        if len(assistant_reply) < 5 and "嗯" in assistant_reply:
            issues.append("太短太敷衍")
        
        if issues:
            advice = "边界提醒：\n"
            for issue in issues:
                advice += f"- {issue}\n"
            advice += "\n调整建议：简短自然，不卑不亢。"
        else:
            advice = "边界OK，保持这个节奏。"
        
        return LifeAdvice(
            category="social",
            advice=advice,
            action_items=["调整回复语气"],
            tools_used=["boundary_checker"],
        )


class CampusSkill:
    """校园生活技能。"""
    
    async def where_to_study(
        self,
        preferences: dict[str, Any],
    ) -> LifeAdvice:
        """推荐学习地点。"""
        
        needs_quiet = preferences.get("needs_quiet", True)
        needs_power = preferences.get("needs_power", True)
        
        if needs_quiet and needs_power:
            advice = "图书馆三楼自习室，有插座还安静。或者教学楼空教室。"
        elif needs_quiet:
            advice = "图书馆任意楼层，找个角落。"
        elif needs_power:
            advice = "食堂二楼（下午人少），或者任何有插座的地方。"
        else:
            advice = "宿舍、草坪、甚至床上，怎么舒服怎么来。"
        
        return LifeAdvice(
            category="campus",
            advice=advice,
            action_items=["去图书馆看看有没有位"],
            tools_used=["campus_guide"],
        )
    
    async def daily_routine_check(
        self,
        current_time: str,
        known_routine: dict[str, Any] | None = None,
    ) -> LifeAdvice:
        """日常提醒。"""
        
        # 根据时间段给提醒
        if "早" in current_time or "morning" in current_time.lower():
            advice = "早上好。今天有课吗？记得吃早餐，哪怕只是面包。"
        elif "午" in current_time or "afternoon" in current_time.lower():
            advice = "下午容易犯困，如果没事可以眯20分钟。"
        elif "晚" in current_time or "evening" in current_time.lower():
            advice = "晚上了，今天过得怎么样？还有ddl吗？"
        else:
            advice = "新的一天，有什么计划？"
        
        return LifeAdvice(
            category="campus",
            advice=advice,
            action_items=[],
            tools_used=["routine_reminder"],
        )


class LifeSkillsEngine:
    """生活技能引擎，统一管理所有生活能力。"""
    
    def __init__(self):
        self.diet = DietSkill()
        self.study = StudySkill()
        self.social = SocialSkill()
        self.campus = CampusSkill()
    
    async def execute(
        self,
        task_category: str,
        user_message: str,
        context: dict[str, Any],
    ) -> LifeAdvice:
        """根据任务类别执行对应技能。"""
        
        if task_category == "food":
            # 克制干预检查
            restraint = await self.diet.restraint_check(
                user_message=user_message,
                recent_meals=context.get("recent_meals", []),
            )
            if restraint.advice:  # 如果触发了克制干预
                return restraint
            
            return await self.diet.recommend(
                time_of_day=context.get("time_of_day", "午餐"),
                preferences=context.get("preferences", {}),
                budget_level=context.get("budget_level", "medium"),
                mood=context.get("mood", "neutral"),
                location=context.get("location", ""),
            )
        
        elif task_category == "study":
            # 判断是多任务排序还是单个任务
            if "\n" in user_message and any(kw in user_message for kw in ["ddl", "deadline", "截止", "任务"]):
                return await self.study.parse_and_sort_tasks(user_message)
            
            if any(kw in user_message for kw in ["考试", "期末", "期中", "quiz", "test"]):
                return await self.study.plan_exam(
                    days_left=context.get("days_left", 7),
                    subjects=context.get("subjects", []),
                )
            elif any(kw in user_message for kw in ["学不进去", "不想学", "focus"]):
                return await self.study.micro_plan(
                    task=context.get("task", "学习"),
                    time_available=context.get("time_available", 60),
                )
            else:
                return await self.study.sort_ddl(
                    tasks=context.get("tasks", []),
                )
        
        elif task_category == "social":
            if any(kw in user_message for kw in ["怎么回", "回复", "他说", "她说"]):
                return await self.social.reply_advice(
                    message_from_other=context.get("their_message", ""),
                    relationship_stage=context.get("relationship_stage", "crush"),
                )
            elif any(kw in user_message for kw in ["拒绝", "不想去", "不想回", "怎么说"]):
                return await self.social.rejection_advice(
                    situation=user_message,
                    relationship_stage=context.get("relationship_stage", "crush"),
                )
            else:
                return await self.social.date_judgment(
                    situation=user_message,
                )
        
        elif task_category == "campus":
            if any(kw in user_message for kw in ["图书馆", "自习", "哪里", "study"]):
                return await self.campus.where_to_study(
                    preferences=context.get("preferences", {}),
                )
            else:
                return await self.campus.daily_routine_check(
                    current_time=context.get("current_time", ""),
                )
        
        return LifeAdvice(
            category="general",
            advice="这个我还不太熟，但我在学。你先说说具体情况？",
            action_items=[],
            tools_used=[],
        )


# === SkillOutput-based real skills (v2-first) ===

def study_plan_skill(skill_input: SkillInput) -> SkillOutput:
    """学习规划技能：考试/DDL/学习任务拆解。"""
    text = skill_input.user_message
    # 简单规则：检测关键词生成可执行计划
    cards = [
        {
            "title": "现在先做这一小步",
            "items": [
                "把最急的任务写出来",
                "选一个 25 分钟能开始的部分",
                "做完后再决定要不要继续",
            ],
        }
    ]
    if "考试" in text or "复习" in text:
        cards.append({
            "title": "考试突击策略",
            "items": [
                "先抓老师划的重点/往年题",
                "只做最可能考的一章",
                "不懂的先标记，不要死磕",
            ],
        })
    if "ddl" in text.lower() or "deadline" in text.lower() or "截止" in text:
        cards.append({
            "title": "DDL 急救",
            "items": [
                "先交一个 60 分版本",
                "有框架比没完成强",
                "交完再优化",
            ],
        })

    return SkillOutput(
        name="study_plan",
        should_show=True,
        summary_for_prompt=(
            "用户可能处于学习/DDL压力中。回复时先降压，再给最小可执行计划。"
            "不要一次列太多任务，优先给 1 个当前动作 + 2 个后续步骤。"
        ),
        user_visible_cards=cards,
        debug={"source": "rule_based_v1"},
    )


def reply_advice_skill(skill_input: SkillInput) -> SkillOutput:
    """社交回复建议技能。"""
    return SkillOutput(
        name="reply_advice",
        should_show=True,
        summary_for_prompt=(
            "用户想处理社交回复。直接给 2-3 个可复制句子，"
            "分别是：温和版、直接版、留余地版。"
        ),
        user_visible_cards=[
            {
                "title": "可以这样回",
                "items": [
                    "温和版：我刚刚可能没表达清楚，不是那个意思。",
                    "直接版：这件事我有点不舒服，我们能不能重新说一下？",
                    "留余地版：我先想一下，晚点再认真回你。",
                ],
            }
        ],
        debug={"source": "rule_based_v1"},
    )


def food_recommend_skill(skill_input: SkillInput) -> SkillOutput:
    """饮食推荐技能。"""
    text = skill_input.user_message
    mood = "neutral"
    if any(k in text for k in ["累", "烦", "丧", "emo"]):
        mood = "sad"
    time_of_day = "午餐"
    if any(k in text for k in ["早", "早餐"]):
        time_of_day = "早餐"
    elif any(k in text for k in ["晚", "夜宵", "晚上"]):
        time_of_day = "晚餐"

    comfort_foods = ["麻辣香锅", "螺蛳粉", "炸鸡", "火锅", "奶茶"]
    light_foods = ["粥", "沙拉", "汤面", "饭团"]
    items = comfort_foods if mood == "sad" else light_foods + comfort_foods[:2]

    return SkillOutput(
        name="food_recommend",
        should_show=True,
        summary_for_prompt=(
            "用户问吃什么。直接给 2-3 个具体选择，不要分类列举，"
            "像朋友一样说‘我今天其实想吃炸鸡，但要克制’。"
        ),
        user_visible_cards=[
            {
                "title": f"{time_of_day}想吃点啥",
                "items": items[:4],
            }
        ],
        debug={"mood": mood, "time": time_of_day},
    )


def playlist_recommend_skill(skill_input: SkillInput) -> SkillOutput:
    """歌单/情绪音乐推荐技能。"""
    text = skill_input.user_message
    mood = "chill"
    if any(k in text for k in ["累", "困", "晚安", "睡"]):
        mood = "sleep"
    elif any(k in text for k in ["烦", "丧", "emo", "难过"]):
        mood = "sad"
    elif any(k in text for k in ["学", "专注", "写", "赶"]):
        mood = "focus"

    playlists = {
        "sleep": ["白噪音/雨声", "Lo-fi  sleep beats", "钢琴轻音乐"],
        "sad": ["后摇/治愈系", "陈奕迅/李宗盛", "日语抒情"],
        "focus": ["Lo-fi study beats", "古典 concentratiion", "电子轻节奏"],
        "chill": ["City Pop", "Indie 华语", "R&B 慢歌"],
    }

    return SkillOutput(
        name="playlist_recommend",
        should_show=True,
        summary_for_prompt=(
            "用户想要音乐推荐。直接给 2-3 个歌单/风格，不要分析情绪，"
            "像朋友分享耳机一样自然。"
        ),
        user_visible_cards=[
            {
                "title": "试试这些",
                "items": playlists.get(mood, playlists["chill"]),
            }
        ],
        debug={"mood": mood},
    )
