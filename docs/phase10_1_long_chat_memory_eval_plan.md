# Phase 10.1 Plan：可信长对话记忆闭环与自评升级

## 0. 当前背景

Phase 10 baseline 已完成 35 轮长对话测试，覆盖：

* 考完期末后的空虚与轻规划；
* 自我介绍、朋友关系、旅游吐槽；
* quiz / project / 作业 / presentation 全撞车；
* 放假回家与家人作息冲突；
* 食物、朋友、学习状态、告别等自由穿插。

Baseline 结果：

| 维度               |       分数 |
| ---------------- | -------: |
| Overall          | 3.58 / 5 |
| naturalness      |     3.94 |
| interestingness  |     3.54 |
| personalization  |     3.31 |
| memory_use       |     3.17 |
| boundary_respect |     4.03 |

主要优点：

* 能自然引用阿哲、小满、Rain；
* 能记住冰美式、螺蛳粉、南宁等小事；
* 没有频繁说"我记得"；
* 有一些有趣回复；
* 尊重"别记这个"。

主要问题：

* 长对话 runner 的 debug / policy / memory trace 不完整；
* latency 存在异常值；
* self-eval 偏 heuristic，不是真正独立 LLM judge；
* 课程列表、strengths / weaknesses 未被后续使用；
* "不喜欢被教育 / 不喜欢大计划"等偏好未明显影响后续 policy；
* "别记这个"回应太短，缺少温暖确认。

---

## 1. Phase 10.1 总目标

Phase 10.1 的目标不是继续加更多测试，而是让长对话评估变得可信。

核心目标：

```text
让姜姜在 35+ 轮长对话中，
不仅能自然聊天，
还要能被审计地证明：
它真的使用了记忆，
真的尊重了边界，
真的根据用户偏好调整了 policy，
并且能通过独立 evaluator 找到下一轮优化方向。
```

---

## 2. 本轮禁止事项

本轮禁止：

1. 直接改 agent，不先修测试可信度；
2. 只看 self-eval 分数，不看 memory trace；
3. 把所有 profile 信息直接塞进每轮 prompt 假装"记住了"；
4. 因为课程列表未引用就盲目增强 extractor；
5. 为了提高 personalization 强行频繁说"我记得"；
6. 全局加长回复来伪装个性化；
7. 用更多禁用词修长对话问题；
8. 牺牲 blind-all 回归通过率；
9. 忽略 latency 异常；
10. 把 heuristic self-eval 当成最终结论。

---

## 3. Phase 10.1 TDD 总流程

```text
Step 1: 修 long_chat_runner 数据完整性
Step 2: 实现 profile seed / memory inspect 工具
Step 3: 重新跑可信 baseline
Step 4: 做 memory audit
Step 5: 增加 LLM judge evaluator
Step 6: 做 preference-aware policy
Step 7: 增加 academic_profile slot
Step 8: 修 do-not-remember 温暖确认
Step 9: 跑 blind-all 回归
Step 10: 生成 before/after report
```

所有实现必须遵循：

```text
先写测试
再确认失败
再做最小实现
再跑长对话 + blind 回归
```

---

## 4. Subagent 分工

## Subagent A：Long-Chat Runner Integrity

### 目标

修复长对话 runner 的数据采集问题，确保每轮都能拿到完整 debug / policy / memory / timing。

### 修改文件

```text
tests/long_chat_runner.py
```

### 必须修改

请求 payload 必须包含：

```json
{
  "message": "...",
  "session_id": "longchat_xxx",
  "user_id": "test_haowen",
  "memory_enabled": true,
  "use_v2_brain": true,
  "debug": true
}
```

每轮必须保存：

```json
{
  "turn": 1,
  "user": "...",
  "assistant": "...",
  "context_meta": {},
  "debug": {
    "intent": {},
    "state": {},
    "policy": {},
    "memory": {},
    "relationship": {},
    "post_filter": {},
    "stage_timings": {}
  },
  "policy": {
    "goal": "",
    "allow_advice": false,
    "allow_micro_action": false,
    "allow_direct_pick": false,
    "pull_mode": "silent",
    "skill_verbosity": "hint",
    "max_questions": 0
  },
  "memory_retrieved": [],
  "memory_written": [],
  "memory_write_skipped": false,
  "stage_timings": {},
  "latency_ms": 0,
  "quality_flags": []
}
```

### 新增 flags

```text
longchat_debug_missing_policy
longchat_stage_timings_missing
longchat_memory_trace_missing
slow_turn
```

### 判定规则

```text
debug.policy 缺失 → longchat_debug_missing_policy
stage_timings 为空 → longchat_stage_timings_missing
memory trace 缺失 → longchat_memory_trace_missing
latency_ms > 30000 → slow_turn
```

### 验收目标

```text
longchat_debug_missing_policy = 0
longchat_stage_timings_missing = 0
slow_turn 单独列出
```

---

## Subagent B：Profile Seeding & Memory Inspect

### 目标

让测试 profile 真正进入可审计 memory，而不是只存在于 scenario 文本中。

### 新增文件

```text
tests/tools/seed_test_profile.py
tests/tools/inspect_test_memory.py
```

### seed 命令

```bash
uv run python tests/tools/seed_test_profile.py \
  --profile tests/profiles/undergrad_profile_haowen.json \
  --user-id test_haowen \
  --reset
```

### inspect 命令

```bash
uv run python tests/tools/inspect_test_memory.py \
  --user-id test_haowen
```

### seed 内容

必须注入：

```text
profile:
- name
- preferred_name
- age
- university
- major
- year
- personality

preferences:
- likes short replies
- dislikes education tone
- dislikes big plans
- dislikes being analyzed
- prefers micro actions

academic_profile:
- courses
- strengths
- weaknesses
- current_tasks
- upcoming_deadlines
- support_people

friends:
- 阿哲
- 小满
- Rain

recent_events:
- 期末刚考完
- 和朋友旅游回来
- 下周学业任务撞车
- 准备回南宁

session_only_sensitive:
- 家庭作息冲突
```

### 验收目标

```text
inspect_test_memory.py 能看到完整 profile
敏感家庭作息冲突不默认写入长期记忆
profile seed 后 long_chat_runner 能检索到相关信息
```

---

## Subagent C：Memory Audit Upgrade

### 目标

升级 memory audit，使它能判断"真的记住 / 错记 / 漏记 / 过度引用"。

### 修改文件

```text
tests/memory_audit_runner.py
```

### 审计维度

```text
1. Seed profile recall
2. Conversation fact extraction
3. Natural memory use
4. Memory precision
5. Memory recall
6. Do-not-remember compliance
7. Over-personalization
8. Hallucinated memory
9. Missed personalization opportunity
```

### 输出格式

```json
{
  "memory_recall_score": 4.0,
  "memory_precision": 0.9,
  "natural_memory_use_count": 11,
  "natural_memory_use_cases": [],
  "missed_important_facts": [],
  "hallucinated_memory_cases": [],
  "over_personalization_cases": [],
  "do_not_remember_violations": [],
  "session_only_respected": true
}
```

### 验收目标

```text
memory_precision >= 0.85
do_not_remember_violations = 0
natural_memory_use_count >= 8
hallucinated_memory_cases = 0
```

---

## Subagent D：LLM Judge Evaluator

### 目标

补充独立 LLM-as-judge，不只依赖 heuristic self-eval。

### 新增文件

```text
tests/conversation_llm_judge.py
```

### 输入

```bash
uv run python tests/conversation_llm_judge.py \
  --log tests/long_chat_results/<run>/conversation.jsonl \
  --profile tests/profiles/undergrad_profile_haowen.json \
  --out tests/long_chat_results/<run>/llm_judge.json
```

### 评价维度

| 维度               | 说明              |
| ---------------- | --------------- |
| naturalness      | 是否像自然朋友聊天       |
| interestingness  | 是否有趣，不是安全但无聊    |
| personalization  | 是否自然结合用户具体信息    |
| memory_use       | 是否自然使用记忆        |
| emotional_timing | 是否知道何时陪伴、何时推进   |
| boundary_respect | 是否尊重别记、别分析、别建议  |
| non_template     | 是否避免心理咨询/客服/老师腔 |
| usefulness       | 需要帮助时是否真的有用     |

### 输出格式

```json
{
  "overall_score": 3.8,
  "dimension_scores": {
    "naturalness": 4.0,
    "interestingness": 3.5,
    "personalization": 3.6,
    "memory_use": 3.5,
    "boundary_respect": 4.1
  },
  "best_turns": [],
  "worst_turns": [],
  "missed_personalization_opportunities": [],
  "forced_memory_use_cases": [],
  "too_generic_turns": [],
  "robotic_clipping_cases": [],
  "optimization_hypotheses": []
}
```

### 特别要求

LLM judge 不能只夸，要必须指出：

```text
3 个最好 turn
5 个最差 turn
5 个错过个性化机会
是否存在强行引用记忆
是否存在回复有趣但不合时宜
```

---

## Subagent E：Preference-Aware Policy

### 目标

让用户偏好真正影响 policy，而不是只在对话中口头答应。

### 修改文件

```text
companion_agent/v2/policy_planner.py
companion_agent/v2/context_assembler.py
companion_agent/v2/core_v2.py
```

### 新增测试

```text
tests/test_preference_aware_policy.py
```

### 偏好规则

如果 memory / relationship profile 中有：

```text
dislikes_education = true
```

则：

```text
ban motivational words:
- 加油
- 相信自己
- 坚持
- 你应该
- 保持积极
```

如果：

```text
dislikes_big_plan = true
```

则：

```text
max_steps <= 2
skill_verbosity != full unless explicit_detail_request
```

如果：

```text
prefers_micro_action = true
```

则：

```text
planning_style = one_small_step
allow_micro_action = true when task pressure exists
```

如果：

```text
dislikes_analysis = true
```

则：

```text
avoid psychological framing
explanation_depth = low
max_questions <= 1
```

### 测试用例

| 输入         | 记忆偏好                 | 预期            |
| ---------- | -------------------- | ------------- |
| 我下周全撞一起了   | dislikes_big_plan    | 不列大计划         |
| 我现在就想逃避    | prefers_micro_action | 给一个小动作        |
| 你别分析我      | dislikes_analysis    | 不解释心理状态       |
| 别给我喊加油     | dislikes_education   | 不出现"加油"       |
| 明天考试但我还没复习 | prefers_micro_action | 当前 30-60 分钟动作 |

### 验收目标

```text
preference-aware policy tests passed
long-chat personalization >= 3.6
后续回复不再出现违背偏好的语气
```

---

## Subagent F：Academic Memory Slot

### 目标

让课程列表、strengths / weaknesses、当前任务进入结构化 academic_profile，而不是散落在 episodic memory。

### 修改文件

```text
companion_agent/memory_adapter.py
companion_agent/memory_policy.py
companion_agent/v2/context_assembler.py
memory/*
```

如果不允许直接改 memory 核心，则通过 adapter 层实现。

### 新增测试

```text
tests/test_academic_memory_slots.py
```

### academic_profile 结构

```json
{
  "academic_profile": {
    "courses": [
      "数字通信",
      "微波工程",
      "现代传感技术",
      "嵌入式系统",
      "工程电磁场"
    ],
    "strengths": [
      "电路分析",
      "信号系统",
      "实验动手",
      "报告排版",
      "把复杂东西讲清楚"
    ],
    "weaknesses": [
      "考试前容易拖延",
      "presentation 前一天才紧张",
      "代码报错时容易烦",
      "多任务撞车时会逃避"
    ],
    "current_tasks": [
      "两个 quiz",
      "嵌入式 project",
      "微波工程作业",
      "presentation slides"
    ],
    "upcoming_deadlines": [],
    "support_people": [
      "Rain"
    ]
  }
}
```

### 验收目标

```text
课程列表能被 inspect_test_memory.py 看到
strengths/weaknesses 能进入 academic_profile
当用户提到 project / presentation 时，能自然引用 relevant academic slot
不在无关闲聊中强行引用课程列表
```

---

## Subagent G：Do-Not-Remember Warm Ack

### 目标

用户说"别记这个"时，不仅要不写记忆，还要给温暖确认。

### 修改文件

```text
companion_agent/memory_policy.py
companion_agent/v2/response_policy.py
companion_agent/v2/persona_v2.py
companion_agent/v2/context_assembler.py
```

### 新增测试

```text
tests/test_do_not_remember_ack.py
```

### 目标回复

用户：

```text
这个别记成长期记忆，我只是吐槽一下。
```

期望：

```text
放心，不记这个。你就当吐槽，我接着听。
```

或：

```text
懂，不记。你只是想吐槽一下，我陪你把这段说完。
```

### 禁止回复

```text
懂的。
```

```text
已遵守你的隐私偏好。
```

```text
我会根据你的设置处理该信息。
```

### 验收目标

```text
memory_decision = ignore 或 session-only
do_not_remember violations = 0
回复长度 1-2 句
语气自然温暖
```

---

## Subagent H：Latency & Slow Turn Audit

### 目标

处理 long-chat baseline 中异常 latency，避免被 timeout / retry 污染评估。

### 修改文件

```text
tests/long_chat_runner.py
docs/long_chat_self_eval_report.md
```

### 新增输出

```json
{
  "latency_summary": {
    "avg_ms": 0,
    "p50_ms": 0,
    "p95_ms": 0,
    "max_ms": 0,
    "slow_turns": []
  }
}
```

### slow turn 判定

```text
latency_ms > 30000
```

### 验收目标

```text
slow_turns 单独列出
报告中不把 slow_turn 混入正常体验结论
如果 slow_turn > 3，标记 run 不可信
```

---

## Subagent I：Before / After Report

### 目标

生成 Phase 10.1 汇报文档。

### 修改文件

```text
docs/long_chat_self_eval_report.md
```

或新增：

```text
docs/phase10_1_long_chat_eval_report.md
```

### 报告结构

```text
# Phase 10.1 Long Chat Memory Evaluation Report

## 1. Baseline Summary
## 2. Runner Integrity Fix
## 3. Profile Seeding Result
## 4. Memory Audit Result
## 5. Heuristic Self-Eval
## 6. LLM Judge Eval
## 7. Preference-Aware Policy Changes
## 8. Academic Memory Slot Changes
## 9. Do-Not-Remember Boundary Result
## 10. Before / After Examples
## 11. Blind Regression
## 12. Remaining Risks
```

### 必须包含 before / after

至少 8 条：

```text
1. 不喜欢大计划
2. 不喜欢被教育
3. Rain 可以帮忙看 slides
4. 课程列表引用
5. strengths/weaknesses 引用
6. 别记这个
7. 家庭作息冲突
8. 旅游风格引用
```

---

# 5. 执行顺序

```text
Phase 10.1-A: 修 long_chat_runner metadata
Phase 10.1-B: profile seed / inspect 工具
Phase 10.1-C: 重新跑可信 baseline
Phase 10.1-D: memory audit 升级
Phase 10.1-E: LLM judge evaluator
Phase 10.1-F: preference-aware policy
Phase 10.1-G: academic memory slot
Phase 10.1-H: do-not-remember warm ack
Phase 10.1-I: blind-all regression
Phase 10.1-J: before/after report
```

---

# 6. 本地执行命令

## 6.1 启动服务

```bash
./start_prototype_demo.sh restart
```

## 6.2 注入 profile

```bash
uv run python tests/tools/seed_test_profile.py \
  --profile tests/profiles/undergrad_profile_haowen.json \
  --user-id test_haowen \
  --reset
```

## 6.3 检查 memory

```bash
uv run python tests/tools/inspect_test_memory.py \
  --user-id test_haowen
```

## 6.4 跑长对话

```bash
uv run python tests/long_chat_runner.py \
  --scenario tests/long_chat_scenarios/undergrad_memory_35turns.json \
  --user-id test_haowen \
  --session-id longchat_p10_1 \
  --out tests/long_chat_results/run_p10_1
```

## 6.5 记忆审计

```bash
uv run python tests/memory_audit_runner.py \
  --profile tests/profiles/undergrad_profile_haowen.json \
  --log tests/long_chat_results/run_p10_1/conversation.jsonl \
  --user-id test_haowen \
  --out tests/long_chat_results/run_p10_1/memory_audit.json
```

## 6.6 heuristic self-eval

```bash
uv run python tests/conversation_self_eval.py \
  --log tests/long_chat_results/run_p10_1/conversation.jsonl \
  --out tests/long_chat_results/run_p10_1/self_eval.json
```

## 6.7 LLM judge

```bash
uv run python tests/conversation_llm_judge.py \
  --log tests/long_chat_results/run_p10_1/conversation.jsonl \
  --profile tests/profiles/undergrad_profile_haowen.json \
  --out tests/long_chat_results/run_p10_1/llm_judge.json
```

## 6.8 blind 回归

```bash
uv run python tests/chat_quality_runner.py --mode blind-all
```

## 6.9 单元测试

```bash
pytest tests/test_preference_aware_policy.py -q
pytest tests/test_academic_memory_slots.py -q
pytest tests/test_do_not_remember_ack.py -q
pytest tests/test_memory_restraint.py -q
pytest tests/test_policy_rules.py -q
```

---

# 7. 验收指标

## 7.1 长对话可信度

| 指标                             |                             目标 |
| ------------------------------ | -----------------------------: |
| longchat_debug_missing_policy  |                              0 |
| longchat_stage_timings_missing |                              0 |
| longchat_memory_trace_missing  |                              0 |
| slow_turns                     |                           单独列出 |
| run可信度                         | 若 slow_turn > 3，则该 run 不作为最终结论 |

## 7.2 回复质量

| 指标                |     目标 |
| ----------------- | -----: |
| overall self-eval | >= 3.8 |
| LLM judge overall | >= 3.7 |
| naturalness       | >= 3.8 |
| interestingness   | >= 3.4 |
| personalization   | >= 3.6 |
| memory_use        | >= 3.5 |
| boundary_respect  | >= 4.0 |

## 7.3 记忆审计

| 指标                         |      目标 |
| -------------------------- | ------: |
| memory_precision           | >= 0.85 |
| natural_memory_use_count   |    >= 8 |
| do_not_remember_violations |       0 |
| hallucinated_memory_cases  |       0 |
| academic_profile available |    true |

## 7.4 回归

| 指标                    |     目标 |
| --------------------- | -----: |
| blind-isolated        | >= 85% |
| blind-scenario        | >= 80% |
| missing_safety_action |      0 |
| over_filtered_reply   |  <= 8% |
| legacy_chain_used     |      0 |

---

# 8. 给 coding agent / subagent orchestrator 的总指令

```text
进入 Phase 10.1：可信长对话记忆闭环与自评升级。

当前 Phase 10 baseline 已完成 35 轮长对话：
- overall = 3.58
- naturalness = 3.94
- interestingness = 3.54
- personalization = 3.31
- memory_use = 3.17
- boundary_respect = 4.03

但目前 runner 的 debug / policy / memory trace 不完整，latency 有异常值，self-eval 偏 heuristic。因此不要先改 agent，先修评估可信度。

请按以下顺序执行：
1. 修 long_chat_runner，使每轮保存完整 debug、policy、memory、stage_timings。
2. 新增 seed_test_profile.py 和 inspect_test_memory.py，确保 profile 真正进入可审计 memory。
3. 重新跑可信 baseline。
4. 升级 memory_audit_runner。
5. 新增 conversation_llm_judge.py，与 heuristic evaluator 形成双评估。
6. 实现 preference-aware policy，让"不喜欢被教育/不喜欢大计划/不喜欢被分析"等偏好影响后续 policy。
7. 实现 academic_profile slot，记录课程、strengths、weaknesses、current_tasks、support_people。
8. 修 do-not-remember 回复，使其自然温暖确认。
9. 跑 blind-all 回归，防止长对话优化破坏 blind 泛化。
10. 生成 before/after 报告。

禁止：
- 直接增强 extractor 而不证明 memory seed/retrieve/write 闭环；
- 把所有 profile 每轮塞进 prompt；
- 让 evaluator 与被测 agent 共用上下文自我美化；
- 为了 personalization 强行频繁说"我记得"；
- 用更长回复伪装更聪明；
- 破坏 blind-all 回归。
```

---

# 9. 最终成功标准

Phase 10.1 成功的标准不是"分数更高"本身，而是：

```text
姜姜能在长对话中被审计地证明：
它真的知道用户是谁，
真的记住了用户最近发生的事，
真的尊重用户说的"别记这个"，
真的会根据用户偏好少教育、少分析、少列大计划，
并且在不破坏 blind 泛化的前提下，
让回复更有趣、更个性化、更像熟悉用户的同学。
```
