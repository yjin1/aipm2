from __future__ import annotations

from dataclasses import dataclass

from aipm_data import parse_datetime


# What: Marine/process rule diagnostic utilities.
# Purpose: Checks whether generated schedules respect mapped PDF #2/#3 operation-order rules.

OperationSignature = tuple[str, str, str, str]


# What: One process-rule diagnostic finding.
# Purpose: Carries a human-readable violation for reports and debugging.
@dataclass(frozen=True)
class RuleViolation:
    wbs: str
    before: OperationSignature
    after: OperationSignature
    before_finish: str
    after_start: str
    message: str


# What: Domain precedence validator.
# Purpose: Reports cases where a mapped predecessor finishes after the successor starts.
def validate_precedence_rules(
    schedule_rows: list[dict[str, str]],
    edges: set[tuple[OperationSignature, OperationSignature]],
) -> list[RuleViolation]:
    rows_by_wbs_signature: dict[tuple[str, OperationSignature], dict[str, str]] = {}
    for row in schedule_rows:
        rows_by_wbs_signature[(row.get("WBS", ""), _operation_signature(row))] = row

    violations: list[RuleViolation] = []
    wbs_values = {row.get("WBS", "") for row in schedule_rows}
    for wbs in wbs_values:
        for before_sig, after_sig in edges:
            before = rows_by_wbs_signature.get((wbs, before_sig))
            after = rows_by_wbs_signature.get((wbs, after_sig))
            if not before or not after:
                continue
            before_finish = parse_datetime(before.get("スケジュール結果終了日時", ""))
            after_start = parse_datetime(after.get("スケジュール結果開始日時", ""))
            if before_finish and after_start and before_finish > after_start:
                violations.append(
                    RuleViolation(
                        wbs=wbs,
                        before=before_sig,
                        after=after_sig,
                        before_finish=before.get("スケジュール結果終了日時", ""),
                        after_start=after.get("スケジュール結果開始日時", ""),
                        message=(
                            f"{before_sig[2]} finishes after {after_sig[2]} starts "
                            f"for WBS {wbs}."
                        ),
                    )
                )
    return violations


# What: Operation signature helper.
# Purpose: Matches rule signatures to generated schedule rows.
def _operation_signature(row: dict[str, str]) -> OperationSignature:
    return (
        row.get("工程NO", ""),
        row.get("作業工程ID", ""),
        row.get("作業工程名称", ""),
        row.get("基本工区名称", ""),
    )

