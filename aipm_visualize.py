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
      <p class="subtle">Generated {escape(generated_at)} from current order, activity, resource, and optional reference/progress CSV files.</p>
      <a class="button-link" href="process_management_report.html">View Process Panel</a>
    </div>
    <div class="meta">
      <span>Schedule CSV</span>
      <strong>{escape(str(schedule_path))}</strong>
    </div>
  </header>
  {dashboard_section(summary)}
  {agent_diagnosis_section(agent_findings or [])}
  {feasibility_validation_section(dataset, generated_rows)}
  {comparison_section(comparisons, generated_rows, dataset.reference_schedule)}
  {field_rule_diagnostics_section(generated_rows, dataset.reference_schedule)}
  {resource_load_section(generated_rows)}
  {gantt_section(generated_rows)}
  {order_timeline_section(generated_rows)}
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
    from work_order_agent import generate_work_orders, render_work_order_card, work_order_css

    progress_rows = progress_rows or []
    monitor = monitor_execution(schedule_rows, progress_rows)
    work_orders = generate_work_orders(schedule_rows, progress_rows)
    summary = monitor.summary
    downstream_at_risk = _downstream_at_risk_count(schedule_rows, progress_rows)
    manager_actions = _manager_action_items(monitor.findings, downstream_at_risk, monitor.has_progress)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    finding_rows = "\n".join(
        f"""<tr>
          <td>{_severity_badge(finding.severity)}</td>
          <td>{escape(finding.wbs)}</td>
          <td>{escape(finding.operation_no)}</td>
          <td>{escape(finding.activity_name)}</td>
          <td>{escape(finding.status)}</td>
          <td>{escape(finding.planned_finish)}</td>
          <td>{escape(finding.actual_finish or '-')}</td>
          <td>{escape(finding.message)}</td>
        </tr>"""
        for finding in monitor.findings[:30]
    )
    if not finding_rows:
        finding_rows = '<tr><td colspan="8">No execution exceptions detected.</td></tr>'
    action_items = "\n".join(f"<li>{escape(item)}</li>" for item in manager_actions)
    updated_work_orders = [
        order
        for order in work_orders
        if order.execution_status.casefold() != "not_reported"
    ]
    cards = "\n".join(render_work_order_card(order) for order in updated_work_orders[:12])
    if not cards:
        cards = '<p class="statline">No updated work orders are shown because no progress rows were reported for scheduled operations.</p>'

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
      <p class="eyebrow">AIPM Process Management Agent</p>
      <h1>Execution Monitoring and Work Orders</h1>
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
      <article class="card"><span>Overdue Unfinished</span><strong>{summary.late_unfinished}</strong></article>
      <article class="card"><span>Downstream At Risk</span><strong>{downstream_at_risk}</strong></article>
    </div>
    {'' if monitor.has_progress else '<p class="subtle">No actual_progress.csv file was provided for this run.</p>'}
  </section>
  <section>
    <h2>Management Focus</h2>
    <div class="split">
      <div class="panel diagnosis">
        <h3>Immediate Actions</h3>
        <ul>{action_items}</ul>
      </div>
      <div class="panel diagnosis">
        <h3>Progress Coverage</h3>
        <p class="statline">{_progress_coverage_text(len(schedule_rows), summary.progress_rows, monitor.has_progress)}</p>
        <p class="statline">{_risk_summary_text(summary.blocked_or_delayed, summary.late_unfinished, downstream_at_risk)}</p>
      </div>
    </div>
  </section>
  <section>
    <h2>Execution Exceptions</h2>
    <div class="panel scroll">
      <table>
        <thead><tr><th>Severity</th><th>WBS</th><th>Operation</th><th>Activity</th><th>Status</th><th>Planned Finish</th><th>Actual Finish</th><th>Message</th></tr></thead>
        <tbody>{finding_rows}</tbody>
      </table>
    </div>
  </section>
  <section>
    <h2>Updated Work Orders</h2>
    <p class="statline">This section lists only work orders touched by actual progress updates, such as completed, in-progress, blocked, or delayed operations. It is intentionally empty when no progress has been reported.</p>
    <div class="work-order-grid">{cards}</div>
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


# What: Process-report severity badge renderer.
# Purpose: Makes execution exception severity scannable for managers.
def _severity_badge(severity: str) -> str:
    normalized = severity.casefold()
    if normalized == "critical":
        css_class = "status-violated"
    elif normalized == "warning":
        css_class = "status-warning"
    else:
        css_class = "status-passed"
    return f'<span class="status-pill {css_class}">{escape(severity.title())}</span>'


# What: Downstream risk estimator.
# Purpose: Counts unfinished downstream operations in the same WBS after blocked or delayed progress rows.
def _downstream_at_risk_count(
    schedule_rows: list[dict[str, str]],
    progress_rows: list[dict[str, str]],
) -> int:
    if not progress_rows:
        return 0
    blocked_keys = {
        _process_key(row)
        for row in progress_rows
        if str(row.get("状態", "")).casefold() in {"blocked", "delayed", "遅延", "停止", "保留"}
    }
    if not blocked_keys:
        return 0
    progress_by_key = {_process_key(row): row for row in progress_rows}
    schedule_by_wbs: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in schedule_rows:
        schedule_by_wbs[row.get("WBS", "")].append(row)
    risk_keys = set()
    for wbs, _part_no, operation_no, _activity_id in blocked_keys:
        try:
            blocked_operation = int(operation_no)
        except ValueError:
            blocked_operation = -1
        for row in schedule_by_wbs.get(wbs, []):
            key = _process_key(row)
            if key in progress_by_key:
                continue
            try:
                operation = int(row.get("工程NO", ""))
            except ValueError:
                operation = -1
            if operation > blocked_operation:
                risk_keys.add(key)
    return len(risk_keys)


# What: Process-row key.
# Purpose: Matches schedule and progress rows without importing execution internals into the visualizer.
def _process_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("WBS", ""),
        row.get("部品NO", ""),
        row.get("工程NO", ""),
        row.get("作業工程ID", ""),
    )


# What: Manager action list builder.
# Purpose: Turns execution findings into short operational next steps.
def _manager_action_items(findings, downstream_at_risk: int, has_progress: bool) -> list[str]:
    if not has_progress:
        return [
            "Upload actual_progress.csv to activate execution monitoring.",
            "Use the progress-template CSV so each workgroup reports status with the correct schedule keys.",
            "Review generated work orders as planned dispatch candidates, not live execution evidence.",
        ]
    critical = [finding for finding in findings if finding.severity.casefold() == "critical"]
    warning = [finding for finding in findings if finding.severity.casefold() == "warning"]
    actions: list[str] = []
    if critical:
        actions.append(f"Resolve {len(critical)} critical blocked/delayed execution exceptions before dispatching dependent work.")
    if warning:
        actions.append(f"Review {len(warning)} warning item(s), especially completed-late operations that may shift downstream assumptions.")
    if downstream_at_risk:
        actions.append(f"Check {downstream_at_risk} downstream operation(s) at risk from blocked or delayed predecessors.")
    actions.append("Refresh actual_progress.csv after workgroup updates and rerun the progress scenario.")
    return actions


# What: Progress coverage text.
# Purpose: Explains how much of the schedule is covered by actual progress rows.
def _progress_coverage_text(total_rows: int, progress_rows: int, has_progress: bool) -> str:
    if not has_progress:
        return "No progress file was provided, so this panel shows planned dispatch only."
    coverage = progress_rows / total_rows * 100 if total_rows else 0
    return f"{progress_rows} of {total_rows} scheduled operations have progress updates ({coverage:.1f}% coverage)."


# What: Process risk summary text.
# Purpose: Provides a compact management interpretation of execution risk.
def _risk_summary_text(blocked: int, late_unfinished: int, downstream_at_risk: int) -> str:
    if not any([blocked, late_unfinished, downstream_at_risk]):
        return "No blocked, delayed, or downstream-at-risk operations were detected from the supplied progress file."
    return (
        f"{blocked} blocked/delayed operation(s), {late_unfinished} overdue unfinished operation(s), "
        f"and {downstream_at_risk} downstream operation(s) should be reviewed."
    )


# What: Dataset and schedule summary calculator.
# Purpose: Feeds the dashboard cards with compact management-level metrics.
def summarize(
    dataset: AIPMDataset,
    generated_rows: list[dict[str, str]],
    comparisons: list[dict[str, object]],
) -> dict[str, object]:
    overloaded = [row for row in generated_rows if row.get("負荷状態") == "1:OV"]
    late_orders: dict[str, float] = {}
    for row in generated_rows:
        finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
        due = parse_datetime(row.get("納期", ""))
        if finish and due and finish > due:
            late_orders[row.get("WBS", "")] = max(
                late_orders.get(row.get("WBS", ""), 0),
                (finish - due).total_seconds() / 3600,
            )

    start_deltas = [abs(int(item["start_delta_minutes"])) for item in comparisons if item["matched"]]
    finish_deltas = [abs(int(item["finish_delta_minutes"])) for item in comparisons if item["matched"]]
    avg_start_delta = sum(start_deltas) / len(start_deltas) if start_deltas else 0
    avg_finish_delta = sum(finish_deltas) / len(finish_deltas) if finish_deltas else 0
    dated_rows = _rows_with_dates(generated_rows)
    makespan_hours = 0.0
    if dated_rows:
        start, finish = _date_extent(dated_rows)
        makespan_hours = (finish - start).total_seconds() / 3600

    return {
        "orders": len(dataset.product_orders),
        "activities": len(generated_rows),
        "resources": len({row.get("資源ID", "") for row in generated_rows if row.get("資源ID")}),
        "overloaded": len(overloaded),
        "late_orders": len([wbs for wbs in late_orders if wbs]),
        "total_tardiness_hours": sum(late_orders.values()),
        "max_tardiness_hours": max(late_orders.values(), default=0),
        "makespan_hours": makespan_hours,
        "domain_rule_violations": len(_domain_precedence_violations(generated_rows)),
        "reference_matches": sum(1 for item in comparisons if item["matched"]),
        "reference_total": len(comparisons),
        "reference_available": bool(dataset.reference_schedule),
        "exact_matches": sum(1 for item in comparisons if item["exact_match"]),
        "resource_matches": sum(1 for item in comparisons if item["resource_match"]),
        "avg_start_delta_hours": avg_start_delta / 60,
        "avg_finish_delta_hours": avg_finish_delta / 60,
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
    profile_cards = [
        ("Orders", summary["orders"]),
        ("Activities", summary["activities"]),
        ("Resources Used", summary["resources"]),
    ]
    quality_cards = [
        ("Late Orders", summary["late_orders"]),
        ("Total Tardiness", f"{float(summary['total_tardiness_hours']):.1f} h"),
        ("Max Tardiness", f"{float(summary['max_tardiness_hours']):.1f} h"),
        ("Overload Flags", summary["overloaded"]),
        ("Domain Rule Violations", summary["domain_rule_violations"]),
        ("Makespan", f"{float(summary['makespan_hours']):.1f} h"),
    ]
    if summary["reference_available"]:
        reference_cards = [
            ("Reference Matches", f"{summary['reference_matches']} / {summary['reference_total']}"),
            ("Exact Row Matches", summary["exact_matches"]),
            ("Resource Matches", f"{summary['resource_matches']} / {summary['reference_total']}"),
            ("Avg Start Delta", f"{float(summary['avg_start_delta_hours']):.1f} h"),
            ("Avg Finish Delta", f"{float(summary['avg_finish_delta_hours']):.1f} h"),
        ]
    else:
        reference_cards = [
            ("Reference Matches", "No reference provided"),
            ("Exact Row Matches", "N/A"),
            ("Resource Matches", "N/A"),
            ("Avg Start Delta", "N/A"),
            ("Avg Finish Delta", "N/A"),
        ]

    return f"""<section>
      <h2>Dashboard Summary</h2>
      <div class="dashboard-block">
        <h3>Schedule Profile</h3>
        <div class="cards">{_cards_html(profile_cards)}</div>
      </div>
      <div class="dashboard-block primary">
        <h3>Schedule Quality</h3>
        <p class="statline">Primary measures of schedule health, independent of exact reference reconstruction.</p>
        <div class="cards">{_cards_html(quality_cards)}</div>
      </div>
      <div class="dashboard-block secondary">
        <h3>Reference Comparison</h3>
        <p class="statline">Secondary measures showing how closely the generated schedule reconstructs the provided middle schedule when a reference is available.</p>
        <div class="cards">{_cards_html(reference_cards)}</div>
      </div>
    </section>"""


# What: Metric-card renderer.
# Purpose: Keeps dashboard card markup consistent across profile, quality, and comparison groups.
def _cards_html(cards: list[tuple[str, object]]) -> str:
    return "\n".join(
        f"""<article class="card">
          <span>{escape(label)}</span>
          <strong>{escape(str(value))}</strong>
        </article>"""
        for label, value in cards
    )


# What: Feasibility validation report section.
# Purpose: Checks the generated schedule against encoded production constraints, not against the reference schedule.
def feasibility_validation_section(dataset: AIPMDataset, rows: list[dict[str, str]]) -> str:
    overload_rows = [row for row in rows if row.get("負荷状態") == "1:OV"]
    capacity_conflicts = _capacity_conflicts(dataset, rows)
    precedence_violations = _domain_precedence_violations(rows)
    overlaps = _same_phase_overlaps(rows)
    cards = [
        ("Overload Rows", len(overload_rows), "Review" if overload_rows else "Passed", "status-warning" if overload_rows else "status-passed"),
        ("Capacity Conflicts", len(capacity_conflicts), "Failed" if capacity_conflicts else "Passed", "status-violated" if capacity_conflicts else "status-passed"),
        ("Domain Precedence Violations", len(precedence_violations), "Failed" if precedence_violations else "Passed", "status-violated" if precedence_violations else "status-passed"),
        ("Same-Phase Overlap Reviews", len(overlaps), "Review" if overlaps else "Passed", "status-warning" if overlaps else "status-passed"),
    ]
    card_html = "\n".join(
        f"""<article class="rule-card">
          <h4>{escape(label)}</h4>
          <div class="rule-metrics">
            <span><strong>{count}</strong> findings</span>
            <span><span class="status-pill {status_class}">{escape(status)}</span></span>
          </div>
        </article>"""
        for label, count, status, status_class in cards
    )
    return f"""<section class="report-group">
      <h2>Feasibility Validation</h2>
      <p class="statline">This section checks whether the generated schedule is trustworthy under the currently encoded production constraints. It is intentionally stricter than reference comparison.</p>
      <div class="rule-grid">{card_html}</div>
      {_capacity_conflicts_section(capacity_conflicts)}
      {_precedence_violations_section(precedence_violations)}
      {_overload_rows_section(overload_rows)}
      {_same_phase_overlaps_section(overlaps)}
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
    if not reference_rows:
        return """<section>
      <h2>Reference Comparison</h2>
      <div class="panel">
        <p class="statline">No reference schedule was provided. AIPM2 generated the schedule from order, activity, resource, and encoded domain-rule inputs only.</p>
      </div>
    </section>"""
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
    if not reference_rows:
        return ""
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
    if not reference_rows:
        return """<section>
      <h2>Field Rule Diagnostics</h2>
      <div class="panel diagnosis">
        <p class="statline">No reference schedule was provided, so field-level generated-vs-reference diagnostics are not available for this run.</p>
      </div>
    </section>"""
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
      <div class="panel diagnosis">
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


# What: Capacity conflict detector.
# Purpose: Finds resource time points where overlapping generated work exceeds resource capacity.
def _capacity_conflicts(dataset: AIPMDataset, rows: list[dict[str, str]]) -> list[dict[str, object]]:
    resource_lookup = dataset.resources_by_id
    conflicts: list[dict[str, object]] = []
    rows_by_resource: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in _rows_with_dates(rows):
        resource_id = str(row.get("資源ID", ""))
        if resource_id:
            rows_by_resource[resource_id].append(row)
    for resource_id, resource_rows in rows_by_resource.items():
        try:
            capacity = float(resource_lookup.get(resource_id, {}).get("保有量", "") or 1)
        except ValueError:
            capacity = 1.0
        capacity = max(capacity, 1.0)
        event_times = sorted({row["_start"] for row in resource_rows} | {row["_finish"] for row in resource_rows})
        for time_value in event_times:
            active = [
                row
                for row in resource_rows
                if row["_start"] <= time_value < row["_finish"]
            ]
            if len(active) > capacity:
                conflicts.append(
                    {
                        "resource_id": resource_id,
                        "resource": active[0].get("資源名称", ""),
                        "time": time_value,
                        "load": float(len(active)),
                        "capacity": capacity,
                        "active_work": ", ".join(sorted({str(row.get("作業工程名称", "")) for row in active})),
                    }
                )
                break
    return sorted(conflicts, key=lambda item: (str(item["resource_id"]), str(item["time"])))


# What: Domain precedence violation detector.
# Purpose: Checks generated rows against PDF #2/#3 operation-order rules.
def _domain_precedence_violations(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    try:
        from marine_design_process_rules import documented_precedence_edges
        from sponsor_domain_rules import sponsor_precedence_edges
    except Exception:
        return []
    edges = documented_precedence_edges() | sponsor_precedence_edges()
    by_wbs_signature: dict[tuple[str, tuple[str, str, str, str]], dict[str, object]] = {}
    for row in _rows_with_dates(rows):
        by_wbs_signature[(str(row.get("WBS", "")), _operation_signature(row))] = row
    violations: list[dict[str, object]] = []
    wbs_values = sorted({str(row.get("WBS", "")) for row in rows})
    for wbs in wbs_values:
        for before, after in edges:
            before_row = by_wbs_signature.get((wbs, before))
            after_row = by_wbs_signature.get((wbs, after))
            if not before_row or not after_row:
                continue
            if before_row["_finish"] > after_row["_start"]:
                violations.append(
                    {
                        "wbs": wbs,
                        "before": f"{before_row.get('工程NO', '')} {before_row.get('作業工程名称', '')}".strip(),
                        "before_finish": before_row["_finish"],
                        "after": f"{after_row.get('工程NO', '')} {after_row.get('作業工程名称', '')}".strip(),
                        "after_start": after_row["_start"],
                        "violation_hours": (before_row["_finish"] - after_row["_start"]).total_seconds() / 3600,
                    }
                )
    return sorted(violations, key=lambda item: float(item["violation_hours"]), reverse=True)


# What: Same-phase overlap detector.
# Purpose: Flags potentially suspicious parallel work inside the same WBS and process phase for planner review.
def _same_phase_overlaps(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in _rows_with_dates(rows):
        grouped[(str(row.get("WBS", "")), str(row.get("基本工区名称", "")))].append(row)
    overlaps: list[dict[str, object]] = []
    for (wbs, phase), group_rows in grouped.items():
        sorted_rows = sorted(group_rows, key=lambda row: row["_start"])
        for index, left in enumerate(sorted_rows):
            for right in sorted_rows[index + 1 :]:
                overlap_seconds = (min(left["_finish"], right["_finish"]) - max(left["_start"], right["_start"])).total_seconds()
                if overlap_seconds > 0:
                    overlaps.append(
                        {
                            "wbs": wbs,
                            "phase": phase,
                            "activity_a": f"{left.get('工程NO', '')} {left.get('作業工程名称', '')}".strip(),
                            "activity_b": f"{right.get('工程NO', '')} {right.get('作業工程名称', '')}".strip(),
                            "overlap_hours": overlap_seconds / 3600,
                        }
                    )
    return sorted(overlaps, key=lambda item: float(item["overlap_hours"]), reverse=True)


# What: Operation signature helper.
# Purpose: Maps generated rows onto documented PDF #2/#3 process-rule signatures.
def _operation_signature(row: dict[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row.get("工程NO", "")),
        str(row.get("作業工程ID", "")),
        str(row.get("作業工程名称", "")),
        str(row.get("基本工区名称", "")),
    )


# What: Capacity-conflict HTML section.
# Purpose: Presents resource overload conflicts in a compact sponsor-readable table.
def _capacity_conflicts_section(conflicts: list[dict[str, object]]) -> str:
    if conflicts:
        rows = "\n".join(
            f"""<tr>
          <td>{escape(item['resource_id'])}</td>
          <td>{escape(item['resource'])}</td>
          <td>{escape(item['time'].strftime('%Y-%m-%d %H:%M'))}</td>
          <td>{float(item['load']):.2f}</td>
          <td>{float(item['capacity']):.2f}</td>
          <td>{escape(item['active_work'])}</td>
        </tr>"""
            for item in conflicts[:20]
        )
    else:
        rows = '<tr><td colspan="6">No capacity conflicts detected under the current resource-capacity check.</td></tr>'
    return f"""<section class="subsection">
      <h3>Capacity Conflicts</h3>
      <div class="panel compare-table">
        <table>
          <thead><tr><th>Resource ID</th><th>Resource</th><th>Time</th><th>Load</th><th>Capacity</th><th>Active Work</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>"""


# What: Precedence-violation HTML section.
# Purpose: Shows where generated timing violates encoded sponsor/domain process order.
def _precedence_violations_section(violations: list[dict[str, object]]) -> str:
    if not violations:
        return ""
    rows = "\n".join(
        f"""<tr>
          <td>{escape(item['wbs'])}</td>
          <td>{escape(item['before'])}</td>
          <td>{escape(item['before_finish'].strftime('%Y-%m-%d %H:%M'))}</td>
          <td>{escape(item['after'])}</td>
          <td>{escape(item['after_start'].strftime('%Y-%m-%d %H:%M'))}</td>
          <td>{float(item['violation_hours']):.1f}</td>
        </tr>"""
        for item in violations[:20]
    )
    return f"""<section class="subsection">
      <h3>Domain Precedence Violations</h3>
      <div class="panel compare-table">
        <table>
          <thead><tr><th>WBS</th><th>Required Before</th><th>Before Finish</th><th>Required After</th><th>After Start</th><th>Violation (h)</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>"""


# What: Overload-row HTML section.
# Purpose: Lists generated rows marked overloaded by the current resource-load field logic.
def _overload_rows_section(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    body = "\n".join(
        f"""<tr>
          <td>{escape(row.get('WBS', ''))}</td>
          <td>{escape(row.get('工程NO', ''))}</td>
          <td>{escape(row.get('作業工程名称', ''))}</td>
          <td>{escape(row.get('資源ID', ''))}</td>
          <td>{escape(row.get('資源名称', ''))}</td>
          <td>{escape(row.get('スケジュール結果開始日時', ''))}</td>
          <td>{escape(row.get('スケジュール結果終了日時', ''))}</td>
        </tr>"""
        for row in rows[:20]
    )
    return f"""<section class="subsection">
      <h3>Overload Rows</h3>
      <div class="panel compare-table">
        <table>
          <thead><tr><th>WBS</th><th>Operation</th><th>Activity</th><th>Resource ID</th><th>Resource</th><th>Start</th><th>Finish</th></tr></thead>
          <tbody>{body}</tbody>
        </table>
      </div>
    </section>"""


# What: Same-phase overlap HTML section.
# Purpose: Gives planners review candidates where same-phase operations run in parallel.
def _same_phase_overlaps_section(overlaps: list[dict[str, object]]) -> str:
    if not overlaps:
        return ""
    rows = "\n".join(
        f"""<tr>
          <td>{escape(item['wbs'])}</td>
          <td>{escape(item['phase'])}</td>
          <td>{escape(item['activity_a'])}</td>
          <td>{escape(item['activity_b'])}</td>
          <td>{float(item['overlap_hours']):.1f}</td>
        </tr>"""
        for item in overlaps[:20]
    )
    return f"""<section class="subsection">
      <h3>Same-Phase Overlap Reviews</h3>
      <p class="statline">These overlaps are not automatically wrong, but they are useful indicators of missing or intentionally parallel process logic.</p>
      <div class="panel compare-table">
        <table>
          <thead><tr><th>WBS</th><th>Phase</th><th>Activity A</th><th>Activity B</th><th>Overlap (h)</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
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
    :root { color-scheme: light; --ink: #0f172a; --muted: #64748b; --line: #e2e8f0; --bg: #f8fafc; --panel: #ffffff; --win-bg: #dcfce7; --win-fg: #166534; --lose-bg: #f5e6d3; --lose-fg: #7c2d12; --tie-bg: #f1f5f9; --tie-fg: #475569; }
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
    .button-link { display: inline-flex; align-items: center; min-height: 36px; margin-top: 14px; padding: 7px 12px; border-radius: 8px; background: #1d4ed8; color: #fff; font-size: 13px; font-weight: 800; text-decoration: none; }
    .button-link:hover { background: #1e40af; }
    .dashboard-block { margin-top: 16px; }
    .dashboard-block:first-of-type { margin-top: 0; }
    .dashboard-block.primary { padding: 16px; border: 1px solid #bbf7d0; border-radius: 8px; background: #f0fdf4; }
    .dashboard-block.secondary { padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
    .comparison-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }
    .report-group { margin: 24px 40px; padding: 22px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
    .report-group > h2 { margin-bottom: 18px; font-size: 22px; }
    .subsection { padding: 0; margin-top: 18px; }
    .subsection:first-of-type { margin-top: 0; }
    .rule-grid + .subsection { margin-top: 28px; }
    .rule-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
    .rule-card { padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: #f8fafc; }
    .rule-card h4 { margin: 0 0 10px; font-size: 13px; color: #0f172a; overflow-wrap: anywhere; }
    .rule-metrics { display: grid; gap: 6px; color: var(--muted); font-size: 12px; }
    .rule-metrics strong { color: var(--ink); font-size: 15px; }
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
    .status-pill { display: inline-flex; align-items: center; min-height: 22px; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 800; white-space: nowrap; }
    .status-passed { color: var(--win-fg); background: var(--win-bg); }
    .status-warning { color: #854d0e; background: #fef3c7; }
    .status-violated { color: var(--lose-fg); background: var(--lose-bg); }
    code { padding: 1px 5px; border-radius: 4px; background: #f1f5f9; color: #0f172a; }
    svg { display: block; max-width: none; }
    .axis-label { font-size: 11px; fill: #334155; }
    .value-label { font-size: 11px; fill: #475569; }
    .bar-label { font-size: 10px; fill: #fff; font-weight: 700; pointer-events: none; }
    .flow-label { font-size: 12px; fill: #fff; font-weight: 700; }
    .flow-sub { font-size: 11px; fill: #e2e8f0; }
    @media (max-width: 900px) { header { display: block; padding: 24px; } section { padding: 20px 24px; } .report-group { margin: 20px 24px; padding: 18px; } .subsection { padding: 0; } .meta { margin-top: 16px; } .split { grid-template-columns: 1fr; } }
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
