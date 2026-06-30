# AIPM Actual Progress File Format

**File name:** `actual_progress.csv`

## Purpose

This optional file lets AIPM2 monitor execution status after a plan/schedule has
been released.

## Required Columns

| Column | Meaning |
|---|---|
| `WBS` | Order/WBS identifier. |
| `部品NO` | Part number from the generated schedule. |
| `工程NO` | Operation number. |
| `作業工程ID` | Activity/operation ID. |
| `状態` | Execution status such as `not_started`, `in_progress`, `completed`, `blocked`, `delayed`, `作業中`, `完了`, or `遅延`. |
| `実績開始日時` | Actual start datetime. |
| `実績終了日時` | Actual finish datetime. |
| `進捗率` | Progress percentage. |
| `遅延理由` | Optional delay/blockage reason. |
| `更新日時` | Timestamp when the progress update was recorded. |

## Behavior

- If no progress file is provided, AIPM2 still generates the schedule.
- Completed rows preserve actual start/finish times in `execution_reschedule`.
- In-progress rows preserve actual start times and progress percentages.
- Blocked or delayed rows are flagged in the process-management report.

