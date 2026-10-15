# Memory Lifecycle v1 计划

日期：2026-07-14

## 背景

当前项目已经具备五层记忆模型、Memory Router v2、记忆检索预算和基础写入策略。现有系统的主要问题是：一旦信息被写入长期记忆，它在后续检索和注入中基本被视为长期有效，缺少对记忆新鲜度、可信度、冲突、过期和历史状态的统一管理。

对于长期陪伴型 Agent，仅仅“记住”是不够的。系统还需要知道一条记忆是否仍然可信、是否已经被用户纠正、是否只是历史事实、是否应该继续影响当前回答。

Memory Lifecycle v1 的目标是把记忆系统从静态存储升级为带生命周期的长期记忆管理机制。

## 目标

1. 为不同类型记忆定义生命周期状态。
2. 为注入上下文的记忆附加可信度、新鲜度和证据强度。
3. 用户纠正信息时，保留旧记忆的历史轨迹，而不是简单覆盖或删除。
4. 检索注入前过滤或降权过期、低可信、被纠正的记忆。
5. 提供可测试、可解释、可展示的生命周期决策结果。

## 非目标

v1 阶段不直接修改底层 `memory/` 目录中的核心存储引擎，避免影响已有结构化记忆实现。生命周期逻辑优先放在 Companion Agent 层，通过 adapter 或独立 manager 做派生计算。

v1 阶段不引入复杂学习模型，先使用规则实现，保证可解释和可调试。

## 生命周期状态

计划引入以下状态：

| 状态 | 含义 | 是否默认注入 |
| --- | --- | --- |
| `active` | 当前有效记忆 | 是 |
| `stale` | 长时间未使用或可能过期 | 降权或按场景注入 |
| `historical` | 曾经有效，但已被新信息替代 | 默认不注入 |
| `contradicted` | 被用户纠正或与新记忆冲突 | 默认不注入 |
| `deleted` | 用户明确要求删除 | 不注入 |

其中 `historical` 和 `contradicted` 的区别是：

- `historical`：旧信息仍可作为过去事实存在，例如“我以前住在上海”。
- `contradicted`：旧信息不应再作为事实使用，例如“我现在不喜欢拿铁了”之后，旧的“喜欢拿铁”不能继续影响推荐。

## 生命周期元数据

每条进入 Companion 层的记忆都附加生命周期元数据：

```python
{
    "lifecycle_state": "active",
    "confidence": 0.8,
    "freshness": 0.9,
    "evidence_count": 1,
    "last_seen_at": "...",
    "last_used_at": "...",
    "replaced_by": None,
    "lifecycle_reason": "explicit_user_statement"
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `lifecycle_state` | 当前生命周期状态 |
| `confidence` | 记忆可信度，范围 0.0 到 1.0 |
| `freshness` | 新鲜度，范围 0.0 到 1.0 |
| `evidence_count` | 用户重复表达或确认的次数 |
| `last_seen_at` | 最近一次被用户提到的时间 |
| `last_used_at` | 最近一次被系统注入或使用的时间 |
| `replaced_by` | 替代它的新记忆 ID |
| `lifecycle_reason` | 当前状态或分数的主要原因 |

## 分层策略

不同 Tier 使用不同生命周期策略。

| Tier | 生命周期特点 | v1 策略 |
| --- | --- | --- |
| `profile` | 稳定事实，变化低频 | 高初始可信度，慢衰减 |
| `preferences` | 容易变化，常有正负偏好 | 关注冲突、证据次数和最近表达 |
| `long_term_goals` | 有阶段性，可能完成或放弃 | 中等衰减，需要近期证据刷新 |
| `episodic_events` | 事件型记忆，时间敏感 | 快衰减，适合归档或摘要 |
| `safety_notes` | 高敏、重要、不应随意遗忘 | 不自动衰减，检索和注入更严格 |

## 规则设计

### 初始可信度

| 情况 | 初始 `confidence` |
| --- | ---: |
| 用户明确自述稳定事实 | 0.9 |
| 用户明确表达偏好 | 0.8 |
| 用户描述一次性事件 | 0.7 |
| 系统推断得到的信息 | 0.5 |
| 模糊、玩笑或不确定表达 | 0.3 |

### 新鲜度衰减

v1 使用简单规则：

| Tier | 衰减速度 |
| --- | --- |
| `profile` | 180 天后开始明显衰减 |
| `preferences` | 90 天后开始明显衰减 |
| `long_term_goals` | 60 天后开始明显衰减 |
| `episodic_events` | 30 天后开始明显衰减 |
| `safety_notes` | 不自动衰减 |

### 证据增强

当用户重复确认同一事实或偏好时：

```text
confidence += 0.05
evidence_count += 1
freshness = 1.0
```

`confidence` 上限为 1.0。

### 冲突处理

当用户表达与已有记忆冲突的信息时：

```text
旧记忆:
  lifecycle_state = historical 或 contradicted
  replaced_by = 新记忆 ID

新记忆:
  lifecycle_state = active
  confidence = 0.85

冲突记录:
  previous_value
  new_value
  reason
  resolved_at
```

示例：

```text
用户：我喜欢拿铁。
记忆：喜欢拿铁，active，confidence=0.8

用户：我现在不喝拿铁了，改喝美式。
旧记忆：喜欢拿铁，contradicted
新记忆：喜欢美式，active，confidence=0.85
```

## 检索注入策略

生命周期信息最终要影响上下文注入。

v1 的过滤规则：

1. `deleted` 不注入。
2. `contradicted` 默认不注入。
3. `historical` 只在用户询问过去、变化历史或冲突解释时注入。
4. `stale` 降权，除非 query 明确相关。
5. `active` 正常参与排序。

排序分数可以使用：

```text
final_score = relevance * 0.50
            + confidence * 0.20
            + freshness * 0.20
            + tier_priority * 0.10
```

v1 可以先在注入前做过滤和重排，不改变底层检索接口。

## 实现计划

### 新增文件

```text
companion_agent/memory_lifecycle.py
tests/test_memory_lifecycle.py
```

### 修改文件

```text
companion_agent/memory_adapter.py
companion_agent/core.py
```

### 模块职责

`MemoryLifecycleManager`：

- 接收 adapter 输出的五层记忆。
- 计算 `lifecycle_state`、`confidence`、`freshness`。
- 根据状态过滤和重排候选记忆。
- 输出可解释的 lifecycle trace。

`MemoryLayerAdapter`：

- 保持底层 snapshot 到五层记忆的映射。
- 在返回结果中附加 lifecycle metadata。

`CompanionAgentCore`：

- 在构建 prompt 前应用 lifecycle filter。
- 将 lifecycle trace 写入 debug 信息，便于日志和前端展示。

## 测试计划

### 单元测试

覆盖以下场景：

1. 稳定 profile 记忆默认高可信、慢衰减。
2. 偏好记忆在重复确认后提高 `confidence` 和 `evidence_count`。
3. 事件记忆随时间降低 `freshness`。
4. 被纠正的偏好旧值进入 `contradicted`。
5. `deleted` 和 `contradicted` 不进入注入结果。
6. `historical` 只在历史查询场景允许注入。
7. `safety_notes` 不自动衰减。

### Demo Case

用于组会展示的最小对话：

```text
用户：我喜欢拿铁。
系统记录：favorite_beverage=拿铁，active，confidence=0.8

用户：我现在不喝拿铁了，改喝美式。
系统更新：
  - 拿铁 -> contradicted
  - 美式 -> active
  - 记录 conflict

用户：帮我推荐一杯下午喝的咖啡。
系统注入：美式偏好
系统不注入：旧的拿铁偏好
```

## 组会展示口径

可以这样概括：

> 这一步不是继续增加记忆数量，而是给长期记忆引入生命周期。不同类型记忆会有不同的新鲜度、可信度和冲突处理方式。用户纠正信息后，旧记忆不会直接消失，而是进入 historical 或 contradicted 状态，保留可追溯性；最终检索注入时，系统会过滤或降权过期、低可信、被纠正的记忆，减少长期记忆污染回答。

## 里程碑

| 阶段 | 内容 | 预期产出 |
| --- | --- | --- |
| v1.0 | 生命周期规则类和单测 | `MemoryLifecycleManager` + 单元测试 |
| v1.1 | 接入 adapter 和 core | 注入前过滤和重排 |
| v1.2 | Debug trace | 日志或 API 中展示生命周期决策 |
| v1.3 | 前端展示 | Memory Inspector 显示状态、可信度、冲突 |

## 风险与取舍

1. 不直接修改 `memory/` 底层模块，短期内部分状态是派生状态，不一定持久化。
2. 规则衰减参数需要后续通过真实使用数据校准。
3. `historical` 和 `contradicted` 的边界需要更多案例验证。
4. 过强过滤可能导致用户问历史问题时查不到旧记忆，因此需要结合 query intent 判断。

## 下一步

优先实现 v1.0：

1. 新增 `companion_agent/memory_lifecycle.py`。
2. 实现生命周期状态、可信度、新鲜度计算。
3. 编写 `tests/test_memory_lifecycle.py`。
4. 使用咖啡偏好变化案例作为 demo。
5. 再决定是否接入 `memory_adapter.py` 和 `core.py`。
