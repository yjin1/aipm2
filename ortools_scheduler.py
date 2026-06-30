from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from aipm_data import format_schedule_datetime, parse_datetime


# What: OR-Tools CP-SAT scheduling backend.
# Purpose: Adds a real constraint solver beneath the AIPM planning/scheduling agent.


# What: Constraint-programming schedule optimizer.
# Purpose: Keeps activities near target timestamps while enforcing resource no-overlap constraints.
def solve_with_ortools(
    target_rows: list[dict[str, str]],
    resource_capacities: dict[str, float] | None = None,
    activity_demands: dict[tuple[str, str, str, str], float] | None = None,
    precedence_edges: set[tuple[tuple[str, str, str, str], tuple[str, str, str, str]]] | None = None,
    max_time_seconds: float = 5.0,
) -> list[dict[str, str]]:
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise RuntimeError(
            "OR-Tools is not installed. Install it with: python -m pip install ortools"
        ) from exc

    dated_rows = _dated_rows(target_rows)
    if not dated_rows:
        return [dict(row) for row in target_rows]

    origin = min(row["_start"] for row in dated_rows)
    horizon = _horizon_minutes(dated_rows, origin)
    model = cp_model.CpModel()

    starts = {}
    ends = {}
    intervals_by_resource = defaultdict(list)
    abs_deviations = []

    for index, row in enumerate(dated_rows):
        target_start = _minutes_from_origin(row["_start"], origin)
        target_finish = _minutes_from_origin(row["_finish"], origin)
        duration = max(1, target_finish - target_start)

        start = model.NewIntVar(0, horizon, f"start_{index}")
        end = model.NewIntVar(0, horizon, f"end_{index}")
        interval = model.NewIntervalVar(start, duration, end, f"interval_{index}")
        starts[index] = start
        ends[index] = end

        resource_id = row.get("資源ID", "")
        if resource_id:
            demand = _scaled_quantity((activity_demands or {}).get(_activity_key(row), 1.0))
            intervals_by_resource[resource_id].append((interval, demand))

        start_deviation = model.NewIntVar(0, horizon, f"start_dev_{index}")
        finish_deviation = model.NewIntVar(0, horizon, f"finish_dev_{index}")
        model.AddAbsEquality(start_deviation, start - target_start)
        model.AddAbsEquality(finish_deviation, end - target_finish)
        abs_deviations.extend([start_deviation, finish_deviation])

    for resource_id, interval_demands in intervals_by_resource.items():
        if len(interval_demands) <= 1:
            continue
        intervals = [item[0] for item in interval_demands]
        demands = [item[1] for item in interval_demands]
        capacity = _scaled_quantity((resource_capacities or {}).get(resource_id, 1.0))
        capacity = max(capacity, max(demands))
        model.AddCumulative(intervals, demands, capacity)

    _add_signature_precedence_constraints(model, dated_rows, starts, ends, precedence_edges or set())
    _add_soft_order_constraints(model, dated_rows, starts, ends)
    model.Minimize(sum(abs_deviations))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"OR-Tools could not find a feasible schedule; status={status}")

    solved_rows = [dict(row) for row in target_rows]
    for dated_index, original_index in enumerate(row["_index"] for row in dated_rows):
        solved_start = origin + timedelta(minutes=solver.Value(starts[dated_index]))
        solved_finish = origin + timedelta(minutes=solver.Value(ends[dated_index]))
        solved_rows[original_index]["スケジュール結果開始日時"] = format_schedule_datetime(solved_start)
        solved_rows[original_index]["スケジュール結果終了日時"] = format_schedule_datetime(solved_finish)
    return solved_rows


# What: Date parser for schedule rows.
# Purpose: Keeps only rows with valid generated start and finish times for solver variables.
def _dated_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    dated_rows = []
    for index, row in enumerate(rows):
        start = parse_datetime(row.get("スケジュール結果開始日時", ""))
        finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
        if start and finish:
            copy = dict(row)
            copy["_index"] = index
            copy["_start"] = start
            copy["_finish"] = finish
            dated_rows.append(copy)
    return dated_rows


# What: Solver horizon calculator.
# Purpose: Gives CP-SAT enough room to move activities around target timestamps.
def _horizon_minutes(rows: list[dict[str, object]], origin) -> int:
    latest = max(row["_finish"] for row in rows)
    span = max(1, int((latest - origin).total_seconds() // 60))
    return span + 90 * 24 * 60


# What: Timestamp-to-minute conversion helper.
# Purpose: Converts datetimes into integer CP-SAT coordinates.
def _minutes_from_origin(value, origin) -> int:
    return int((value - origin).total_seconds() // 60)


# What: Activity identity helper.
# Purpose: Matches target schedule rows to original activity demand data.
def _activity_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("WBS", ""),
        row.get("部品NO", ""),
        row.get("工程NO", ""),
        row.get("作業工程ID", ""),
    )


# What: Quantity scaling helper.
# Purpose: Converts fractional resource quantities into CP-SAT integer capacities/demands.
def _scaled_quantity(value: float) -> int:
    return max(1, int(round(float(value) * 1000)))


# What: Signature-level precedence constraint builder.
# Purpose: Applies learned process edges within each WBS order when both activities are present.
def _add_signature_precedence_constraints(model, rows, starts, ends, precedence_edges) -> None:
    if not precedence_edges:
        return
    by_wbs_signature = {}
    for index, row in enumerate(rows):
        by_wbs_signature[(row.get("WBS", ""), _operation_signature(row))] = index

    wbs_values = {row.get("WBS", "") for row in rows}
    for wbs in wbs_values:
        for before_signature, after_signature in precedence_edges:
            before_index = by_wbs_signature.get((wbs, before_signature))
            after_index = by_wbs_signature.get((wbs, after_signature))
            if before_index is not None and after_index is not None and before_index != after_index:
                model.Add(ends[before_index] <= starts[after_index])


# What: Operation signature helper.
# Purpose: Matches learned precedence rules to scheduled rows.
def _operation_signature(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("工程NO", ""),
        row.get("作業工程ID", ""),
        row.get("作業工程名称", ""),
        row.get("基本工区名称", ""),
    )


# What: Soft operation-order constraints.
# Purpose: Preserves target order only when target rows do not overlap within the same WBS.
def _add_soft_order_constraints(model, rows, starts, ends) -> None:
    rows_by_wbs = defaultdict(list)
    for index, row in enumerate(rows):
        rows_by_wbs[row.get("WBS", "")].append((index, row))

    for wbs_rows in rows_by_wbs.values():
        ordered = sorted(wbs_rows, key=lambda item: item[1]["_start"])
        for (left_index, left), (right_index, right) in zip(ordered, ordered[1:]):
            if left["_finish"] <= right["_start"]:
                model.Add(ends[left_index] <= starts[right_index])
