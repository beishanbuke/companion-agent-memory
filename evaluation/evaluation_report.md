# 姜姜聊天质量评估报告（自动化汇总）

> 生成时间：2026-05-05 14:12
> 数据来源：`tests/chat_quality_results/`

## 关键里程碑

| 阶段 | Blind Isolated | Blind Scenario |
|------|---------------|----------------|
| Phase 7.1 Baseline | 67% (70/104) | 45% (9/20) |
| Phase 8 After-fix | 88% (92/104) | 85% (17/20) |
| **Phase 8.1 Final** | **97% (101/104)** | **100% (20/20)** |

## 所有运行记录

| 运行名称 | 模式 | 用例数 | 通过 | 失败 | 通过率 |
|----------|------|--------|------|------|--------|
| baseline_enhanced | all | 58 | 31 | 25 | 55.0% |
| full_suite | all | 58 | 57 | 1 | 98.0% |
| final_suite | all | 58 | 58 | 0 | 100.0% |
| blind_isolated_run | isolated | 104 | 70 | 34 | 67.0% |
| final_isolated | isolated | 53 | 45 | 8 | 85.0% |
| post_filter_fix | isolated | 53 | 46 | 7 | 87.0% |
| runner_fix | isolated | 53 | 46 | 7 | 87.0% |
| blind_isolated_p8 | isolated | 104 | 92 | 12 | 88.0% |
| near_perfect | isolated | 53 | 49 | 4 | 92.0% |
| push_for_100 | isolated | 53 | 51 | 2 | 96.0% |
| blind_isolated_p8_final | isolated | 104 | 101 | 3 | 97.0% |
| attempt_100 | isolated | 53 | 52 | 1 | 98.0% |
| attempt_100_2 | isolated | 53 | 52 | 1 | 98.0% |
| final_attempt | isolated | 53 | 52 | 1 | 98.0% |
| final_check | isolated | 53 | 52 | 1 | 98.0% |
| final_push | isolated | 53 | 52 | 1 | 98.0% |
| final_verification | isolated | 53 | 52 | 1 | 98.0% |
| next_attempt | isolated | 53 | 52 | 1 | 98.0% |
| perfect_run | isolated | 53 | 52 | 1 | 98.0% |
| server_restarted | isolated | 53 | 52 | 1 | 98.0% |
| blind_sample | isolated | 5 | 5 | 0 | 100.0% |
| final_final | isolated | 53 | 53 | 0 | 100.0% |
| subset_check | isolated | 12 | 12 | 0 | 100.0% |
| blind_scenario_run | scenario | 20 | 9 | 11 | 45.0% |
| scenario_check | scenario | 5 | 3 | 2 | 60.0% |
| blind_scenario_p8_final_v4 | scenario | 20 | 16 | 4 | 80.0% |
| blind_scenario_p8_final | scenario | 20 | 17 | 3 | 85.0% |
| blind_scenario_p8_v2 | scenario | 20 | 17 | 3 | 85.0% |
| blind_scenario_p8_final_v2 | scenario | 20 | 18 | 2 | 90.0% |
| blind_scenario_p8_final_v3 | scenario | 20 | 18 | 2 | 90.0% |
| blind_scenario_p8_final_v5 | scenario | 20 | 20 | 0 | 100.0% |
| scenario_after_fix | scenario | 5 | 5 | 0 | 100.0% |

## 可视化图表

- `milestone_comparison.png` — 关键里程碑通过率对比
- `blind_isolated_trend.png` — Blind Isolated 通过率趋势
- `blind_scenario_trend.png` — Blind Scenario 通过率趋势
- `failure_distribution_isolated.png` — Isolated 失败原因分布
- `failure_distribution_scenario.png` — Scenario 失败原因分布

## Human-likeness 评估（102 cases, LLM-as-judge）

| 维度 | 平均分 | 说明 |
|------|--------|------|
| naturalness | **4.56/5.0** | 非常自然，像真人微信聊天 |
| warmth | **4.16/5.0** | 有温度，有共情 |
| undergrad_vibe | **4.53/5.0** | 本科生感强，贴近校园生活 |
| non_template | **4.39/5.0** | 非模板感，独特有新意 |
| usefulness | **2.68/5.0** | 较低（符合陪伴型 Agent 设计，重点在情绪支持而非信息提供） |

**低分 case 分析（非 usefulness）**：
- `blind_greeting_01` "在" → "懂的。"（warmth=2，过短且冷淡）
- `blind_mock_02` "你是不是有感情了" → "啊这.."（warmth=2）
- `blind_typo_01` "好累阿" → "懂的。"（warmth=2, undergrad_vibe=2）
- 多次出现 "这也太真实了.." / "这也太惨了.." 被评 warmth=2（重复口头禅）

**洞察**：短回复（"懂的。" / "啊这.."）虽然满足 hard_rules，但在 human-likeness 维度上 warmth 不足。可考虑在 persona 中增加情感表达 variety。

---
*本报告由 `evaluation/generate_report.py` 自动生成*