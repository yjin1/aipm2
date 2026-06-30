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
    return f"""<article class="work-order-card {risk_class}">
      <div class="work-order-head">
        <div>
          <span class="ticket-label">Work Order</span>
          <strong>{html.escape(_compact_work_order_id(order))}</strong>
        </div>
        <div class="badge-stack">
          <span class="status-pill priority-{html.escape(order.priority.lower())}">{html.escape(order.priority)}</span>
          <span class="status-pill risk-{risk_class}">{html.escape(order.risk_level)}</span>
        </div>
      </div>
      <h3>{html.escape(order.activity_name)}</h3>
      <p class="ticket-subtitle">{html.escape(order.wbs)}</p>
      <dl class="ticket-grid">
        <div><dt>Group</dt><dd>{html.escape(order.workgroup)}</dd></div>
        <div><dt>Operation</dt><dd>{html.escape(order.operation_no)} / {html.escape(order.activity_id)}</dd></div>
        <div><dt>Resource</dt><dd>{html.escape(order.resource_id)} {html.escape(order.resource_name)}</dd></div>
        <div><dt>Status</dt><dd>{html.escape(order.execution_status)} ({html.escape(order.progress_rate)})</dd></div>
      </dl>
      <div class="ticket-window">
        <span>{html.escape(order.planned_start)}</span>
        <strong>to</strong>
        <span>{html.escape(order.planned_finish)}</span>
      </div>
      <p class="instruction">{html.escape(order.instruction)}</p>
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
main{max-width:1180px;margin:0 auto;padding:40px 24px}
.eyebrow{margin:0;color:#2563eb;font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:12px}
h1{margin:6px 0 8px;font-size:34px;letter-spacing:0}
.subtle{color:#64748b}
.cards,.work-order-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-top:24px;align-items:start}
.work-order-card{background:#fff;border:1px solid #dbe3ef;border-left:4px solid #94a3b8;border-radius:8px;padding:16px;box-shadow:0 8px 22px rgba(15,23,42,.05)}
.work-order-card.high{border-left-color:#d97706}.work-order-card.critical{border-left-color:#dc2626}.work-order-card.watch{border-left-color:#2563eb}
.work-order-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.ticket-label{display:block;color:#64748b;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.06em}
.work-order-head strong{display:block;margin-top:3px;color:#334155;font-size:13px;line-height:1.25;overflow-wrap:anywhere}
.badge-stack{display:flex;flex-direction:column;gap:5px;align-items:flex-end;flex:0 0 auto}
.status-pill{display:inline-flex;align-items:center;justify-content:center;min-height:22px;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:800;text-transform:capitalize;white-space:nowrap}
.priority-urgent,.risk-critical{color:#991b1b;background:#fee2e2}.priority-high,.risk-high{color:#92400e;background:#fef3c7}.priority-normal,.risk-normal{color:#475569;background:#f1f5f9}.risk-watch{color:#1d4ed8;background:#dbeafe}
h3{font-size:18px;line-height:1.25;margin:14px 0 4px;color:#0f172a;letter-spacing:0}
.ticket-subtitle{margin:0 0 14px;color:#64748b;font-size:12px;font-weight:700;overflow-wrap:anywhere}
.ticket-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px;margin:0}
.ticket-grid div{min-width:0}
dt{font-size:10px;color:#64748b;text-transform:uppercase;font-weight:800;letter-spacing:.04em}
dd{margin:2px 0 0;font-size:13px;line-height:1.3;font-weight:700;overflow-wrap:anywhere}
.ticket-window{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;margin-top:14px;padding:10px;border-radius:8px;background:#f8fafc;color:#334155;font-size:12px;font-weight:700}
.ticket-window strong{color:#64748b;font-size:10px;text-transform:uppercase}
.instruction{margin:12px 0 0;padding-top:10px;border-top:1px solid #e2e8f0;color:#475569;font-size:13px;line-height:1.45}
.reason{margin:10px 0 0;color:#991b1b;font-weight:700;font-size:13px}
@media(max-width:720px){.ticket-grid{grid-template-columns:1fr}.ticket-window{grid-template-columns:1fr}.ticket-window strong{display:none}}
"""


# What: Compact work-order identifier formatter.
# Purpose: Prevents long WBS-based IDs from dominating the work-order card layout.
def _compact_work_order_id(order: WorkOrder) -> str:
    parts = [order.part_no, order.operation_no, order.activity_id]
    suffix = "-".join(part for part in parts if part)
    return suffix or order.work_order_id


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
