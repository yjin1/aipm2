from __future__ import annotations

import argparse
import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from aipm_data import (
    AIPMDataset,
    build_middle_schedule,
    format_schedule_datetime,
    parse_datetime,
    write_middle_schedule,
)


# What: Phase colors used across all report visuals.
# Purpose: Keeps Gantt, timeline, and flow diagrams visually consistent.
PHASE_COLORS = {
    "設計": "#2563eb",
    "ｿﾌﾄ": "#7c3aed",
    "生設": "#0891b2",
    "工作": "#ca8a04",
    "塗装": "#16a34a",
    "弱電": "#db2777",
    "組立": "#ea580c",
    "検査": "#dc2626",
    "出荷": "#475569",
    "部品": "#0f766e",
}

# What: Default phase color for unknown or new process groups.
# Purpose: Lets the visualizer handle future activity types gracefully.
DEFAULT_PHASE_COLOR = "#64748b"


# What: Command-line entry point for visual report generation.
# Purpose: Allows users and future agents to create schedule visuals from the current CSV data.
def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an AIPM schedule visual report.")
    parser.add_argument("--data-dir", default="data", help="Folder containing the AIPM CSV files.")
    parser.add_argument(
        "--output",
        default="outputs/aipm_schedule_report.html",
        help="HTML report path to write.",
    )
    parser.add_argument(
        "--schedule-output",
        default="outputs/generated_middle_schedule.csv",
        help="Generated middle-level schedule CSV path to write.",
    )
    args = parser.parse_args()

    dataset = AIPMDataset.from_data_dir(args.data_dir)
    generated_rows = build_middle_schedule(dataset)

    schedule_path = Path(args.schedule_output)
    schedule_path.parent.mkdir(parents=True, exist_ok=True)
    write_middle_schedule(generated_rows, schedule_path)

    report_path = Path(args.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_report_html(dataset, generated_rows, schedule_path),
        encoding="utf-8",
    )
    print(f"Generated report: {report_path}")
    print(f"Generated schedule CSV: {schedule_path}")
    return 0


# What: Full HTML report builder.
# Purpose: Combines all schedule visuals into one self-contained inspection artifact.
def build_report_html(
    dataset: AIPMDataset,
    generated_rows: list[dict[str, str]],
    schedule_path: Path,
    agent_findings: list[str] | None = None,
) -> str:
    comparisons = compare_with_reference(generated_rows, dataset.reference_schedule)
    summary = summarize(dataset, generated_rows, comparisons)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIPM Schedule Visual Report</title>
  <style>{report_css()}</style>
</head>
<body>
  <header>
    <div>
      <p class="eyebrow">AIPM Planning and Scheduling Agent</p>
      <h1>Middle-Level Plan and Schedule Visual Report</h1>
      <p class="subtle">Generated {escape(generated_at)} from current order, activity, resource, and reference schedule CSV files.</p>
    </div>
    <div class="meta">
      <span>Schedule CSV</span>
      <strong>{escape(str(schedule_path))}</strong>
    </div>
  </header>
  {dashboard_section(summary)}
  {agent_diagnosis_section(agent_findings or [])}
  {gantt_section(generated_rows)}
  {resource_load_section(generated_rows)}
  {order_timeline_section(generated_rows)}
  {comparison_section(comparisons, generated_rows, dataset.reference_schedule)}
  {field_rule_diagnostics_section(generated_rows, dataset.reference_schedule)}
  {timing_divergence_section(comparisons, generated_rows, dataset.reference_schedule)}
  {flow_section(dataset.activities)}
</body>
</html>
"""


# What: Process-management HTML report builder.
# Purpose: Separates execution monitoring and work-order examples from the main schedule report.
def build_process_management_report_html(
    schedule_rows: list[dict[str, str]],
    progress_rows: list[dict[str, str]] | None = None,
    schedule_report_url: str = "agent_schedule_report.html",
) -> str:
    from execution_management import monitor_execution
    from work_order_agent import demo_work_orders, generate_work_orders, render_work_order_card, work_order_css

    progress_rows = progress_rows or []
    monitor = monitor_execution(schedule_rows, progress_rows)
    work_orders = generate_work_orders(schedule_rows, progress_rows)
    summary = monitor.summary
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    finding_rows = "\n".join(
        f"""<tr>
          <td>{escape(finding.severity)}</td>
          <td>{escape(finding.wbs)}</td>
          <td>{escape(finding.operation_no)} {escape(finding.activity_name)}</td>
          <td>{escape(finding.status)}</td>
          <td>{escape(finding.message)}</td>
        </tr>"""
        for finding in monitor.findings[:30]
    )
    if not finding_rows:
        finding_rows = '<tr><td colspan="5">No execution exceptions detected.</td></tr>'
    cards = "\n".join(render_work_order_card(order) for order in demo_work_orders(work_orders, limit=8))
    if not cards:
        cards = "<p>No work-order examples were generated.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIPM Process Management Report</title>
  <style>{report_css()}{work_order_css()}</style>
</head>
<body>
  <header>
    <div>
      <p class="eyebrow">AIPM Process Management</p>
      <h1>Execution Status and Work Orders</h1>
      <p class="subtle">Generated {escape(generated_at)} from the current schedule and optional progress updates.</p>
    </div>
    <div class="meta">
      <a class="button-link" href="{escape(schedule_report_url)}">View Current Schedule</a>
    </div>
  </header>
  <section>
    <h2>Execution Status</h2>
    <div class="cards">
      <article class="card"><span>Progress Updates</span><strong>{summary.progress_rows}</strong></article>
      <article class="card"><span>Completed</span><strong>{summary.completed}</strong></article>
      <article class="card"><span>In Progress</span><strong>{summary.in_progress}</strong></article>
      <article class="card"><span>Blocked / Delayed</span><strong>{summary.blocked_or_delayed}</strong></article>
      <article class="card"><span>Late Unfinished</span><strong>{summary.late_unfinished}</strong></article>
    </div>
    {'' if monitor.has_progress else '<p class="subtle">No actual_progress.csv file was provided for this run.</p>'}
  </section>
  <section>
    <h2>Execution Exceptions</h2>
    <div class="panel scroll">
      <table>
        <thead><tr><th>Severity</th><th>WBS</th><th>Operation</th><th>Status</th><th>Message</th></tr></thead>
        <tbody>{finding_rows}</tbody>
      </table>
    </div>
  </section>
  <section>
    <h2>Generated Work Order Examples</h2>
    <div class="cards">{cards}</div>
  </section>
</body>
</html>"""


# What: Agent diagnosis HTML section.
# Purpose: Displays deterministic and GPT-backed findings when the report is produced by the agent.
def agent_diagnosis_section(findings: list[str]) -> str:
    if not findings:
        return ""
    short_findings = [finding for finding in findings if "\n" not in finding.strip()]
    rich_findings = [finding for finding in findings if "\n" in finding.strip()]
    short_items = "\n".join(f"<li>{_inline_markdown(finding)}</li>" for finding in short_findings)
    rich_items = "\n".join(
        f'<div class="diagnosis-markdown">{render_finding_html(finding)}</div>'
        for finding in rich_findings
    )
    short_block = f"<ul>{short_items}</ul>" if short_items else ""
    return f"""<section>
      <h2>AI Diagnosis</h2>
      <div class="panel diagnosis">
        {short_block}
        {rich_items}
      </div>
    </section>"""


# What: Dataset and schedule summary calculator.
# Purpose: Feeds the dashboard cards with compact management-level metrics.
def summarize(
    dataset: AIPMDataset,
    generated_rows: list[dict[str, str]],
    comparisons: list[dict[str, object]],
) -> dict[str, object]:
    overloaded = [row for row in generated_rows if row.get("負荷状態") == "1:OV"]
    late = []
    for row in generated_rows:
        finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
        due = parse_datetime(row.get("納期", ""))
        if finish and due and finish > due:
            late.append(row)

    start_deltas = [abs(int(item["start_delta_minutes"])) for item in comparisons if item["matched"]]
    avg_start_delta = sum(start_deltas) / len(start_deltas) if start_deltas else 0

    return {
        "orders": len(dataset.product_orders),
        "activities": len(generated_rows),
        "resources": len({row.get("資源ID", "") for row in generated_rows if row.get("資源ID")}),
        "overloaded": len(overloaded),
        "late": len(late),
        "reference_matches": sum(1 for item in comparisons if item["matched"]),
        "reference_total": len(comparisons),
        "exact_matches": sum(1 for item in comparisons if item["exact_match"]),
        "resource_matches": sum(1 for item in comparisons if item["resource_match"]),
        "avg_start_delta_hours": avg_start_delta / 60,
    }


# What: Generated-vs-reference schedule comparator.
# Purpose: Quantifies how the baseline schedule differs from the D6-style reference output.
def compare_with_reference(
    generated_rows: list[dict[str, str]], reference_rows: list[dict[str, str]]
) -> list[dict[str, object]]:
    reference_by_key = {_activity_key(row): row for row in reference_rows}
    comparisons: list[dict[str, object]] = []
    for row in generated_rows:
        key = _activity_key(row)
        reference = reference_by_key.get(key)
        generated_start = parse_datetime(row.get("スケジュール結果開始日時", ""))
        generated_finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
        reference_start = parse_datetime(reference.get("スケジュール結果開始日時", "")) if reference else None
        reference_finish = parse_datetime(reference.get("スケジュール結果終了日時", "")) if reference else None
        comparisons.append(
            {
                "key": key,
                "wbs": row.get("WBS", ""),
                "activity": row.get("作業工程名称", ""),
                "phase": row.get("基本工区名称", ""),
                "matched": reference is not None,
                "start_delta_minutes": _minute_delta(generated_start, reference_start),
                "finish_delta_minutes": _minute_delta(generated_finish, reference_finish),
                "resource_match": bool(reference and row.get("資源ID") == reference.get("資源ID")),
                "exact_match": bool(reference and all(row.get(column, "") == reference.get(column, "") for column in row)),
                "generated_start": format_schedule_datetime(generated_start) if generated_start else "",
                "generated_finish": format_schedule_datetime(generated_finish) if generated_finish else "",
                "reference_start": format_schedule_datetime(reference_start) if reference_start else "",
                "reference_finish": format_schedule_datetime(reference_finish) if reference_finish else "",
            }
        )
    return comparisons


# What: Per-column generated-vs-reference difference counter.
# Purpose: Shows which output fields still diverge from the given middle-level schedule.
def column_difference_counts(
    generated_rows: list[dict[str, str]], reference_rows: list[dict[str, str]]
) -> list[tuple[str, int]]:
    generated_by_key = {_activity_key(row): row for row in generated_rows}
    reference_by_key = {_activity_key(row): row for row in reference_rows}
    common_keys = set(generated_by_key) & set(reference_by_key)
    if not generated_rows or not common_keys:
        return []

    counts = []
    for column in generated_rows[0]:
        count = sum(
            1
            for key in common_keys
            if generated_by_key[key].get(column, "") != reference_by_key[key].get(column, "")
        )
        if count:
            counts.append((column, count))
    return sorted(counts, key=lambda item: item[1], reverse=True)


# What: Dashboard HTML section.
# Purpose: Presents the highest-level schedule health metrics before detailed visuals.
def dashboard_section(summary: dict[str, object]) -> str:
    cards = [
        ("Orders", summary["orders"]),
        ("Activities", summary["activities"]),
        ("Resources Used", summary["resources"]),
        ("Overload Flags", summary["overloaded"]),
        ("Late Activities", summary["late"]),
        (
            "Reference Matches",
            f"{summary['reference_matches']} / {summary['reference_total']}",
        ),
        ("Exact Row Matches", summary["exact_matches"]),
        (
            "Resource Matches",
            f"{summary['resource_matches']} / {summary['reference_total']}",
        ),
        ("Avg Start Delta", f"{summary['avg_start_delta_hours']:.1f} h"),
    ]
    card_html = "\n".join(
        f"""<article class="card">
          <span>{escape(label)}</span>
          <strong>{escape(str(value))}</strong>
        </article>"""
        for label, value in cards
    )
    return f"""<section>
      <h2>Dashboard Summary</h2>
      <div class="cards">{card_html}</div>
    </section>"""


# What: Gantt chart HTML section.
# Purpose: Shows each generated activity as a time bar grouped by WBS and process phase.
def gantt_section(rows: list[dict[str, str]]) -> str:
    return f"""<section>
      <h2>Gantt Chart</h2>
      <div class="panel scroll">{gantt_svg(rows)}</div>
    </section>"""


# What: Resource load HTML section.
# Purpose: Shows total scheduled workload by resource/team to reveal capacity pressure.
def resource_load_section(rows: list[dict[str, str]]) -> str:
    return f"""<section>
      <h2>Resource Load</h2>
      <div class="panel">{resource_load_svg(rows)}</div>
    </section>"""


# What: Order timeline HTML section.
# Purpose: Compresses activities into phase-level bars for each WBS order.
def order_timeline_section(rows: list[dict[str, str]]) -> str:
    return f"""<section>
      <h2>Order Timelines</h2>
      <div class="panel scroll">{order_timeline_svg(rows)}</div>
    </section>"""


# What: Plan-vs-reference comparison HTML section.
# Purpose: Highlights schedule deltas against the provided middle-level reference schedule.
def comparison_section(
    comparisons: list[dict[str, object]],
    generated_rows: list[dict[str, str]],
    reference_rows: list[dict[str, str]],
) -> str:
    mismatch_count = sum(1 for item in comparisons if not item["resource_match"])
    exact_count = sum(1 for item in comparisons if item["exact_match"])
    column_diffs = column_difference_counts(generated_rows, reference_rows)
    diff_rows = "\n".join(
        f"""<tr>
          <td>{escape(column)}</td>
          <td>{count}</td>
        </tr>"""
        for column, count in column_diffs
    )
    rows = sorted(
        [item for item in comparisons if item["matched"]],
        key=lambda item: abs(int(item["start_delta_minutes"])),
        reverse=True,
    )[:15]
    table_rows = "\n".join(
        f"""<tr>
          <td>{escape(str(item["wbs"]))}</td>
          <td>{escape(str(item["activity"]))}</td>
          <td>{escape(str(item["phase"]))}</td>
          <td>{int(item["start_delta_minutes"]) / 60:.1f}</td>
          <td>{int(item["finish_delta_minutes"]) / 60:.1f}</td>
          <td>{escape(str(item["generated_start"]))}</td>
          <td>{escape(str(item["reference_start"]))}</td>
          <td>{escape(str(item["generated_finish"]))}</td>
          <td>{escape(str(item["reference_finish"]))}</td>
        </tr>"""
        for item in rows
    )
    return f"""<section>
      <h2>Plan vs Reference Comparison</h2>
      <div class="comparison-cards">
        <article class="card"><span>Exact row matches</span><strong>{exact_count} / {len(comparisons)}</strong></article>
        <article class="card"><span>Resource mismatches</span><strong>{mismatch_count}</strong></article>
        <article class="card"><span>Columns with differences</span><strong>{len(column_diffs)}</strong></article>
      </div>
      <div class="split">
        <div class="panel">
          <h3>Largest Start-Time Differences</h3>
          {comparison_svg(comparisons)}
        </div>
        <div class="panel">
          <h3>Column Difference Counts</h3>
          <table>
            <thead><tr><th>Column</th><th>Differing Rows</th></tr></thead>
            <tbody>{diff_rows}</tbody>
          </table>
        </div>
      </div>
      <div class="panel compare-table">
        <h3>Largest Generated vs Given Timing Gaps</h3>
          <table>
            <thead>
              <tr><th>WBS</th><th>Activity</th><th>Phase</th><th>Start Delta (h)</th><th>Finish Delta (h)</th><th>Generated Start</th><th>Given Start</th><th>Generated Finish</th><th>Given Finish</th></tr>
            </thead>
            <tbody>{table_rows}</tbody>
          </table>
      </div>
    </section>"""


# What: Timing divergence HTML section.
# Purpose: Pinpoints the rows where generated timing is farthest from the given schedule.
def timing_divergence_section(
    comparisons: list[dict[str, object]],
    generated_rows: list[dict[str, str]],
    reference_rows: list[dict[str, str]],
) -> str:
    reference_by_key = {_activity_key(row): row for row in reference_rows}
    generated_by_key = {_activity_key(row): row for row in generated_rows}
    rows = sorted(
        [item for item in comparisons if item["matched"]],
        key=lambda item: max(
            abs(int(item["start_delta_minutes"])),
            abs(int(item["finish_delta_minutes"])),
        ),
        reverse=True,
    )[:20]
    table_rows = []
    for item in rows:
        key = item["key"]
        generated = generated_by_key.get(key, {})
        reference = reference_by_key.get(key, {})
        cause = classify_visual_divergence(generated, reference, item)
        table_rows.append(
            f"""<tr>
              <td>{escape(str(item["wbs"]))}</td>
              <td>{escape(str(item["activity"]))}</td>
              <td>{escape(str(item["phase"]))}</td>
              <td>{int(item["start_delta_minutes"]) / 60:.1f}</td>
              <td>{int(item["finish_delta_minutes"]) / 60:.1f}</td>
              <td>{escape(cause)}</td>
            </tr>"""
        )
    return f"""<section>
      <h2>Timing Divergence Diagnostics</h2>
      <div class="panel compare-table">
        <table>
          <thead>
            <tr><th>WBS</th><th>Activity</th><th>Phase</th><th>Start Delta (h)</th><th>Finish Delta (h)</th><th>Likely Cause</th></tr>
          </thead>
          <tbody>{''.join(table_rows)}</tbody>
        </table>
      </div>
    </section>"""


# What: Field-rule diagnostics HTML section.
# Purpose: Counts mismatches in status/flag fields that strongly affect schedule interpretation.
def field_rule_diagnostics_section(
    generated_rows: list[dict[str, str]], reference_rows: list[dict[str, str]]
) -> str:
    fields = [
        "工程計画内外区分",
        "負荷状態",
        "最早最遅逆転救済対象工程",
        "スケジュール状態",
    ]
    reference_by_key = {_activity_key(row): row for row in reference_rows}
    generated_by_key = {_activity_key(row): row for row in generated_rows}
    common_keys = sorted(set(reference_by_key) & set(generated_by_key))
    rows = []
    for field_name in fields:
        mismatch_count = sum(
            1
            for key in common_keys
            if generated_by_key[key].get(field_name, "") != reference_by_key[key].get(field_name, "")
        )
        match_count = len(common_keys) - mismatch_count
        rows.append(
            f"""<tr>
              <td>{escape(field_name)}</td>
              <td>{match_count}</td>
              <td>{mismatch_count}</td>
              <td>{match_count / len(common_keys) * 100 if common_keys else 0:.1f}%</td>
            </tr>"""
        )
    return f"""<section>
      <h2>Field Rule Diagnostics</h2>
      <div class="panel">
        <table>
          <thead><tr><th>Field</th><th>Matches</th><th>Mismatches</th><th>Match Rate</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>"""


# What: Process-flow HTML section.
# Purpose: Visualizes the operation sequence by operation number as a planning logic map.
def flow_section(activities: list[dict[str, str]]) -> str:
    return f"""<section>
      <h2>Process Flow</h2>
      <div class="panel scroll">{process_flow_svg(activities)}</div>
    </section>"""


# What: SVG Gantt renderer.
# Purpose: Converts activity start/end times into scaled horizontal bars.
def gantt_svg(rows: list[dict[str, str]]) -> str:
    dated_rows = _rows_with_dates(rows)
    if not dated_rows:
        return "<p>No scheduled rows to display.</p>"
    start, finish = _date_extent(dated_rows)
    width = 1500
    left = 260
    top = 48
    row_h = 24
    height = top + len(dated_rows) * row_h + 42
    scale_width = width - left - 40
    parts = [_svg_header(width, height)]
    parts.append(_time_axis(start, finish, left, 24, scale_width))
    for index, row in enumerate(dated_rows):
        y = top + index * row_h
        phase = row["基本工区名称"]
        x = left + _time_ratio(row["_start"], start, finish) * scale_width
        x2 = left + _time_ratio(row["_finish"], start, finish) * scale_width
        bar_w = max(2, x2 - x)
        label = f"{row['WBS']} | {row['作業工程名称']}"
        parts.append(f'<text x="10" y="{y + 14}" class="axis-label">{escape(label)}</text>')
        parts.append(
            f'<rect x="{x:.1f}" y="{y + 4}" width="{bar_w:.1f}" height="14" rx="3" fill="{_phase_color(phase)}"/>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


# What: SVG resource-load renderer.
# Purpose: Aggregates generated schedule durations by resource and draws a ranked bar chart.
def resource_load_svg(rows: list[dict[str, str]]) -> str:
    load: dict[str, float] = defaultdict(float)
    for row in _rows_with_dates(rows):
        label = f"{row.get('資源ID', '')} {row.get('資源名称', '')}".strip()
        load[label] += (row["_finish"] - row["_start"]).total_seconds() / 3600
    ranked = sorted(load.items(), key=lambda item: item[1], reverse=True)[:25]
    width = 980
    left = 230
    row_h = 28
    height = 44 + len(ranked) * row_h
    max_hours = max((value for _, value in ranked), default=1)
    parts = [_svg_header(width, height)]
    for index, (label, hours) in enumerate(ranked):
        y = 30 + index * row_h
        bar_w = (width - left - 90) * hours / max_hours
        parts.append(f'<text x="10" y="{y + 14}" class="axis-label">{escape(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="16" rx="3" fill="#2563eb"/>')
        parts.append(f'<text x="{left + bar_w + 8:.1f}" y="{y + 13}" class="value-label">{hours:.1f} h</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# What: SVG order-timeline renderer.
# Purpose: Shows phase spans for each order after aggregating activities by WBS and basic process area.
def order_timeline_svg(rows: list[dict[str, str]]) -> str:
    dated_rows = _rows_with_dates(rows)
    start, finish = _date_extent(dated_rows)
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in dated_rows:
        grouped[(row["WBS"], row["基本工区名称"])].append(row)
    wbs_values = sorted({row["WBS"] for row in dated_rows})
    width = 1300
    left = 230
    row_h = 42
    height = 58 + len(wbs_values) * row_h
    scale_width = width - left - 60
    parts = [_svg_header(width, height)]
    parts.append(_time_axis(start, finish, left, 24, scale_width))
    for index, wbs in enumerate(wbs_values):
        y = 52 + index * row_h
        parts.append(f'<text x="10" y="{y + 16}" class="axis-label">{escape(wbs)}</text>')
        for (group_wbs, phase), group_rows in grouped.items():
            if group_wbs != wbs:
                continue
            phase_start = min(row["_start"] for row in group_rows)
            phase_finish = max(row["_finish"] for row in group_rows)
            x = left + _time_ratio(phase_start, start, finish) * scale_width
            x2 = left + _time_ratio(phase_finish, start, finish) * scale_width
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{max(3, x2 - x):.1f}" height="20" rx="4" fill="{_phase_color(phase)}"/>'
            )
            parts.append(f'<text x="{x + 4:.1f}" y="{y + 15}" class="bar-label">{escape(phase)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# What: SVG comparison renderer.
# Purpose: Draws the largest generated-vs-reference start-time differences.
def comparison_svg(comparisons: list[dict[str, object]]) -> str:
    rows = sorted(
        [item for item in comparisons if item["matched"]],
        key=lambda item: abs(int(item["start_delta_minutes"])),
        reverse=True,
    )[:20]
    width = 980
    left = 260
    center = 600
    row_h = 28
    height = 44 + len(rows) * row_h
    max_abs = max((abs(int(item["start_delta_minutes"])) for item in rows), default=0)
    if max_abs == 0:
        return '<p class="statline">Generated schedule start times match the given reference for all compared rows.</p>'
    parts = [_svg_header(width, height)]
    parts.append(f'<line x1="{center}" y1="20" x2="{center}" y2="{height - 16}" stroke="#94a3b8"/>')
    for index, item in enumerate(rows):
        y = 30 + index * row_h
        delta = int(item["start_delta_minutes"]) / 60
        bar_w = 300 * abs(delta * 60) / max_abs
        x = center if delta >= 0 else center - bar_w
        color = "#dc2626" if delta >= 0 else "#16a34a"
        label = f"{item['wbs']} | {item['activity']}"
        parts.append(f'<text x="10" y="{y + 14}" class="axis-label">{escape(label)}</text>')
        parts.append(f'<rect x="{x:.1f}" y="{y}" width="{bar_w:.1f}" height="16" rx="3" fill="{color}"/>')
        parts.append(f'<text x="{center + 310}" y="{y + 13}" class="value-label">{delta:.1f} h</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# What: SVG process-flow renderer.
# Purpose: Draws the unique operation sequence as connected phase-colored boxes.
def process_flow_svg(activities: list[dict[str, str]]) -> str:
    unique: dict[str, dict[str, str]] = {}
    for activity in activities:
        key = activity.get("工程NO", "")
        unique.setdefault(key, activity)
    operations = sorted(unique.values(), key=lambda row: int(row.get("工程NO", "0") or 0))
    box_w = 170
    box_h = 58
    gap_x = 34
    gap_y = 34
    cols = 5
    rows = (len(operations) + cols - 1) // cols
    width = cols * box_w + (cols - 1) * gap_x + 40
    height = rows * box_h + (rows - 1) * gap_y + 40
    parts = [_svg_header(width, height)]
    centers = []
    for index, operation in enumerate(operations):
        col = index % cols
        row = index // cols
        x = 20 + col * (box_w + gap_x)
        y = 20 + row * (box_h + gap_y)
        centers.append((x + box_w, y + box_h / 2, x, y + box_h / 2))
        phase = operation.get("基本工区名称", "")
        title = f"{operation.get('工程NO', '')} {operation.get('作業工程名称', '')}"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="6" fill="{_phase_color(phase)}" opacity="0.92"/>'
        )
        parts.append(f'<text x="{x + 10}" y="{y + 22}" class="flow-label">{escape(title[:18])}</text>')
        parts.append(f'<text x="{x + 10}" y="{y + 43}" class="flow-sub">{escape(phase)}</text>')
    for index in range(len(operations) - 1):
        x1, y1, _, _ = centers[index]
        _, _, x2, y2 = centers[index + 1]
        if (index + 1) % cols == 0:
            continue
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#64748b" marker-end="url(#arrow)"/>')
    parts.insert(
        1,
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="#64748b"/></marker></defs>',
    )
    parts.append("</svg>")
    return "\n".join(parts)


# What: CSS stylesheet provider.
# Purpose: Keeps the generated HTML report readable without external assets.
def report_css() -> str:
    return """
    :root { color-scheme: light; --ink: #0f172a; --muted: #64748b; --line: #e2e8f0; --bg: #f8fafc; --panel: #ffffff; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg); }
    header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; padding: 32px 40px 20px; border-bottom: 1px solid var(--line); background: #fff; }
    h1 { margin: 0; font-size: 30px; line-height: 1.15; letter-spacing: 0; }
    h2 { margin: 0 0 14px; font-size: 20px; letter-spacing: 0; }
    h3 { margin: 0 0 12px; font-size: 14px; letter-spacing: 0; color: #334155; }
    section { padding: 24px 40px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: #334155; background: #f8fafc; }
    .eyebrow { margin: 0 0 8px; font-size: 12px; font-weight: 700; text-transform: uppercase; color: #2563eb; }
    .subtle { margin: 8px 0 0; color: var(--muted); }
    .meta { min-width: 260px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 8px; background: #f8fafc; }
    .meta span { display: block; color: var(--muted); font-size: 12px; }
    .meta strong { display: block; margin-top: 4px; font-size: 13px; overflow-wrap: anywhere; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
    .comparison-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }
    .card, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
    .card { padding: 16px; }
    .card span { display: block; color: var(--muted); font-size: 12px; }
    .card strong { display: block; margin-top: 8px; font-size: 26px; }
    .panel { padding: 14px; overflow: hidden; }
    .scroll { overflow-x: auto; }
    .split { display: grid; grid-template-columns: minmax(420px, 1fr) minmax(420px, 1fr); gap: 16px; align-items: start; }
    .compare-table { margin-top: 16px; overflow-x: auto; }
    .statline { margin: 0 0 12px; color: var(--muted); }
    .diagnosis ul { margin: 0; padding-left: 20px; }
    .diagnosis li { margin: 8px 0; line-height: 1.45; }
    .diagnosis > ul { margin-bottom: 18px; }
    .diagnosis-markdown { border-top: 1px solid var(--line); padding-top: 16px; }
    .diagnosis-markdown h3 { margin: 18px 0 8px; font-size: 17px; color: #0f172a; }
    .diagnosis-markdown h3:first-child { margin-top: 0; }
    .diagnosis-markdown h4 { margin: 14px 0 6px; font-size: 14px; color: #1e293b; }
    .diagnosis-markdown h4 span { color: #2563eb; }
    .diagnosis-markdown p { margin: 8px 0; line-height: 1.5; }
    .diagnosis-markdown ul { margin: 6px 0 12px; }
    code { padding: 1px 5px; border-radius: 4px; background: #f1f5f9; color: #0f172a; }
    svg { display: block; max-width: none; }
    .axis-label { font-size: 11px; fill: #334155; }
    .value-label { font-size: 11px; fill: #475569; }
    .bar-label { font-size: 10px; fill: #fff; font-weight: 700; pointer-events: none; }
    .flow-label { font-size: 12px; fill: #fff; font-weight: 700; }
    .flow-sub { font-size: 11px; fill: #e2e8f0; }
    @media (max-width: 900px) { header { display: block; padding: 24px; } section { padding: 20px 24px; } .meta { margin-top: 16px; } .split { grid-template-columns: 1fr; } }
    """


# What: HTML escaping helper.
# Purpose: Prevents source CSV text from breaking generated report markup.
def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


# What: Finding renderer for report diagnosis text.
# Purpose: Converts GPT-style Markdown snippets into readable, safe HTML inside the report.
def render_finding_html(value: str) -> str:
    import re

    text = str(value).strip()
    if "\n" not in text and not text.startswith("#"):
        return _inline_markdown(text)

    blocks = []
    list_open = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            continue
        heading = re.match(r"^(#{2,4})\s+(.+)$", line)
        numbered = re.match(r"^(\d+)[.)]\s+(.+)$", line)
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if heading:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            blocks.append(f"<h3>{_inline_markdown(heading.group(2))}</h3>")
        elif numbered:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            blocks.append(
                f'<h4><span>{numbered.group(1)}.</span> {_inline_markdown(numbered.group(2))}</h4>'
            )
        elif bullet:
            if not list_open:
                blocks.append("<ul>")
                list_open = True
            blocks.append(f"<li>{_inline_markdown(bullet.group(1))}</li>")
        else:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            blocks.append(f"<p>{_inline_markdown(line)}</p>")
    if list_open:
        blocks.append("</ul>")
    return "\n".join(blocks)


# What: Inline Markdown renderer.
# Purpose: Supports bold and code spans while escaping all source text first.
def _inline_markdown(value: str) -> str:
    escaped = escape(value)
    escaped = re_sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re_sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


# What: Regex substitution wrapper.
# Purpose: Keeps regex import local to rendering behavior and easy to test.
def re_sub(pattern: str, replacement: str, value: str) -> str:
    import re

    return re.sub(pattern, replacement, value)


# What: Activity identity helper.
# Purpose: Matches generated and reference rows using stable scheduling fields.
def _activity_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("WBS", ""),
        row.get("部品NO", ""),
        row.get("工程NO", ""),
        row.get("作業工程ID", ""),
    )


# What: Visual divergence cause classifier.
# Purpose: Mirrors agent diagnostics without importing the agent module into the visualizer.
def classify_visual_divergence(
    generated: dict[str, str], reference: dict[str, str], comparison: dict[str, object]
) -> str:
    if generated.get("資源ID", "") != reference.get("資源ID", ""):
        return "resource assignment mismatch"
    if generated.get("最早最遅逆転救済対象工程", "") != reference.get("最早最遅逆転救済対象工程", ""):
        return "earliest/latest relief flag mismatch"
    if generated.get("負荷状態", "") != reference.get("負荷状態", ""):
        return "load-state mismatch"
    if generated.get("工程計画内外区分", "") != reference.get("工程計画内外区分", ""):
        return "internal/external planning classification mismatch"
    start_delta = int(comparison["start_delta_minutes"]) / 60
    finish_delta = int(comparison["finish_delta_minutes"]) / 60
    if abs(start_delta - finish_delta) < 1:
        return "phase anchor or due-date offset mismatch"
    return "dependency/calendar propagation mismatch"


# What: Datetime delta helper.
# Purpose: Reports generated-vs-reference differences in whole minutes.
def _minute_delta(left: datetime | None, right: datetime | None) -> int:
    if not left or not right:
        return 0
    return int((left - right).total_seconds() // 60)


# What: Schedule row date enricher.
# Purpose: Filters rows that have usable start and finish datetimes for chart rendering.
def _rows_with_dates(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    dated_rows = []
    for row in rows:
        start = parse_datetime(row.get("スケジュール結果開始日時", ""))
        finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
        if start and finish:
            copy = dict(row)
            copy["_start"] = start
            copy["_finish"] = finish
            dated_rows.append(copy)
    return dated_rows


# What: Date extent helper.
# Purpose: Finds chart scale boundaries for rows with parsed datetimes.
def _date_extent(rows: list[dict[str, object]]) -> tuple[datetime, datetime]:
    start = min(row["_start"] for row in rows)
    finish = max(row["_finish"] for row in rows)
    return start, finish


# What: Time scale helper.
# Purpose: Maps datetimes into a 0-to-1 chart coordinate ratio.
def _time_ratio(value: datetime, start: datetime, finish: datetime) -> float:
    total = max(1, (finish - start).total_seconds())
    return (value - start).total_seconds() / total


# What: SVG header helper.
# Purpose: Starts each inline SVG with consistent sizing and namespace attributes.
def _svg_header(width: int, height: int) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'


# What: Time-axis SVG helper.
# Purpose: Draws evenly spaced date labels for timeline-based charts.
def _time_axis(start: datetime, finish: datetime, left: int, y: int, width: int) -> str:
    parts = []
    ticks = 6
    for index in range(ticks + 1):
        ratio = index / ticks
        tick_time = start + (finish - start) * ratio
        x = left + ratio * width
        parts.append(f'<line x1="{x:.1f}" y1="{y}" x2="{x:.1f}" y2="{y + 10}" stroke="#cbd5e1"/>')
        parts.append(f'<text x="{x - 34:.1f}" y="{y - 6}" class="value-label">{tick_time.strftime("%m/%d")}</text>')
    return "\n".join(parts)


# What: Phase color lookup.
# Purpose: Assigns stable colors to process phases while tolerating future phase names.
def _phase_color(phase: str) -> str:
    return PHASE_COLORS.get(phase, DEFAULT_PHASE_COLOR)


if __name__ == "__main__":
    raise SystemExit(main())
