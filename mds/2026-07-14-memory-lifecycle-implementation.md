# Memory Lifecycle v1 实现记录

日期：2026-07-14

## 本次完成

在不修改底层 `memory/` 目录的前提下，完成 Memory Lifecycle v1 的 Companion 层实现。当前版本把生命周期逻辑放在 `companion_agent/memory_lifecycle.py`，由 `MemoryLayerAdapter` 在返回五层记忆后统一应用。

## 核心能力

### 1. 生命周期状态

支持以下派生状态：

- `active`：当前有效记忆。
- `stale`：新鲜度较低的记忆。
- `historical`：历史上成立，但默认不影响当前回答。
- `contradicted`：被用户纠正或冲突覆盖，默认不注入。
- `deleted`：用户删除或遗忘请求对应的记忆，不注入。

### 2. 生命周期元数据

每条候选记忆都会生成可观测元数据：

```python
{
    "lifecycle_state": "active",
    "confidence": 0.8,
    "freshness": 1.0,
    "evidence_count": 1,
    "last_seen_at": "...",
    "last_used_at": "",
    "replaced_by": None,
    "lifecycle_reason": "active_memory",
    "injectable": True,
    "final_score": 0.95,
}
```

这些信息不会改变原有 prompt 文本结构，而是通过 `TieredMemoryContext.lifecycle_trace` 暴露给 debug 和后续前端展示。

### 3. 分层衰减策略

不同 Tier 使用不同新鲜度策略：

| Tier | 策略 |
| --- | --- |
| `profile` | 180 天后开始衰减 |
| `preferences` | 90 天后开始衰减 |
| `long_term_goals` | 60 天后开始衰减 |
| `episodic_events` | 30 天后开始衰减 |
| `safety_notes` | 不自动衰减 |

### 4. 注入过滤与重排

注入前会执行：

1. 过滤 `deleted`。
2. 过滤 `contradicted`。
3. 默认过滤 `historical`。
4. 当 query 是历史/回忆类问题时，允许 `historical` 注入。
5. 对可注入记忆按 `final_score` 重排。

排序分数由以下因素组成：

```text
final_score = base_relevance
            + confidence
            + freshness
            + tier_priority
            - stale_or_historical_penalty
```

### 5. Debug Trace 接入

`CompanionAgentCore.debug_info["memory"]["lifecycle_trace"]` 现在会包含生命周期决策，便于日志、API 和前端调试面板展示。

## 相关文件

- `companion_agent/memory_lifecycle.py`
- `companion_agent/memory_adapter.py`
- `companion_agent/core.py`
- `companion_agent/__init__.py`
- `tests/test_memory_lifecycle.py`
- `tests/test_memory_adapter.py`

## 测试覆盖

新增或补充测试覆盖：

1. `deleted` 和 `contradicted` 不进入注入结果。
2. `historical` 只在历史查询中注入。
3. `episodic_events` 比 `profile` 衰减更快。
4. 重复偏好证据会提高 `confidence`。
5. `safety_notes` 不自动衰减。
6. preference snapshot 中的状态会影响 mapping 注入。
7. adapter 默认生成 `lifecycle_trace`。

## 验证结果

使用项目 Python 环境验证：

```bash
./condaenv/bin/python -m unittest discover -s tests
./condaenv/bin/python -m compileall companion_agent tests
git diff --check
```

结果：

- 全量 31 个单元测试通过。
- `compileall` 通过。
- `git diff --check` 通过。

说明：系统默认 `python` 是 3.9，全量测试会因为已有 `memory/base.py` 使用 Python 3.10 类型语法而失败。项目文档要求 Python 3.10+，因此以 `./condaenv/bin/python` 为准。

## 组会展示口径

本次工作把长期记忆从“写入后默认长期有效”推进到“带生命周期的可解释记忆系统”。现在每条记忆在进入 prompt 前都会经过状态判断、可信度计算、新鲜度计算和注入过滤。被纠正、删除或过期的记忆不会直接污染当前回答；历史记忆仍可在用户明确询问过去时被使用。

这为后续 Memory Inspector 前端面板、冲突可视化、记忆清理策略和更细粒度的隐私控制打下了基础。
