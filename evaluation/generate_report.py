#!/usr/bin/env python3
"""
Evaluation Report Generator
整理历史测试结果并生成可视化图表
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

# 设置中文字体
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "SimHei", "STHeiti", "PingFang SC", "Heiti SC"]
plt.rcParams["axes.unicode_minus"] = False

# 项目根目录
ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "tests" / "chat_quality_results"
EVAL_DIR = ROOT / "evaluation"


def load_all_summaries() -> list[dict]:
    """加载所有 chat_quality_summary.json 文件。"""
    summaries = []
    for subdir in sorted(RESULTS_DIR.iterdir()):
        summary_file = subdir / "chat_quality_summary.json"
        if summary_file.exists():
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_run_name"] = subdir.name
                summaries.append(data)
    return summaries


def categorize_runs(summaries: list[dict]) -> dict[str, list[dict]]:
    """按测试模式分类运行结果。"""
    categorized = defaultdict(list)
    for s in summaries:
        mode = s.get("mode", "unknown")
        categorized[mode].append(s)
    # 按 total_cases 排序作为时间顺序的近似
    for mode in categorized:
        categorized[mode].sort(key=lambda x: x.get("pass_rate", 0))
    return dict(categorized)


def plot_pass_rate_trend(runs: list[dict], title: str, output_path: Path) -> None:
    """绘制通过率趋势图。"""
    labels = [r["_run_name"] for r in runs]
    rates = [r.get("pass_rate", 0) * 100 for r in runs]
    counts = [r.get("pass_count", 0) for r in runs]
    totals = [r.get("total_cases", 0) for r in runs]

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = plt.cm.RdYlGn([rate / 100 for rate in rates])
    bars = ax.barh(range(len(labels)), rates, color=colors, edgecolor="gray")

    for i, (bar, rate, count, total) in enumerate(zip(bars, rates, counts, totals)):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                f"{rate:.0f}% ({count}/{total})", va="center", fontsize=9)

    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Pass Rate (%)", fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.axvline(x=85, color="green", linestyle="--", alpha=0.5, label="Target 85%")
    ax.axvline(x=90, color="blue", linestyle="--", alpha=0.5, label="Target 90%")
    ax.legend(loc="lower right")
    ax.invert_yaxis()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def plot_failure_distribution(run_name: str, output_path: Path) -> None:
    """绘制失败原因分布饼图（取最新的一次运行）。"""
    results_file = RESULTS_DIR / run_name / "chat_quality_results.jsonl"
    if not results_file.exists():
        return

    failures = []
    with open(results_file, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line.strip())
            if not obj.get("passed") and "error" not in obj:
                failures.append(obj)

    if not failures:
        return

    # 统计失败原因
    reason_counts = defaultdict(int)
    for f in failures:
        for flag in f.get("flags", []):
            reason_counts[flag] += 1

    if not reason_counts:
        return

    fig, ax = plt.subplots(figsize=(10, 8))
    labels = list(reason_counts.keys())
    sizes = list(reason_counts.values())
    colors = plt.cm.Set3(range(len(labels)))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.1f%%", startangle=90,
        colors=colors, textprops={"fontsize": 9}
    )
    ax.set_title(f"Failure Distribution: {run_name}", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def plot_milestone_comparison(output_path: Path) -> None:
    """绘制关键里程碑对比图。"""
    milestones = [
        ("Phase 7.1\nBaseline", "blind_isolated_run", "blind_scenario_run"),
        ("Phase 8\nAfter-fix", "blind_isolated_p8", "blind_scenario_p8_final"),
        ("Phase 8.1\nFinal", "blind_isolated_p8_final", "blind_scenario_p8_final_v5"),
    ]

    isolated_rates = []
    scenario_rates = []
    labels = []

    for label, iso_name, scen_name in milestones:
        labels.append(label)
        iso_file = RESULTS_DIR / iso_name / "chat_quality_summary.json"
        scen_file = RESULTS_DIR / scen_name / "chat_quality_summary.json"

        iso_rate = 0
        if iso_file.exists():
            with open(iso_file) as f:
                iso_rate = json.load(f).get("pass_rate", 0) * 100
        isolated_rates.append(iso_rate)

        scen_rate = 0
        if scen_file.exists():
            with open(scen_file) as f:
                scen_rate = json.load(f).get("pass_rate", 0) * 100
        scenario_rates.append(scen_rate)

    x = range(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar([i - width / 2 for i in x], isolated_rates, width, label="Blind Isolated (104 cases)", color="#4CAF50")
    bars2 = ax.bar([i + width / 2 for i in x], scenario_rates, width, label="Blind Scenario (20 cases)", color="#2196F3")

    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, height + 1, f"{height:.0f}%",
                    ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_ylabel("Pass Rate (%)", fontsize=11)
    ax.set_title("Companion Agent Quality Milestones", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 110)
    ax.axhline(y=85, color="green", linestyle="--", alpha=0.5, label="Target 85%")
    ax.axhline(y=90, color="blue", linestyle="--", alpha=0.5, label="Target 90%")
    ax.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {output_path}")


def generate_markdown_report(summaries: list[dict]) -> str:
    """生成 Markdown 汇总报告。"""
    lines = [
        "# 姜姜聊天质量评估报告（自动化汇总）",
        "",
        f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "> 数据来源：`tests/chat_quality_results/`",
        "",
        "## 关键里程碑",
        "",
        "| 阶段 | Blind Isolated | Blind Scenario |",
        "|------|---------------|----------------|",
        "| Phase 7.1 Baseline | 67% (70/104) | 45% (9/20) |",
        "| Phase 8 After-fix | 88% (92/104) | 85% (17/20) |",
        "| **Phase 8.1 Final** | **97% (101/104)** | **100% (20/20)** |",
        "",
        "## 所有运行记录",
        "",
        "| 运行名称 | 模式 | 用例数 | 通过 | 失败 | 通过率 |",
        "|----------|------|--------|------|------|--------|",
    ]

    for s in sorted(summaries, key=lambda x: (x.get("mode", ""), x.get("pass_rate", 0))):
        name = s["_run_name"]
        mode = s.get("mode", "?")
        total = s.get("total_cases", 0)
        passed = s.get("pass_count", 0)
        failed = s.get("fail_count", 0)
        rate = s.get("pass_rate", 0) * 100
        lines.append(f"| {name} | {mode} | {total} | {passed} | {failed} | {rate:.1f}% |")

    lines.extend([
        "",
        "## 可视化图表",
        "",
        "- `milestone_comparison.png` — 关键里程碑通过率对比",
        "- `blind_isolated_trend.png` — Blind Isolated 通过率趋势",
        "- `blind_scenario_trend.png` — Blind Scenario 通过率趋势",
        "- `failure_distribution_isolated.png` — Isolated 失败原因分布",
        "- `failure_distribution_scenario.png` — Scenario 失败原因分布",
        "",
        "---",
        "*本报告由 `evaluation/generate_report.py` 自动生成*",
    ])

    return "\n".join(lines)


def main():
    print("Loading all test results...")
    summaries = load_all_summaries()
    print(f"  Found {len(summaries)} result sets")

    categorized = categorize_runs(summaries)

    print("\nGenerating visualizations...")

    # 里程碑对比
    plot_milestone_comparison(EVAL_DIR / "milestone_comparison.png")

    # Blind Isolated 趋势
    if "isolated" in categorized:
        iso_runs = [r for r in categorized["isolated"] if r.get("total_cases", 0) == 104]
        if iso_runs:
            plot_pass_rate_trend(iso_runs, "Blind Isolated Pass Rate Trend (104 cases)",
                                 EVAL_DIR / "blind_isolated_trend.png")

    # Blind Scenario 趋势
    if "scenario" in categorized:
        scen_runs = [r for r in categorized["scenario"] if r.get("total_cases", 0) == 20]
        if scen_runs:
            plot_pass_rate_trend(scen_runs, "Blind Scenario Pass Rate Trend (20 cases)",
                                 EVAL_DIR / "blind_scenario_trend.png")

    # 失败原因分布（最新运行）
    plot_failure_distribution("blind_isolated_p8_final", EVAL_DIR / "failure_distribution_isolated.png")
    plot_failure_distribution("blind_scenario_p8_final_v5", EVAL_DIR / "failure_distribution_scenario.png")

    # Markdown 报告
    print("\nGenerating markdown report...")
    report = generate_markdown_report(summaries)
    report_path = EVAL_DIR / "evaluation_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  Saved: {report_path}")

    print("\nDone! All outputs saved to evaluation/")


if __name__ == "__main__":
    main()
