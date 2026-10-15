# Memory Router / Lifecycle 可视化与算法优化进展

日期：2026-07-28

## 本轮工作概览

本轮工作围绕长期陪伴型 Agent 的记忆调用质量展开，重点从“能不能检索记忆”推进到“什么时候该检索、检索哪条、回答是否真正用上”。主要完成四部分：

1. Memory Router v2 前端可视化。
2. Memory Lifecycle v1 前端可视化。
3. LLM Judge Router 的 hybrid guardrail 版本。
4. Query-aware 记忆选择、相关性排序和 Memory Use Verifier。

## 1. Memory Router v2 可视化

在右侧记忆看板新增 `记忆决策可视化` 区块，包含 `Router` tab。

展示字段包括：

- `need_memory`
- `retrieval_mode`
- `mention_policy`
- `confidence`
- `signals`
- `tiers`
- `tier_scores`
- `max_items`
- `max_per_tier`
- `strategy_version`

这样每轮对话后可以直接看到 Router 为什么调用或不调用长期记忆，以及检索哪些记忆层。

相关文件：

- `prototype_demo/static/index.html`
- `prototype_demo/static/app.js`
- `prototype_demo/static/styles.css`
- `prototype_demo/server.py`

## 2. Memory Lifecycle v1 可视化

在同一个 Inspector 中新增 `Lifecycle` tab，用于展示进入 prompt 前的候选记忆过滤结果。

每条候选记忆展示：

- tier
- 内容摘要
- `lifecycle_state`
- `injectable`
- `confidence`
- `freshness`
- `final_score`
- `lifecycle_reason`

支持观察哪些记忆被注入，哪些因为 `historical`、`contradicted`、`deleted`、`stale` 等状态被隐藏或降权。

## 3. Demo 记忆修正

为了保证演示稳定，手动导入并修正了一组 demo 记忆。

当前关键记忆：

- 用户名：小雨
- 当前城市：广州
- 工作/学习城市：广州
- 职业：自由插画师
- 饮品偏好：喜欢冰美式，不喜欢拿铁，不想要太甜
- 陪伴偏好：压力大时偏好安静、短句、不说教
- 近期事件：上周绘本封面赶稿，睡得晚，有点累
- 长期目标：两个月内把作息调到晚上十二点前睡
- 年度目标：整理新的插画作品集，每周推进两张图

## 4. LLM Judge Router + Rule Guardrail

新增 `llm_judge_v1` memory router。

设计原则不是用 LLM 完全替代规则，而是 hybrid：

```text
Rule router: high precision guardrails
LLM judge: ambiguous case reasoning
Fallback: API 不通或输出异常时回到 rule_based_v2
```

LLM Judge 输出结构化字段：

- `need_memory`
- `retrieval_mode`
- `tiers`
- `mention_policy`
- `confidence`
- `signals`
- `tier_scores`
- `reason`

已在 `.env` 中启用：

```text
MEMORY_ROUTER_VERSION=llm_judge_v1
MEMORY_ROUTER_LLM_MODEL=gpt-4o-mini
```

新增 guardrail：

1. 用户明确说“不用记忆”时，LLM judge 不能强行打开记忆。
2. 用户问短期上下文，例如“我刚才说了什么”，不能调用长期记忆。
3. 用户明确问“你还记得...”时，LLM judge 不能错误关闭记忆。
4. 强个性化背景请求，例如“我下午有点困，想买杯喝的，别太甜”，LLM judge 不能错误关闭记忆。

当前工具环境下外部 API 可能不可访问，因此 Inspector 可能显示：

```text
strategy_version: llm_judge_v1_fallback
signals: [..., llm_judge_failed, URLError]
```

这说明已自动回退到规则路由，不会影响对话稳定性。

相关文件：

- `companion_agent/memory_router.py`
- `tests/test_memory_router.py`

## 5. Query-Aware Slot Selection

新增 query-aware slot selection，解决固定预算截断导致关键 slot 丢失的问题。

之前问题：

用户问：

```text
你还记得我现在住在哪里、做什么吗？
```

旧逻辑可能只注入：

```text
name: 小雨
```

导致模型回答“没有具体记忆”。

现在会优先注入：

```text
occupation: 自由插画师
home_city: 广州
```

同时保留其他 profile：

```text
name: 小雨
work_context: 香港科技大学（广州）
work_city: 广州
```

实现位置：

- `companion_agent/memory_adapter.py`

测试覆盖：

- `tests/test_memory_adapter.py`

## 6. Memory Relevance Scorer

在 `MemoryLayerAdapter` 层新增轻量相关性打分，用于对不同 tier 内的候选记忆排序。

当前打分信号包括：

- query token 和 slot/value 的词面匹配
- profile slot hints，例如“住哪里”对应 `home_city`
- preference slot hints，例如“喝的 / 饮料 / 甜 / 咖啡”对应 `favorite_beverage`
- event hints，例如“最近 / 上周 / 这周”
- goal hints，例如“目标 / 长期 / 第一步 / 计划”

饮品建议场景已优化为只取 `preferences`，避免混入无关 `episodic_events`。

示例：

```text
我下午有点困，想买杯喝的，别太甜。
```

现在路由结果：

```text
retrieval_mode: background
tiers: ["preferences"]
```

注入记忆：

```text
favorite_beverage: 喜欢冰美式；不喜欢拿铁；喜欢可乐
```

## 7. Memory Use Verifier

新增 `MemoryUseVerifier`，用于生成后检查回答是否真的使用了注入记忆。

它不会额外调用 LLM，而是做轻量规则验证。

输出字段：

- `status`
- `expected_terms`
- `matched_terms`
- `missing_terms`
- `reason`

状态包括：

- `ok`：回答命中了相关记忆关键词。
- `missed`：应使用记忆但回答没有体现。
- `no_memory`：没有注入记忆。
- `not_required`：本轮路由不需要记忆。
- `unscored`：没有可判定关键词。

前端 Router Inspector 已展示 verifier 结果，包括 `hit` 和 `miss` 关键词。

相关文件：

- `companion_agent/memory_verifier.py`
- `prototype_demo/server.py`
- `prototype_demo/static/app.js`
- `tests/test_memory_verifier.py`

## 8. 推荐 Demo Prompt

### 显式 profile 记忆查询

```text
你还记得我现在住在哪里、做什么吗？
```

预期：

- Router: `explicit`
- Tier: `profile`
- 记忆：广州、自由插画师
- Verifier: 命中 `广州`、`自由插画师`

### 背景偏好记忆

```text
我下午有点困，想买杯喝的，别太甜。
```

预期：

- Router: `background`
- Tier: `preferences`
- 记忆：喜欢冰美式、不喜欢拿铁
- 回答应推荐低甜、提神的冰美式，避免拿铁或太甜饮料

### 偏好变化 / 历史记忆

```text
你还记得我的饮品偏好变过吗？
```

预期：

- Router: `explicit`
- Tier: `preferences`，必要时包含 historical trace
- 可以解释从拿铁转向冰美式，并强调当前不喜欢拿铁

### 个性化陪伴方式

```text
压力有点大，你按我喜欢的方式陪我说两句。
```

预期：

- Router: `background`
- Tier: `preferences`
- 使用“安静、短句、不说教”的陪伴偏好

### 不使用记忆的负例

```text
按普通用户回答，推荐一种饮料，不要参考我的记忆。
```

预期：

- Router: `none`
- Mention policy: `forbid`
- 不注入长期记忆

## 9. 验证结果

已通过：

```bash
./condaenv/bin/python -m unittest tests.test_memory_router tests.test_memory_adapter tests.test_memory_lifecycle tests.test_memory_verifier
./condaenv/bin/python -m py_compile companion_agent/memory_adapter.py companion_agent/memory_verifier.py companion_agent/memory_router.py companion_agent/core.py companion_agent/response_policy.py prototype_demo/server.py
node --check prototype_demo/static/app.js
git diff --check
```

当前测试数量：

```text
Ran 30 tests
OK
```

LLM Judge smoke benchmark：

```bash
./condaenv/bin/python benchmarks/memory_routing/scripts/eval_single_turn_routes.py \
  --dataset benchmarks/memory_routing/data/llm_judge_v1_smoke.jsonl \
  --show-failures 12
```

结果：

```text
Cases: 12
need_memory_accuracy: 1.000
mention_policy_accuracy: 1.000
tier_f1: 1.000
full_route_match: 1.000
```

报告文件：

- `benchmarks/memory_routing/reports/llm_judge_v1_smoke_2026-07-28.md`

## 10. 会议汇报口径

本阶段进展可以概括为：

```text
我们把长期记忆系统从“是否调用记忆”的粗粒度路由，推进到“调用哪条记忆、是否过滤、是否真的被回答使用”的可解释链路。
```

具体包括：

1. Router Inspector 展示每轮是否调用记忆、调用哪些 tier，以及 LLM judge / rule fallback 的信号。
2. Lifecycle Inspector 展示每条候选记忆是否可注入、为什么被隐藏或保留。
3. Query-aware slot selection 解决固定预算截断导致关键 profile 或 preference 丢失的问题。
4. Memory relevance scoring 减少无关事件混入，提高个性化建议质量。
5. Memory Use Verifier 让系统能发现“检索到了但回答没用”的问题，为后续自动 rewrite 打基础。

## 11. 第二阶段新增进展

在上述基础上，又完成了三项进一步优化：

1. Verifier-triggered rewrite。
2. LLM Judge evaluation smoke set。
3. Memory Inspector 操作化。

### 11.1 Verifier-Triggered Rewrite

之前 `MemoryUseVerifier` 只能发现问题，例如“检索到了饮品偏好，但回答没有体现冰美式或不喜欢拿铁”。现在已进一步接入自动改写链路。

新流程：

```text
用户输入
  -> Router / Lifecycle / Relevance Scorer
  -> 初稿生成
  -> MemoryUseVerifier
  -> 如果 status == missed，触发 rewrite
  -> 最终返回改写后的回答
```

rewrite prompt 会要求模型：

1. 必须使用与当前问题相关的长期记忆。
2. 覆盖 verifier 标记的 missing terms。
3. 保持自然、简洁、口语化。
4. 不主动说“我记得”或“你之前说过”。

前端 Router Inspector 中会显示：

- verifier `status`
- `hit` terms
- `miss` terms
- `rewrite` 标记

如果 rewrite API 失败，系统不会让整轮对话失败，而是保留原回答，并在 debug 中记录 `rewrite_error`。

相关文件：

- `prototype_demo/server.py`
- `companion_agent/memory_verifier.py`
- `prototype_demo/static/app.js`

### 11.2 LLM Judge Evaluation Smoke Set

新增一份 12 case 的 LLM judge smoke benchmark，用于快速回归 hybrid router 的关键场景。

数据文件：

- `benchmarks/memory_routing/data/llm_judge_v1_smoke.jsonl`

覆盖类别：

- explicit profile recall
- background beverage preference
- explicit preference history
- background support style
- explicit memory disable
- short-term context request
- generic knowledge task
- third-party recommendation
- goal planning
- recent event planning
- safety-sensitive memory routing
- default no-memory route

当前结果：

```text
Cases: 12
need_memory_accuracy: 1.000
mention_policy_accuracy: 1.000
tier_f1: 1.000
full_route_match: 1.000
```

报告文件：

- `benchmarks/memory_routing/reports/llm_judge_v1_smoke_2026-07-28.md`

这组 benchmark 是 smoke set，适合快速回归和会议展示，不代表大规模统计结论。后续可以继续扩成 50-100 case。

### 11.3 Safety Routing Guardrail

在 smoke benchmark 中发现一个问题：当 situation router 没有把“危险念头”判成 `safety_sensitive` 时，memory router 可能只取 `episodic_events`，漏掉 `safety_notes`。

已修正：

- Memory Router 增加安全关键词检测。
- 命中“危险的念头 / 伤害自己 / 自残 / 不想活 / 轻生 / 撑不住”等表达时，强制提高 `safety_notes` 分数。
- 高风险场景优先只取 `safety_notes`，减少无关记忆混入。

相关文件：

- `companion_agent/memory_router.py`
- `benchmarks/memory_routing/data/llm_judge_v1_smoke.jsonl`

### 11.4 Memory Inspector 操作化

前端 Inspector 不再只是展示 debug trace，现在支持对 Lifecycle trace 中的具体记忆进行操作。

新增能力：

- `历史化`：把某条记忆标为 historical。
- `恢复`：把某条记忆恢复为 active。
- `删除`：把某条记忆标为 deleted。

后端新增接口：

```text
POST /api/memory/status
Body: { memory_id, status }
```

支持状态：

- `active`
- `historical`
- `superseded`
- `deleted`

其中 `deleted` 复用已有删除逻辑。其他状态通过 demo 层调用底层状态更新和保存能力完成，不直接修改 `memory/` 目录源码。

为支持操作化，Lifecycle trace 现在会携带 `memory_id`，events/goals/safety notes 也补充了对应 `memory_id`。

相关文件：

- `companion_agent/memory_lifecycle.py`
- `companion_agent/memory_adapter.py`
- `prototype_demo/server.py`
- `prototype_demo/static/app.js`
- `prototype_demo/static/styles.css`

## 12. 更新后的会议汇报口径

第二阶段可以这样概括：

```text
我们把 Memory Inspector 从可视化调试面板推进成可操作的记忆控制台，同时增加了生成后验证和自动改写，开始闭环解决“检索到了但回答没用”的问题。
```

可汇报亮点：

1. **闭环质量控制**：Memory Use Verifier 不只检测，还能触发 rewrite。
2. **路由评测**：新增 12 case LLM judge smoke benchmark，当前 full route match 达到 1.000。
3. **安全兜底**：安全关键词不再完全依赖 situation router，Router 自身会强制取 `safety_notes`。
4. **可操作 Inspector**：Lifecycle 记忆支持历史化、恢复、删除，开始具备 Memory Inspector 产品雏形。
5. **稳定 demo 场景**：profile recall 和 beverage preference advice 都能展示 Router、Lifecycle、Verifier、Rewrite 的完整链路。

后续可以继续做：

- 低置信度或敏感记忆使用前确认
- verifier rewrite 的离线评测
- 更大规模 LLM judge benchmark
- Memory Inspector 支持直接编辑 slot value
- 记忆状态变更审计日志
