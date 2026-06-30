from __future__ import annotations

import csv
import html
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from execution_management import load_progress_updates


# What: Work-order generation agent.
# Purpose: Turns generated schedule rows and optional progress updates into dispatch-ready work instructions.

WORK_ORDER_COLUMNS = [
    "work_order_id",
    "wbs",
    "part_no",
    "operation_no",
    "activity_id",
    "activity_name",
    "workgroup",
    "resource_id",
    "resource_name",
    "planned_start",
    "planned_finish",
    "execution_status",
    "progress_rate",
    "priority",
    "risk_level",
    "instruction",
    "delay_reason",
]


# What: Dispatch-ready operation instruction.
# Purpose: Carries one workgroup-facing instruction to CSV, HTML, and process reports.
@dataclass(frozen=True)
class WorkOrder:
    work_order_id: str
    wbs: str
    part_no: str
    operation_no: str
    activity_id: str
    activity_name: str
    workgroup: str
    resource_id: str
    resource_name: str
    planned_start: str
    planned_finish: str
    execution_status: str
    progress_rate: str
    priority: str
    risk_level: str
    instruction: str
    delay_reason: str


# What: Work-order generator.
# Purpose: Builds workgroup-facing instructions from schedule/progress data.
def generate_work_orders(
    schedule_rows: list[dict[str, str]],
    progress_rows: list[dict[str, str]] | None = None,
) -> list[WorkOrder]:
    progress_by_key = {_progress_key(row): row for row in progress_rows or []}
    work_orders: list[WorkOrder] = []
    for row in schedule_rows:
        progress = progress_by_key.get(_schedule_key(row), {})
        status = _execution_status(progress)
        priority, risk_level = _priority_and_risk(row, progress, status)
        work_orders.append(
            WorkOrder(
                work_order_id=_work_order_id(row),
                wbs=row.get("WBS", ""),
                part_no=row.get("部品NO", ""),
                operation_no=row.get("工程NO", ""),
                activity_id=row.get("作業工程ID", ""),
                activity_name=row.get("作業工程名称", ""),
                workgroup=row.get("基本工区名称", ""),
                resource_id=row.get("資源ID", ""),
                resource_name=row.get("資源名称", ""),
                planned_start=row.get("スケジュール結果開始日時", ""),
                planned_finish=row.get("スケジュール結果終了日時", ""),
                execution_status=status,
                progress_rate=progress.get("進捗率", row.get("進捗率", "")),
                priority=priority,
                risk_level=risk_level,
                instruction=_instruction(row, progress, status, priority),
                delay_reason=progress.get("遅延理由", ""),
            )
        )
    return _sort_work_orders(work_orders)


# What: Data-folder work-order generator.
# Purpose: Lets scripts create work orders from a schedule plus optional actual_progress.csv.
def generate_work_orders_from_data_dir(
    schedule_rows: list[dict[str, str]],
    data_dir: str | Path = "data",
) -> list[WorkOrder]:
    return generate_work_orders(schedule_rows, load_progress_updates(data_dir))


# What: Work-order CSV exporter.
# Purpose: Exports generated work orders for spreadsheet review or downstream dispatch.
def write_work_orders_csv(work_orders: Iterable[WorkOrder], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=WORK_ORDER_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for order in work_orders:
            writer.writerow(asdict(order))


# What: Work-order HTML exporter.
# Purpose: Creates a standalone visual work-order page for sponsor demos.
def write_work_orders_html(work_orders: list[WorkOrder], path: str | Path, limit: int = 30) -> None:
    Path(path).write_text(render_work_orders_html(work_orders, limit=limit), encoding="utf-8")


# What: Work-order HTML renderer.
# Purpose: Presents the highest-priority work-order examples as cards.
def render_work_orders_html(work_orders: list[WorkOrder], limit: int = 30) -> str:
    cards = "\n".join(render_work_order_card(order) for order in demo_work_orders(work_orders, limit))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIPM Work Orders</title>
  <style>{work_order_css()}</style>
</head>
<body>
  <main>
    <p class="eyebrow">AIPM Process Management</p>
    <h1>Generated Work Orders</h1>
    <p class="subtle">Dispatch-ready examples generated from the current schedule and progress updates.</p>
    <section class="cards">{cards or '<p>No work orders were generated.</p>'}</section>
  </main>
</body>
</html>"""


# What: Single work-order card renderer.
# Purpose: Makes one operation instruction readable for workgroups and managers.
def render_work_order_card(order: WorkOrder) -> str:
    risk_class = html.escape(order.risk_level.lower())
    return f"""<article class="card {risk_class}">
      <div class="card-head">
        <strong>{html.escape(order.work_order_id)}</strong>
        <span>{html.escape(order.priority)} / {html.escape(order.risk_level)}</span>
      </div>
      <h2>{html.escape(order.activity_name)}</h2>
      <dl>
        <div><dt>WBS</dt><dd>{html.escape(order.wbs)}</dd></div>
        <div><dt>Workgroup</dt><dd>{html.escape(order.workgroup)}</dd></div>
        <div><dt>Resource</dt><dd>{html.escape(order.resource_id)} {html.escape(order.resource_name)}</dd></div>
        <div><dt>Planned Window</dt><dd>{html.escape(order.planned_start)} - {html.escape(order.planned_finish)}</dd></div>
        <div><dt>Status</dt><dd>{html.escape(order.execution_status)} ({html.escape(order.progress_rate)})</dd></div>
      </dl>
      <p>{html.escape(order.instruction)}</p>
      {f'<p class="reason">Delay reason: {html.escape(order.delay_reason)}</p>' if order.delay_reason else ''}
    </article>"""


# What: Demo-order selector.
# Purpose: Places critical/watch items first, then fills with earliest normal work orders.
def demo_work_orders(work_orders: list[WorkOrder], limit: int = 8) -> list[WorkOrder]:
    return _sort_work_orders(work_orders)[:limit]


# What: Work-order CSS.
# Purpose: Keeps standalone work-order HTML readable without external assets.
def work_order_css() -> str:
    return """
body{margin:0;background:#f8fafc;color:#0f172a;font-family:Inter,Arial,sans-serif}
main{max-width:1120px;margin:0 auto;padding:40px 24px}
.eyebrow{margin:0;color:#2563eb;font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:12px}
h1{margin:6px 0 8px;font-size:34px}
.subtle{color:#64748b}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:24px}
.card{background:white;border:1px solid #dbe3ef;border-radius:8px;padding:18px;box-shadow:0 8px 24px rgba(15,23,42,.06)}
.card.high{border-color:#b45309}.card.critical{border-color:#dc2626}
.card-head{display:flex;justify-content:space-between;gap:12px;color:#475569}
h2{font-size:18px;margin:12px 0}
dl{display:grid;gap:8px;margin:0}
dt{font-size:12px;color:#64748b}dd{margin:0;font-weight:650}
.reason{color:#991b1b;font-weight:650}
"""


def _work_order_id(row: dict[str, str]) -> str:
    return "-".join(
        part for part in [row.get("WBS", ""), row.get("部品NO", ""), row.get("工程NO", ""), row.get("作業工程ID", "")] if part
    )


def _schedule_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (row.get("WBS", ""), row.get("部品NO", ""), row.get("工程NO", ""), row.get("作業工程ID", ""))


def _progress_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (row.get("WBS", ""), row.get("部品NO", ""), row.get("工程NO", ""), row.get("作業工程ID", ""))


def _execution_status(progress: dict[str, str]) -> str:
    return (progress.get("状態", "") or "not_reported").strip()


def _priority_and_risk(row: dict[str, str], progress: dict[str, str], status: str) -> tuple[str, str]:
    normalized = status.casefold()
    if normalized in {"blocked", "delayed", "遅延", "停止", "保留"}:
        return "urgent", "critical"
    if row.get("負荷状態") == "1:OV":
        return "high", "high"
    if normalized in {"in_progress", "in progress", "作業中"}:
        return "normal", "watch"
    return "normal", "normal"


def _instruction(row: dict[str, str], progress: dict[str, str], status: str, priority: str) -> str:
    if priority == "urgent":
        reason = progress.get("遅延理由", "")
        return "Manager review required before dispatch." + (f" Reason: {reason}" if reason else "")
    if status.casefold() in {"in_progress", "in progress", "作業中"}:
        return "Continue work and update progress before shift end."
    return "Prepare resource and execute within the planned window."


def _sort_work_orders(work_orders: list[WorkOrder]) -> list[WorkOrder]:
    priority_rank = {"urgent": 0, "high": 1, "normal": 2}
    risk_rank = {"critical": 0, "high": 1, "watch": 2, "normal": 3}
    return sorted(
        work_orders,
        key=lambda order: (
            priority_rank.get(order.priority, 9),
            risk_rank.get(order.risk_level, 9),
            order.planned_start,
            order.work_order_id,
        ),
    )

