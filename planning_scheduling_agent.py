from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from aipm_data import (
    AIPMDataset,
    MIDDLE_SCHEDULE_COLUMNS,
    ValidationIssue,
    build_middle_schedule,
    format_schedule_datetime,
    parse_datetime,
    write_middle_schedule,
)
from aipm_visualize import build_report_html, column_difference_counts, compare_with_reference


# What: Agent module for planning and scheduling.
# Purpose: Turns the parser/scheduler utilities into a problem-solving agent interface.

# What: Default GPT model name for future LLM-backed reasoning.
# Purpose: Records the target reasoning model without requiring API access for local operation.
DEFAULT_REASONING_MODEL = "gpt-5.4-mini"


# What: LLM adapter protocol.
# Purpose: Allows GPT-5.4-mini or another model to be injected without coupling core scheduling to one API.
class ReasoningClient(Protocol):
    # What: Reasoning request method.
    # Purpose: Lets the agent ask for strategy/explanation while keeping Python tools authoritative.
    def reason(self, prompt: str, model: str = DEFAULT_REASONING_MODEL) -> str:
        ...


# What: Inferred timing rule for an operation signature.
# Purpose: Captures how the reference schedule positions an activity relative to order due date.
@dataclass(frozen=True)
class TimingRule:
    operation_no: str
    activity_id: str
    activity_name: str
    phase: str
    avg_start_offset_minutes: int
    avg_finish_offset_minutes: int
    sample_count: int


# What: Inferred categorical output-field rule.
# Purpose: Learns D6-style field values such as load status and relief flags by operation signature.
@dataclass(frozen=True)
class FieldRule:
    operation_no: str
    activity_id: str
    activity_name: str
    phase: str
    field_name: str
    value: str
    sample_count: int
    confidence: float


# What: Agent analysis result.
# Purpose: Stores validation, inferred rules, differences, and human-readable findings together.
@dataclass
class AgentAnalysis:
    issues: list[ValidationIssue]
    timing_rules: list[TimingRule]
    field_rules: list[FieldRule]
    dependency_edges: list[tuple[str, str]]
    column_differences: list[tuple[str, int]]
    divergences: list["TimingDivergence"] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)


# What: Row-level timing divergence.
# Purpose: Explains how one generated activity differs from the given middle-level schedule.
@dataclass(frozen=True)
class TimingDivergence:
    wbs: str
    part_no: str
    operation_no: str
    activity_id: str
    activity_name: str
    phase: str
    generated_start: str
    reference_start: str
    generated_finish: str
    reference_finish: str
    start_delta_hours: float
    finish_delta_hours: float
    resource_match: bool
    load_status_match: bool
    relief_flag_match: bool
    internal_external_match: bool
    likely_cause: str


# What: Agent solve result.
# Purpose: Returns all machine-readable and human-readable outputs from one agent run.
@dataclass
class AgentResult:
    strategy: str
    schedule_rows: list[dict[str, str]]
    analysis: AgentAnalysis
    comparison_rows: list[dict[str, object]]
    schedule_path: Path | None = None
    report_path: Path | None = None


# What: Planning and scheduling agent.
# Purpose: Coordinates data validation, rule inference, schedule generation, comparison, and explanation.
class PlanningSchedulingAgent:
    # What: Agent constructor.
    # Purpose: Loads the AIPM dataset and configures optional LLM-backed reasoning.
    def __init__(
        self,
        data_dir: str | Path = "data",
        reasoning_client: ReasoningClient | None = None,
        model: str = DEFAULT_REASONING_MODEL,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.dataset = AIPMDataset.from_data_dir(self.data_dir)
        self.reasoning_client = reasoning_client
        self.model = model

    # What: End-to-end problem-solving workflow.
    # Purpose: Produces a schedule, diagnostics, optional CSV/report artifacts, and explanation.
    def solve(
        self,
        problem: str = "Generate a middle-level plan and schedule.",
        strategy: str = "reference_learning",
        output_path: str | Path | None = "outputs/agent_middle_schedule.csv",
        report_path: str | Path | None = "outputs/agent_schedule_report.html",
    ) -> AgentResult:
        analysis = self.analyze_reference_logic()
        schedule_rows = self.generate_schedule(strategy=strategy)
        comparison_rows = compare_with_reference(schedule_rows, self.dataset.reference_schedule)
        analysis.column_differences = column_difference_counts(
            schedule_rows, self.dataset.reference_schedule
        )
        analysis.divergences = self.analyze_timing_divergence(schedule_rows)
        analysis.findings = self.explain_gaps(problem, strategy, comparison_rows, analysis)

        written_schedule = None
        if output_path:
            written_schedule = Path(output_path)
            written_schedule.parent.mkdir(parents=True, exist_ok=True)
            write_middle_schedule(schedule_rows, written_schedule)

        written_report = None
        if report_path:
            written_report = Path(report_path)
            written_report.parent.mkdir(parents=True, exist_ok=True)
            schedule_reference = written_schedule or Path("outputs/agent_middle_schedule.csv")
            written_report.write_text(
                build_report_html(
                    self.dataset,
                    schedule_rows,
                    schedule_reference,
                    agent_findings=analysis.findings,
                ),
                encoding="utf-8",
            )

        return AgentResult(
            strategy=strategy,
            schedule_rows=schedule_rows,
            analysis=analysis,
            comparison_rows=comparison_rows,
            schedule_path=written_schedule,
            report_path=written_report,
        )

    # What: Reference schedule analysis.
    # Purpose: Learns reusable timing patterns and process-order hints from the given schedule.
    def analyze_reference_logic(self) -> AgentAnalysis:
        issues = self.dataset.validate()
        timing_rules = self.infer_timing_rules()
        dependency_edges = self.infer_dependencies()
        column_differences = column_difference_counts(
            build_middle_schedule(self.dataset), self.dataset.reference_schedule
        )
        return AgentAnalysis(
            issues=issues,
            timing_rules=timing_rules,
            field_rules=self.infer_field_rules(),
            dependency_edges=dependency_edges,
            column_differences=column_differences,
        )

    # What: Reference-derived timing rule inference.
    # Purpose: Learns average start/finish offsets from due date by operation signature.
    def infer_timing_rules(self) -> list[TimingRule]:
        products = self.dataset.products_by_wbs
        grouped: dict[tuple[str, str, str, str], list[tuple[int, int]]] = {}

        for row in self.dataset.reference_schedule:
            due = parse_datetime(products.get(row.get("WBS", ""), {}).get("納期", ""))
            start = parse_datetime(row.get("スケジュール結果開始日時", ""))
            finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
            if not due or not start or not finish:
                continue
            key = (
                row.get("工程NO", ""),
                row.get("作業工程ID", ""),
                row.get("作業工程名称", ""),
                row.get("基本工区名称", ""),
            )
            grouped.setdefault(key, []).append(
                (
                    int((start - due).total_seconds() // 60),
                    int((finish - due).total_seconds() // 60),
                )
            )

        rules = []
        for key, offsets in grouped.items():
            start_avg = round(sum(offset[0] for offset in offsets) / len(offsets))
            finish_avg = round(sum(offset[1] for offset in offsets) / len(offsets))
            rules.append(
                TimingRule(
                    operation_no=key[0],
                    activity_id=key[1],
                    activity_name=key[2],
                    phase=key[3],
                    avg_start_offset_minutes=start_avg,
                    avg_finish_offset_minutes=finish_avg,
                    sample_count=len(offsets),
                )
            )
        return sorted(rules, key=lambda rule: int(rule.operation_no or 0))

    # What: Reference-derived field rule inference.
    # Purpose: Learns categorical schedule fields that the baseline currently guesses too simply.
    def infer_field_rules(self) -> list[FieldRule]:
        target_fields = [
            "工程計画内外区分",
            "負荷状態",
            "最早最遅逆転救済対象工程",
            "スケジュール状態",
        ]
        counters: dict[tuple[str, str, str, str, str], dict[str, int]] = {}
        for row in self.dataset.reference_schedule:
            signature = _operation_signature(row)
            for field_name in target_fields:
                key = (*signature, field_name)
                value = row.get(field_name, "")
                bucket = counters.setdefault(key, {})
                bucket[value] = bucket.get(value, 0) + 1

        rules = []
        for key, counts in counters.items():
            value, count = max(counts.items(), key=lambda item: item[1])
            total = sum(counts.values())
            rules.append(
                FieldRule(
                    operation_no=key[0],
                    activity_id=key[1],
                    activity_name=key[2],
                    phase=key[3],
                    field_name=key[4],
                    value=value,
                    sample_count=total,
                    confidence=count / total if total else 0,
                )
            )
        return sorted(
            rules,
            key=lambda rule: (
                int(rule.operation_no or 0),
                rule.field_name,
            ),
        )

    # What: Dependency inference from reference timing.
    # Purpose: Extracts likely operation precedence edges by observing sorted activities per WBS.
    def infer_dependencies(self) -> list[tuple[str, str]]:
        edges: set[tuple[str, str]] = set()
        rows_by_wbs: dict[str, list[dict[str, str]]] = {}
        for row in self.dataset.reference_schedule:
            rows_by_wbs.setdefault(row.get("WBS", ""), []).append(row)

        for rows in rows_by_wbs.values():
            ordered = sorted(
                rows,
                key=lambda row: parse_datetime(row.get("スケジュール結果開始日時", ""))
                or datetime.max,
            )
            for before, after in zip(ordered, ordered[1:]):
                before_id = _operation_label(before)
                after_id = _operation_label(after)
                if before_id != after_id:
                    edges.add((before_id, after_id))
        return sorted(edges)

    # What: Row-level timing divergence analyzer.
    # Purpose: Finds the activities where generated timing differs most from the given schedule.
    def analyze_timing_divergence(
        self, schedule_rows: list[dict[str, str]]
    ) -> list[TimingDivergence]:
        reference_by_key = {_activity_key(row): row for row in self.dataset.reference_schedule}
        divergences = []
        for row in schedule_rows:
            reference = reference_by_key.get(_activity_key(row))
            if not reference:
                continue
            generated_start = parse_datetime(row.get("スケジュール結果開始日時", ""))
            reference_start = parse_datetime(reference.get("スケジュール結果開始日時", ""))
            generated_finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
            reference_finish = parse_datetime(reference.get("スケジュール結果終了日時", ""))
            if not generated_start or not reference_start or not generated_finish or not reference_finish:
                continue

            start_delta = (generated_start - reference_start).total_seconds() / 3600
            finish_delta = (generated_finish - reference_finish).total_seconds() / 3600
            resource_match = row.get("資源ID", "") == reference.get("資源ID", "")
            load_status_match = row.get("負荷状態", "") == reference.get("負荷状態", "")
            relief_flag_match = row.get("最早最遅逆転救済対象工程", "") == reference.get(
                "最早最遅逆転救済対象工程", ""
            )
            internal_external_match = row.get("工程計画内外区分", "") == reference.get(
                "工程計画内外区分", ""
            )
            divergences.append(
                TimingDivergence(
                    wbs=row.get("WBS", ""),
                    part_no=row.get("部品NO", ""),
                    operation_no=row.get("工程NO", ""),
                    activity_id=row.get("作業工程ID", ""),
                    activity_name=row.get("作業工程名称", ""),
                    phase=row.get("基本工区名称", ""),
                    generated_start=row.get("スケジュール結果開始日時", ""),
                    reference_start=reference.get("スケジュール結果開始日時", ""),
                    generated_finish=row.get("スケジュール結果終了日時", ""),
                    reference_finish=reference.get("スケジュール結果終了日時", ""),
                    start_delta_hours=start_delta,
                    finish_delta_hours=finish_delta,
                    resource_match=resource_match,
                    load_status_match=load_status_match,
                    relief_flag_match=relief_flag_match,
                    internal_external_match=internal_external_match,
                    likely_cause=_classify_divergence_cause(
                        start_delta,
                        finish_delta,
                        resource_match,
                        load_status_match,
                        relief_flag_match,
                        internal_external_match,
                    ),
                )
            )
        return sorted(
            divergences,
            key=lambda item: max(abs(item.start_delta_hours), abs(item.finish_delta_hours)),
            reverse=True,
        )

    # What: Schedule generation strategy selector.
    # Purpose: Lets the agent choose between deterministic baseline and reference-informed scheduling.
    def generate_schedule(self, strategy: str = "reference_learning") -> list[dict[str, str]]:
        if strategy == "baseline":
            return build_middle_schedule(self.dataset)
        if strategy == "reference_replay":
            return [dict(row) for row in self.dataset.reference_schedule]
        if strategy == "reference_learning":
            return self._generate_reference_learned_schedule()
        if strategy == "field_repair":
            return self._generate_field_repair_schedule()
        if strategy == "ortools_cp":
            return self._generate_ortools_schedule()
        if strategy == "ortools_precedence":
            return self._generate_ortools_precedence_schedule()
        raise ValueError(f"unknown scheduling strategy: {strategy}")

    # What: Reference-learning schedule generator.
    # Purpose: Uses inferred due-date offsets to create a closer D6-style schedule than the baseline.
    def _generate_reference_learned_schedule(self) -> list[dict[str, str]]:
        baseline_rows = build_middle_schedule(self.dataset)
        rule_by_signature = {
            (rule.operation_no, rule.activity_id, rule.activity_name, rule.phase): rule
            for rule in self.infer_timing_rules()
        }
        products = self.dataset.products_by_wbs
        learned_rows = []

        for row in baseline_rows:
            key = (
                row.get("工程NO", ""),
                row.get("作業工程ID", ""),
                row.get("作業工程名称", ""),
                row.get("基本工区名称", ""),
            )
            rule = rule_by_signature.get(key)
            due = parse_datetime(products.get(row.get("WBS", ""), {}).get("納期", ""))
            learned = dict(row)
            if rule and due:
                start = due + timedelta(minutes=rule.avg_start_offset_minutes)
                finish = due + timedelta(minutes=rule.avg_finish_offset_minutes)
                learned["スケジュール結果開始日時"] = format_schedule_datetime(start)
                learned["スケジュール結果終了日時"] = format_schedule_datetime(finish)
            learned_rows.append(learned)
        return learned_rows

    # What: Field-repair schedule generator.
    # Purpose: Applies learned D6-style status/flag fields on top of reference-learned timing.
    def _generate_field_repair_schedule(self) -> list[dict[str, str]]:
        rows = self._generate_reference_learned_schedule()
        field_rules = {
            (
                rule.operation_no,
                rule.activity_id,
                rule.activity_name,
                rule.phase,
                rule.field_name,
            ): rule
            for rule in self.infer_field_rules()
        }
        for row in rows:
            signature = _operation_signature(row)
            for field_name in (
                "工程計画内外区分",
                "負荷状態",
                "最早最遅逆転救済対象工程",
                "スケジュール状態",
            ):
                rule = field_rules.get((*signature, field_name))
                if rule and rule.confidence >= 0.5:
                    row[field_name] = rule.value
        return rows

    # What: OR-Tools-backed schedule generator.
    # Purpose: Uses CP-SAT to enforce resource no-overlap while staying close to learned targets.
    def _generate_ortools_schedule(self) -> list[dict[str, str]]:
        from ortools_scheduler import solve_with_ortools

        repaired_rows = self._generate_field_repair_schedule()
        return solve_with_ortools(
            repaired_rows,
            resource_capacities=self._resource_capacities(),
            activity_demands=self._activity_demands(),
        )

    # What: OR-Tools schedule generator with learned precedence.
    # Purpose: Adds stable reference-derived precedence rules to capacity-constrained scheduling.
    def _generate_ortools_precedence_schedule(self) -> list[dict[str, str]]:
        from ortools_scheduler import solve_with_ortools

        repaired_rows = self._generate_field_repair_schedule()
        return solve_with_ortools(
            repaired_rows,
            resource_capacities=self._resource_capacities(),
            activity_demands=self._activity_demands(),
            precedence_edges=self.combined_precedence_rules(),
        )

    # What: Combined precedence-rule provider.
    # Purpose: Uses both schedule-derived stable edges and documented flowchart-derived edges.
    def combined_precedence_rules(
        self,
    ) -> set[tuple[tuple[str, str, str, str], tuple[str, str, str, str]]]:
        from marine_design_process_rules import documented_precedence_edges

        return self.infer_stable_precedence_rules() | self._reference_consistent_edges(
            documented_precedence_edges()
        )

    # What: Reference-consistency filter for documented process edges.
    # Purpose: Prevents ambiguous flowchart mappings from becoming infeasible hard constraints.
    def _reference_consistent_edges(
        self,
        edges: set[tuple[tuple[str, str, str, str], tuple[str, str, str, str]]],
    ) -> set[tuple[tuple[str, str, str, str], tuple[str, str, str, str]]]:
        rows_by_wbs: dict[str, dict[tuple[str, str, str, str], dict[str, str]]] = {}
        for row in self.dataset.reference_schedule:
            rows_by_wbs.setdefault(row.get("WBS", ""), {})[_operation_signature(row)] = row

        consistent_edges = set()
        for before_signature, after_signature in edges:
            observations = 0
            violations = 0
            for rows in rows_by_wbs.values():
                before = rows.get(before_signature)
                after = rows.get(after_signature)
                if not before or not after:
                    continue
                before_finish = parse_datetime(before.get("スケジュール結果終了日時", ""))
                after_start = parse_datetime(after.get("スケジュール結果開始日時", ""))
                if not before_finish or not after_start:
                    continue
                observations += 1
                if before_finish > after_start:
                    violations += 1
            if observations and violations == 0:
                consistent_edges.add((before_signature, after_signature))
        return consistent_edges

    # What: Stable precedence-rule inference.
    # Purpose: Keeps only adjacent reference edges observed consistently enough across orders.
    def infer_stable_precedence_rules(
        self,
        min_support: int = 2,
        min_confidence: float = 0.67,
    ) -> set[tuple[tuple[str, str, str, str], tuple[str, str, str, str]]]:
        rows_by_wbs: dict[str, list[dict[str, str]]] = {}
        for row in self.dataset.reference_schedule:
            rows_by_wbs.setdefault(row.get("WBS", ""), []).append(row)

        support: dict[tuple[tuple[str, str, str, str], tuple[str, str, str, str]], int] = {}
        opportunities: dict[tuple[tuple[str, str, str, str], tuple[str, str, str, str]], int] = {}
        for rows in rows_by_wbs.values():
            signatures = {_operation_signature(row) for row in rows}
            ordered = sorted(
                rows,
                key=lambda row: parse_datetime(row.get("スケジュール結果開始日時", ""))
                or datetime.max,
            )
            adjacent_edges = set()
            for before, after in zip(ordered, ordered[1:]):
                before_signature = _operation_signature(before)
                after_signature = _operation_signature(after)
                if before_signature != after_signature:
                    adjacent_edges.add((before_signature, after_signature))
            for edge in adjacent_edges:
                support[edge] = support.get(edge, 0) + 1
            for before_signature in signatures:
                for after_signature in signatures:
                    if before_signature != after_signature:
                        opportunities[(before_signature, after_signature)] = (
                            opportunities.get((before_signature, after_signature), 0) + 1
                        )

        stable_edges = set()
        for edge, count in support.items():
            confidence = count / opportunities.get(edge, count)
            if count >= min_support and confidence >= min_confidence:
                stable_edges.add(edge)
        return stable_edges

    # What: Resource capacity map for solver backends.
    # Purpose: Converts resource master capacity fields into numeric CP-SAT capacities.
    def _resource_capacities(self) -> dict[str, float]:
        capacities = {}
        for resource in self.dataset.resources:
            resource_id = resource.get("資源ID", "")
            try:
                capacity = float(resource.get("保有量", "") or 1)
            except ValueError:
                capacity = 1
            if resource_id:
                capacities[resource_id] = max(capacity, 1)
        return capacities

    # What: Activity demand map for solver backends.
    # Purpose: Converts work-order required quantity into numeric CP-SAT demands.
    def _activity_demands(self) -> dict[tuple[str, str, str, str], float]:
        demands = {}
        for activity in self.dataset.activities:
            try:
                demand = float(activity.get("作業者必要量", "") or 1)
            except ValueError:
                demand = 1
            demands[
                (
                    activity.get("WBS", ""),
                    activity.get("部品NO", ""),
                    activity.get("工程NO", ""),
                    activity.get("作業工程ID", ""),
                )
            ] = max(demand, 0.001)
        return demands

    # What: Gap explanation generator.
    # Purpose: Produces concise findings using either Python summaries or an optional LLM client.
    def explain_gaps(
        self,
        problem: str,
        strategy: str,
        comparisons: list[dict[str, object]],
        analysis: AgentAnalysis,
    ) -> list[str]:
        matched = [row for row in comparisons if row["matched"]]
        exact = sum(1 for row in matched if row["exact_match"])
        resource_matches = sum(1 for row in matched if row["resource_match"])
        avg_start_delta = _average_abs_hours(matched, "start_delta_minutes")
        avg_finish_delta = _average_abs_hours(matched, "finish_delta_minutes")
        baseline_comparisons = compare_with_reference(
            build_middle_schedule(self.dataset), self.dataset.reference_schedule
        )
        baseline_start_delta = _average_abs_hours(
            [row for row in baseline_comparisons if row["matched"]],
            "start_delta_minutes",
        )
        baseline_finish_delta = _average_abs_hours(
            [row for row in baseline_comparisons if row["matched"]],
            "finish_delta_minutes",
        )

        findings = [
            f"Strategy '{strategy}' generated {len(comparisons)} schedule rows for {len(self.dataset.product_orders)} orders.",
            f"Exact row matches against the given middle schedule: {exact} / {len(matched)}.",
            f"Resource assignment matches: {resource_matches} / {len(matched)}.",
            f"Average absolute start-time delta: {avg_start_delta:.1f} hours.",
            f"Average absolute finish-time delta: {avg_finish_delta:.1f} hours.",
            f"Baseline start-time delta was {baseline_start_delta:.1f} hours, so this strategy improves it by {baseline_start_delta - avg_start_delta:.1f} hours on average.",
            f"Baseline finish-time delta was {baseline_finish_delta:.1f} hours, so this strategy improves it by {baseline_finish_delta - avg_finish_delta:.1f} hours on average.",
        ]
        if strategy == "ortools_precedence":
            from marine_design_process_rules import documented_precedence_edges

            documented_edges = documented_precedence_edges()
            accepted_documented_edges = self._reference_consistent_edges(documented_edges)
            findings.append(
                "Precedence constraints used: "
                f"{len(self.infer_stable_precedence_rules())} schedule-derived stable edges "
                f"+ {len(accepted_documented_edges)} reference-consistent documented flowchart edges "
                f"out of {len(documented_edges)} candidates."
            )
        if analysis.column_differences:
            top_columns = ", ".join(
                f"{column} ({count})" for column, count in analysis.column_differences[:5]
            )
            findings.append(f"Most different output fields: {top_columns}.")
        if analysis.divergences:
            top = analysis.divergences[0]
            findings.append(
                "Largest timing gap: "
                f"{top.wbs} {top.operation_no} {top.activity_name}, "
                f"start delta {top.start_delta_hours:.1f}h, "
                f"finish delta {top.finish_delta_hours:.1f}h, "
                f"likely cause: {top.likely_cause}."
            )

        if self.reasoning_client:
            llm_prompt = self._build_reasoning_prompt(problem, strategy, findings, analysis)
            findings.append(self.reasoning_client.reason(llm_prompt, model=self.model))
        else:
            findings.append(
                "No LLM client is configured yet; findings are generated from deterministic schedule metrics."
            )
        return findings

    # What: Reasoning prompt builder.
    # Purpose: Packages compact schedule facts for a future GPT-5.4-mini reasoning call.
    def _build_reasoning_prompt(
        self,
        problem: str,
        strategy: str,
        findings: list[str],
        analysis: AgentAnalysis,
    ) -> str:
        payload = {
            "problem": problem,
            "strategy": strategy,
            "model_target": self.model,
            "findings": findings,
            "top_column_differences": analysis.column_differences[:10],
            "field_rule_count": len(analysis.field_rules),
            "low_confidence_field_rules": [
                {
                    "operation": rule.operation_no,
                    "activity": rule.activity_name,
                    "field": rule.field_name,
                    "value": rule.value,
                    "confidence": round(rule.confidence, 2),
                }
                for rule in analysis.field_rules
                if rule.confidence < 1
            ][:12],
            "top_timing_divergences": [
                {
                    "wbs": item.wbs,
                    "operation": item.operation_no,
                    "activity": item.activity_name,
                    "phase": item.phase,
                    "start_delta_hours": round(item.start_delta_hours, 1),
                    "finish_delta_hours": round(item.finish_delta_hours, 1),
                    "likely_cause": item.likely_cause,
                    "load_status_match": item.load_status_match,
                    "relief_flag_match": item.relief_flag_match,
                }
                for item in analysis.divergences[:12]
            ],
            "timing_rule_count": len(analysis.timing_rules),
            "dependency_edge_count": len(analysis.dependency_edges),
        }
        return (
            "You are the reasoning layer for an AIPM planning and scheduling agent. "
            "Explain the schedule quality, likely causes of gaps, and next improvement steps.\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )


# What: Operation display helper.
# Purpose: Creates compact labels for inferred dependency edges.
def _operation_label(row: dict[str, str]) -> str:
    return f"{row.get('工程NO', '')}:{row.get('作業工程名称', '')}"


# What: Operation signature helper.
# Purpose: Provides the stable key used to learn timing and field rules across orders.
def _operation_signature(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("工程NO", ""),
        row.get("作業工程ID", ""),
        row.get("作業工程名称", ""),
        row.get("基本工区名称", ""),
    )


# What: Activity identity helper.
# Purpose: Matches generated and reference schedule rows at activity level.
def _activity_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("WBS", ""),
        row.get("部品NO", ""),
        row.get("工程NO", ""),
        row.get("作業工程ID", ""),
    )


# What: Divergence cause classifier.
# Purpose: Gives the agent a first-pass explanation for why a row differs from reference timing.
def _classify_divergence_cause(
    start_delta_hours: float,
    finish_delta_hours: float,
    resource_match: bool,
    load_status_match: bool,
    relief_flag_match: bool,
    internal_external_match: bool,
) -> str:
    if not resource_match:
        return "resource assignment mismatch"
    if not relief_flag_match:
        return "earliest/latest relief flag mismatch"
    if not load_status_match:
        return "load-state mismatch"
    if not internal_external_match:
        return "internal/external planning classification mismatch"
    if abs(start_delta_hours - finish_delta_hours) < 1:
        return "phase anchor or due-date offset mismatch"
    if abs(start_delta_hours) > abs(finish_delta_hours) * 1.5:
        return "start constraint mismatch"
    if abs(finish_delta_hours) > abs(start_delta_hours) * 1.5:
        return "duration or finish constraint mismatch"
    return "dependency/calendar propagation mismatch"


# What: Average absolute delta helper.
# Purpose: Summarizes timing differences in hours for generated-vs-reference comparisons.
def _average_abs_hours(rows: list[dict[str, object]], field: str) -> float:
    if not rows:
        return 0.0
    return sum(abs(int(row[field])) for row in rows) / len(rows) / 60


# What: Agent findings writer.
# Purpose: Saves a concise text summary next to generated CSV/report artifacts.
def write_findings(result: AgentResult, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "AIPM Planning and Scheduling Agent Findings",
        f"Strategy: {result.strategy}",
        f"Schedule: {result.schedule_path or ''}",
        f"Report: {result.report_path or ''}",
        "",
        "Findings:",
    ]
    lines.extend(f"- {finding}" for finding in result.analysis.findings)
    lines.extend(
        [
            "",
            "Learned field rules:",
            *[
                (
                    f"- {rule.operation_no} {rule.activity_name} {rule.field_name}="
                    f"{rule.value} confidence={rule.confidence:.2f} samples={rule.sample_count}"
                )
                for rule in result.analysis.field_rules[:40]
            ],
            "",
            "Top timing divergences:",
            *[
                (
                    f"- {item.wbs} {item.operation_no} {item.activity_name}: "
                    f"start {item.start_delta_hours:.1f}h, "
                    f"finish {item.finish_delta_hours:.1f}h, "
                    f"cause={item.likely_cause}"
                )
                for item in result.analysis.divergences[:20]
            ],
            "",
            "Inferred dependency edges:",
            *[f"- {before} -> {after}" for before, after in result.analysis.dependency_edges[:50]],
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


# What: Timing-divergence CSV writer.
# Purpose: Saves row-level diagnostics for spreadsheet review and rule tuning.
def write_timing_divergences(divergences: list[TimingDivergence], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "WBS",
        "部品NO",
        "工程NO",
        "作業工程ID",
        "作業工程名称",
        "基本工区名称",
        "generated_start",
        "reference_start",
        "generated_finish",
        "reference_finish",
        "start_delta_hours",
        "finish_delta_hours",
        "resource_match",
        "load_status_match",
        "relief_flag_match",
        "internal_external_match",
        "likely_cause",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for item in divergences:
            writer.writerow(
                {
                    "WBS": item.wbs,
                    "部品NO": item.part_no,
                    "工程NO": item.operation_no,
                    "作業工程ID": item.activity_id,
                    "作業工程名称": item.activity_name,
                    "基本工区名称": item.phase,
                    "generated_start": item.generated_start,
                    "reference_start": item.reference_start,
                    "generated_finish": item.generated_finish,
                    "reference_finish": item.reference_finish,
                    "start_delta_hours": f"{item.start_delta_hours:.2f}",
                    "finish_delta_hours": f"{item.finish_delta_hours:.2f}",
                    "resource_match": item.resource_match,
                    "load_status_match": item.load_status_match,
                    "relief_flag_match": item.relief_flag_match,
                    "internal_external_match": item.internal_external_match,
                    "likely_cause": item.likely_cause,
                }
            )


# What: Command-line interface for the planning/scheduling agent.
# Purpose: Runs the full agent workflow from terminal or future automation.
def main() -> int:
    parser = argparse.ArgumentParser(description="Run the AIPM planning and scheduling agent.")
    parser.add_argument("--data-dir", default="data", help="Folder containing AIPM CSV files.")
    parser.add_argument(
        "--strategy",
        default="reference_learning",
        choices=[
            "baseline",
            "reference_learning",
            "field_repair",
            "ortools_cp",
            "ortools_precedence",
            "reference_replay",
        ],
        help="Schedule generation strategy.",
    )
    parser.add_argument(
        "--problem",
        default="Generate a middle-level plan and schedule and compare it to the given schedule.",
        help="Problem statement for the agent.",
    )
    parser.add_argument(
        "--output",
        default="outputs/agent_middle_schedule.csv",
        help="Output CSV path for the generated schedule.",
    )
    parser.add_argument(
        "--report",
        default="outputs/agent_schedule_report.html",
        help="Output HTML path for the visual report.",
    )
    parser.add_argument(
        "--findings",
        default="outputs/agent_findings.txt",
        help="Output text path for agent findings.",
    )
    parser.add_argument(
        "--divergences",
        default="outputs/agent_timing_divergences.csv",
        help="Output CSV path for row-level timing divergence diagnostics.",
    )
    parser.add_argument(
        "--use-openai",
        action="store_true",
        help="Enable GPT-backed reasoning through OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_REASONING_MODEL,
        help="OpenAI model to use when --use-openai is enabled.",
    )
    args = parser.parse_args()

    reasoning_client = None
    if args.use_openai:
        from openai_reasoning_client import OpenAIReasoningClient

        reasoning_client = OpenAIReasoningClient()

    agent = PlanningSchedulingAgent(
        data_dir=args.data_dir,
        reasoning_client=reasoning_client,
        model=args.model,
    )
    result = agent.solve(
        problem=args.problem,
        strategy=args.strategy,
        output_path=args.output,
        report_path=args.report,
    )
    write_findings(result, args.findings)
    write_timing_divergences(result.analysis.divergences, args.divergences)

    print(f"Strategy: {result.strategy}")
    print(f"Generated schedule: {result.schedule_path}")
    print(f"Generated report: {result.report_path}")
    print(f"Findings: {args.findings}")
    print(f"Timing divergences: {args.divergences}")
    for finding in result.analysis.findings:
        print(f"- {finding}")
    return 1 if any(issue.severity == "error" for issue in result.analysis.issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
