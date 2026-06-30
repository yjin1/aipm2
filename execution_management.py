from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from aipm_data import MIDDLE_SCHEDULE_COLUMNS, format_schedule_datetime, parse_datetime


# What: Execution-progress monitoring and schedule repair utilities.
# Purpose: Starts the AIPM closed loop from planned schedule to work execution and progress monitoring.

# What: Actual progress CSV schema.
# Purpose: Defines the workgroup-facing status update format.
PROGRESS_COLUMNS = [
    "WBS",
    "部品NO",
    "工程NO",
    "作業工程ID",
    "状態",
    "実績開始日時",
    "実績終了日時",
    "進捗率",
    "遅延理由",
    "更新日時",
]

COMPLETED_STATUSES = {"completed", "complete", "done", "完了", "終了"}
IN_PROGRESS_STATUSES = {"in_progress", "in progress", "started", "作業中", "着手", "開始"}
BLOCKED_STATUSES = {"blocked", "delayed", "遅延", "停止", "保留"}


# What: Execution-monitor summary.
# Purpose: Provides dashboard counts for the process-management report.
@dataclass(frozen=True)
class ExecutionSummary:
    progress_rows: int
    completed: int
    in_progress: int
    blocked_or_delayed: int
    late_unfinished: int


# What: One execution-monitor finding.
# Purpose: Turns progress/schedule comparisons into manager-readable exceptions.
@dataclass(frozen=True)
class ExecutionFinding:
    severity: str
    wbs: str
    operation_no: str
    activity_id: str
    activity_name: str
    planned_finish: str
    actual_start: str
    actual_finish: str
    status: str
    message: str


# What: Execution-monitor result.
# Purpose: Keeps the status summary and detailed exceptions together.
@dataclass(frozen=True)
class ExecutionMonitorResult:
    summary: ExecutionSummary
    findings: list[ExecutionFinding]
    has_progress: bool


# What: Optional progress loader.
# Purpose: Reads actual_progress.csv when present without making it required for scheduling.
def load_progress_updates(data_dir: str | Path = "data") -> list[dict[str, str]]:
    progress_path = find_progress_file(data_dir)
    if not progress_path:
        return []
    with progress_path.open("r", encoding="utf-8-sig", newline="") as stream:
        return [{key: value for key, value in row.items()} for row in csv.DictReader(stream)]


# What: Progress file finder.
# Purpose: Finds progress by schema first, then by conventional filename.
def find_progress_file(data_dir: str | Path = "data") -> Path | None:
    data_path = Path(data_dir)
    conventional = data_path / "actual_progress.csv"
    if conventional.exists():
        return conventional
    for path in data_path.glob("*.csv"):
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
        if all(column in header for column in PROGRESS_COLUMNS[:5]):
            return path
    return None


# What: Execution monitor.
# Purpose: Compares planned rows with actual progress and identifies delays/risks.
def monitor_execution(
    schedule_rows: list[dict[str, str]],
    progress_rows: list[dict[str, str]] | None = None,
) -> ExecutionMonitorResult:
    progress_rows = progress_rows or []
    if not progress_rows:
        return ExecutionMonitorResult(
            summary=ExecutionSummary(0, 0, 0, 0, 0),
            findings=[],
            has_progress=False,
        )

    progress_by_key = {_progress_key(row): row for row in progress_rows}
    completed = 0
    in_progress = 0
    blocked = 0
    late_unfinished = 0
    findings: list[ExecutionFinding] = []

    for row in schedule_rows:
        progress = progress_by_key.get(_schedule_key(row), {})
        if not progress:
            continue
        status = _normalized_status(progress.get("状態", ""))
        planned_finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
        actual_start = parse_datetime(progress.get("実績開始日時", ""))
        actual_finish = parse_datetime(progress.get("実績終了日時", ""))

        if status in COMPLETED_STATUSES:
            completed += 1
            if planned_finish and actual_finish and actual_finish > planned_finish:
                findings.append(_finding("warning", row, progress, "Completed later than planned finish."))
        elif status in IN_PROGRESS_STATUSES:
            in_progress += 1
        elif status in BLOCKED_STATUSES:
            blocked += 1
            findings.append(_finding("critical", row, progress, "Operation is blocked or delayed."))

        if status not in COMPLETED_STATUSES and planned_finish and actual_finish is None:
            # The demo data has no wall-clock 'today'; this flags only rows explicitly marked delayed/blocked.
            if status in BLOCKED_STATUSES:
                late_unfinished += 1

        if actual_start and planned_finish and status not in COMPLETED_STATUSES and actual_start > planned_finish:
            findings.append(_finding("critical", row, progress, "Operation started after planned finish."))

    return ExecutionMonitorResult(
        summary=ExecutionSummary(
            progress_rows=len(progress_rows),
            completed=completed,
            in_progress=in_progress,
            blocked_or_delayed=blocked,
            late_unfinished=late_unfinished,
        ),
        findings=findings,
        has_progress=True,
    )


# What: Progress-aware schedule repair.
# Purpose: Freezes completed/in-progress work and copies progress fields into the schedule.
def repair_schedule_with_progress(
    schedule_rows: list[dict[str, str]],
    progress_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    progress_rows = progress_rows or []
    if not progress_rows:
        return [dict(row) for row in schedule_rows]

    progress_by_key = {_progress_key(row): row for row in progress_rows}
    repaired: list[dict[str, str]] = []
    for row in schedule_rows:
        copy = dict(row)
        progress = progress_by_key.get(_schedule_key(row), {})
        if not progress:
            repaired.append(copy)
            continue

        status = _normalized_status(progress.get("状態", ""))
        actual_start = parse_datetime(progress.get("実績開始日時", ""))
        actual_finish = parse_datetime(progress.get("実績終了日時", ""))
        if progress.get("進捗率", ""):
            copy["進捗率"] = progress["進捗率"]
        if status in COMPLETED_STATUSES and actual_start and actual_finish:
            copy["スケジュール結果開始日時"] = format_schedule_datetime(actual_start)
            copy["スケジュール結果終了日時"] = format_schedule_datetime(actual_finish)
            copy["スケジュール状態"] = "2:実績完了"
        elif status in IN_PROGRESS_STATUSES and actual_start:
            copy["スケジュール結果開始日時"] = format_schedule_datetime(actual_start)
            copy["スケジュール状態"] = "1:作業中"
        elif status in BLOCKED_STATUSES:
            copy["スケジュール状態"] = "9:要注意"
        repaired.append(copy)
    return repaired


# What: Progress template writer.
# Purpose: Gives sponsors the actual_progress.csv column format for a completed schedule.
def write_progress_template(path: str | Path, schedule_rows: list[dict[str, str]]) -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=PROGRESS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in schedule_rows:
            writer.writerow(
                {
                    "WBS": row.get("WBS", ""),
                    "部品NO": row.get("部品NO", ""),
                    "工程NO": row.get("工程NO", ""),
                    "作業工程ID": row.get("作業工程ID", ""),
                    "状態": "not_started",
                    "実績開始日時": "",
                    "実績終了日時": "",
                    "進捗率": row.get("進捗率", "0.00 ％"),
                    "遅延理由": "",
                    "更新日時": "",
                }
            )


# What: Progress validator.
# Purpose: Rejects uploaded progress files that cannot be matched to schedule rows.
def validate_progress_rows(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["actual_progress.csv has no data rows"]
    return [column for column in PROGRESS_COLUMNS if column not in rows[0]]


def _schedule_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (row.get("WBS", ""), row.get("部品NO", ""), row.get("工程NO", ""), row.get("作業工程ID", ""))


def _progress_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (row.get("WBS", ""), row.get("部品NO", ""), row.get("工程NO", ""), row.get("作業工程ID", ""))


def _normalized_status(value: str) -> str:
    return (value or "").strip().casefold()


def _finding(severity: str, schedule_row: dict[str, str], progress_row: dict[str, str], message: str) -> ExecutionFinding:
    return ExecutionFinding(
        severity=severity,
        wbs=schedule_row.get("WBS", ""),
        operation_no=schedule_row.get("工程NO", ""),
        activity_id=schedule_row.get("作業工程ID", ""),
        activity_name=schedule_row.get("作業工程名称", ""),
        planned_finish=schedule_row.get("スケジュール結果終了日時", ""),
        actual_start=progress_row.get("実績開始日時", ""),
        actual_finish=progress_row.get("実績終了日時", ""),
        status=progress_row.get("状態", "") or "not_started",
        message=message,
    )

