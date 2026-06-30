from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aipm_data import (
    AIPMDataset,
    MIDDLE_SCHEDULE_COLUMNS,
    build_middle_schedule,
    parse_datetime,
    parse_japanese_duration,
    write_middle_schedule,
)
from aipm_visualize import build_report_html, compare_with_reference, render_finding_html
from openai_reasoning_client import extract_response_text
from planning_scheduling_agent import PlanningSchedulingAgent, write_timing_divergences


# What: Unit tests for the current AIPM parser and baseline scheduler.
# Purpose: Protects the sample-data contract as the future GPT-backed agent layer evolves.
class AIPMDataTests(unittest.TestCase):
    # What: Shared real dataset fixture.
    # Purpose: Loads the current CSV files once for all contract tests.
    @classmethod
    def setUpClass(cls) -> None:
        # These tests intentionally exercise the real sample files as the current agent contract.
        cls.dataset = AIPMDataset.from_data_dir("data")

    # What: End-to-end validation test.
    # Purpose: Ensures the current sample files have no blocking data-contract errors.
    def test_current_dataset_validates(self) -> None:
        issues = self.dataset.validate()
        errors = [issue for issue in issues if issue.severity == "error"]
        self.assertEqual(errors, [])

    # What: Activity/reference row-count test.
    # Purpose: Confirms one schedulable activity maps to one middle-schedule row.
    def test_real_activities_match_reference_schedule_count(self) -> None:
        self.assertEqual(len(self.dataset.activities), 86)
        self.assertEqual(len(self.dataset.reference_schedule), 86)

    # What: Japanese duration parsing test.
    # Purpose: Verifies D6 duration text can be converted into scheduling minutes.
    def test_duration_parser(self) -> None:
        self.assertEqual(parse_japanese_duration("      66 時間 00 分"), 3960)
        self.assertEqual(parse_japanese_duration("       8 時間 20 分"), 500)

    # What: Date/datetime parsing test.
    # Purpose: Verifies order dates normalize consistently before schedule arithmetic.
    def test_datetime_parser(self) -> None:
        self.assertEqual(parse_datetime("2026/03/27 17:00").strftime("%Y-%m-%d %H:%M"), "2026-03-27 17:00")
        self.assertEqual(parse_datetime("2026/03/26").strftime("%Y-%m-%d %H:%M"), "2026-03-26 17:00")

    # What: Generated schedule schema test.
    # Purpose: Ensures baseline output remains compatible with the D6-style reference file.
    def test_generated_schedule_uses_reference_schema(self) -> None:
        rows = build_middle_schedule(self.dataset)
        self.assertEqual(len(rows), 86)
        # Preserve the D6-style output column order; downstream CSV consumers may depend on it.
        self.assertEqual(list(rows[0]), MIDDLE_SCHEDULE_COLUMNS)

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "schedule.csv"
            write_middle_schedule(rows, output)
            self.assertTrue(output.read_text(encoding="utf-8-sig").startswith(",".join(MIDDLE_SCHEDULE_COLUMNS)))

    # What: Visual report generation test.
    # Purpose: Ensures all requested visual sections are present in the HTML artifact.
    def test_visual_report_contains_requested_sections(self) -> None:
        rows = build_middle_schedule(self.dataset)
        comparisons = compare_with_reference(rows, self.dataset.reference_schedule)
        html = build_report_html(self.dataset, rows, Path("outputs/generated_middle_schedule.csv"))

        self.assertEqual(len(comparisons), 86)
        self.assertIn("Dashboard Summary", html)
        self.assertIn("Gantt Chart", html)
        self.assertIn("Resource Load", html)
        self.assertIn("Order Timelines", html)
        self.assertIn("Plan vs Reference Comparison", html)
        self.assertIn("Column Difference Counts", html)
        self.assertIn("Largest Generated vs Given Timing Gaps", html)
        self.assertIn("Field Rule Diagnostics", html)
        self.assertIn("Timing Divergence Diagnostics", html)
        self.assertIn("Process Flow", html)

    # What: Report diagnosis section test.
    # Purpose: Ensures agent findings can be embedded into the visual HTML report.
    def test_visual_report_contains_agent_diagnosis(self) -> None:
        rows = build_middle_schedule(self.dataset)
        html = build_report_html(
            self.dataset,
            rows,
            Path("outputs/generated_middle_schedule.csv"),
            agent_findings=["AI diagnosis placeholder"],
        )

        self.assertIn("AI Diagnosis", html)
        self.assertIn("AI diagnosis placeholder", html)

    # What: GPT Markdown rendering test.
    # Purpose: Ensures AI diagnosis headings and bullets are readable in the HTML report.
    def test_render_finding_html_formats_markdown(self) -> None:
        rendered = render_finding_html(
            "### Schedule quality summary\n\n- **Resource assignment quality is strong**\n- Uses `負荷状態`."
        )

        self.assertIn("<h3>Schedule quality summary</h3>", rendered)
        self.assertIn("<strong>Resource assignment quality is strong</strong>", rendered)
        self.assertIn("<code>負荷状態</code>", rendered)

    # What: AI Diagnosis section layout test.
    # Purpose: Ensures long GPT Markdown appears as rich report content, not one crowded list item.
    def test_agent_diagnosis_separates_long_markdown(self) -> None:
        html = build_report_html(
            self.dataset,
            build_middle_schedule(self.dataset),
            Path("outputs/generated_middle_schedule.csv"),
            agent_findings=[
                "Short metric finding.",
                "### Schedule quality summary\n\n- **Resource assignment quality is strong**",
            ],
        )

        self.assertIn('<div class="diagnosis-markdown">', html)
        self.assertIn("<h3>Schedule quality summary</h3>", html)

    # What: Agent workflow test.
    # Purpose: Verifies the planning/scheduling agent can solve without an LLM client.
    def test_planning_scheduling_agent_solves(self) -> None:
        agent = PlanningSchedulingAgent(data_dir="data")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = agent.solve(
                strategy="reference_learning",
                output_path=Path(temp_dir) / "agent_schedule.csv",
                report_path=Path(temp_dir) / "agent_report.html",
            )

            self.assertEqual(len(result.schedule_rows), 86)
            self.assertTrue(result.schedule_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertGreater(len(result.analysis.timing_rules), 0)
            self.assertGreater(len(result.analysis.dependency_edges), 0)
            self.assertGreater(len(result.analysis.divergences), 0)
            self.assertTrue(result.analysis.findings)

            divergence_path = Path(temp_dir) / "divergences.csv"
            write_timing_divergences(result.analysis.divergences, divergence_path)
            self.assertTrue(divergence_path.exists())
            self.assertIn("likely_cause", divergence_path.read_text(encoding="utf-8-sig"))

    # What: Agent LLM wiring test.
    # Purpose: Verifies the agent can call an injected reasoning client without real API access.
    def test_planning_scheduling_agent_uses_reasoning_client(self) -> None:
        class FakeReasoningClient:
            def reason(self, prompt: str, model: str) -> str:
                self.prompt = prompt
                self.model = model
                return "GPT-backed diagnosis would appear here."

        client = FakeReasoningClient()
        agent = PlanningSchedulingAgent(data_dir="data", reasoning_client=client, model="gpt-5.4-mini")
        result = agent.solve(strategy="reference_learning", output_path=None, report_path=None)

        self.assertEqual(client.model, "gpt-5.4-mini")
        self.assertIn("GPT-backed diagnosis would appear here.", result.analysis.findings)
        self.assertIn("AIPM planning and scheduling agent", client.prompt)

    # What: Reference-learning improvement test.
    # Purpose: Confirms inferred timing rules produce a closer schedule than the baseline.
    def test_reference_learning_improves_start_delta(self) -> None:
        agent = PlanningSchedulingAgent(data_dir="data")
        baseline = agent.generate_schedule(strategy="baseline")
        learned = agent.generate_schedule(strategy="reference_learning")
        baseline_comparison = compare_with_reference(baseline, self.dataset.reference_schedule)
        learned_comparison = compare_with_reference(learned, self.dataset.reference_schedule)

        baseline_delta = _avg_abs_delta(baseline_comparison, "start_delta_minutes")
        learned_delta = _avg_abs_delta(learned_comparison, "start_delta_minutes")
        self.assertLess(learned_delta, baseline_delta)

    # What: Field-repair strategy test.
    # Purpose: Confirms learned field rules reduce status/flag mismatches.
    def test_field_repair_reduces_field_mismatches(self) -> None:
        agent = PlanningSchedulingAgent(data_dir="data")
        learned = agent.generate_schedule(strategy="reference_learning")
        repaired = agent.generate_schedule(strategy="field_repair")

        learned_mismatches = _field_mismatches(learned, self.dataset.reference_schedule)
        repaired_mismatches = _field_mismatches(repaired, self.dataset.reference_schedule)
        self.assertLess(repaired_mismatches, learned_mismatches)

    # What: Reference replay report test.
    # Purpose: Ensures exact reference matches do not break zero-delta charts.
    def test_reference_replay_report_handles_zero_deltas(self) -> None:
        agent = PlanningSchedulingAgent(data_dir="data")
        rows = agent.generate_schedule(strategy="reference_replay")
        html = build_report_html(
            self.dataset,
            rows,
            Path("outputs/reference_replay_schedule.csv"),
        )

        self.assertIn("start times match the given reference", html)

    # What: OR-Tools strategy test.
    # Purpose: Confirms the constraint solver returns a complete capacity-feasible schedule.
    def test_ortools_strategy_generates_capacity_feasible_schedule(self) -> None:
        agent = PlanningSchedulingAgent(data_dir="data")
        rows = agent.generate_schedule(strategy="ortools_cp")

        self.assertEqual(len(rows), 86)
        self.assertEqual(list(rows[0]), MIDDLE_SCHEDULE_COLUMNS)
        self.assertEqual(
            _resource_capacity_violation_count(
                rows,
                agent._resource_capacities(),
                agent._activity_demands(),
            ),
            0,
        )

    # What: OR-Tools precedence strategy test.
    # Purpose: Confirms learned precedence rules are available and the strategy remains feasible.
    def test_ortools_precedence_strategy_generates_capacity_feasible_schedule(self) -> None:
        agent = PlanningSchedulingAgent(data_dir="data")
        edges = agent.infer_stable_precedence_rules()
        rows = agent.generate_schedule(strategy="ortools_precedence")

        self.assertGreater(len(edges), 0)
        self.assertEqual(len(rows), 86)
        self.assertEqual(
            _resource_capacity_violation_count(
                rows,
                agent._resource_capacities(),
                agent._activity_demands(),
            ),
            0,
        )


# What: Test helper for timing deltas.
# Purpose: Keeps agent improvement assertions readable.
def _avg_abs_delta(rows: list[dict[str, object]], field: str) -> float:
    return sum(abs(int(row[field])) for row in rows) / len(rows)


# What: Test helper for field mismatch counts.
# Purpose: Measures the effect of field-repair strategy on key D6-style status fields.
def _field_mismatches(
    generated_rows: list[dict[str, str]], reference_rows: list[dict[str, str]]
) -> int:
    fields = [
        "工程計画内外区分",
        "負荷状態",
        "最早最遅逆転救済対象工程",
        "スケジュール状態",
    ]
    key = lambda row: (
        row.get("WBS", ""),
        row.get("部品NO", ""),
        row.get("工程NO", ""),
        row.get("作業工程ID", ""),
    )
    generated_by_key = {key(row): row for row in generated_rows}
    reference_by_key = {key(row): row for row in reference_rows}
    return sum(
        1
        for row_key in set(generated_by_key) & set(reference_by_key)
        for field in fields
        if generated_by_key[row_key].get(field, "") != reference_by_key[row_key].get(field, "")
    )


# What: Resource-capacity violation counter for tests.
# Purpose: Verifies OR-Tools respects team capacity while allowing valid parallel work.
def _resource_capacity_violation_count(
    rows: list[dict[str, str]],
    capacities: dict[str, float],
    demands: dict[tuple[str, str, str, str], float],
) -> int:
    intervals_by_resource: dict[str, list[tuple[object, object, float]]] = {}
    for row in rows:
        start = parse_datetime(row.get("スケジュール結果開始日時", ""))
        finish = parse_datetime(row.get("スケジュール結果終了日時", ""))
        resource = row.get("資源ID", "")
        if start and finish and resource:
            key = (
                row.get("WBS", ""),
                row.get("部品NO", ""),
                row.get("工程NO", ""),
                row.get("作業工程ID", ""),
            )
            intervals_by_resource.setdefault(resource, []).append(
                (start, finish, demands.get(key, 1.0))
            )

    violations = 0
    for resource, intervals in intervals_by_resource.items():
        effective_capacity = max(
            capacities.get(resource, 1.0),
            max((demand for _, _, demand in intervals), default=1.0),
        )
        boundaries = sorted({point for start, finish, _ in intervals for point in (start, finish)})
        for left, right in zip(boundaries, boundaries[1:]):
            if left >= right:
                continue
            active_demand = sum(
                demand for start, finish, demand in intervals if start < right and finish > left
            )
            if active_demand > effective_capacity + 1e-9:
                violations += 1
    return violations


# What: OpenAI response extraction test.
# Purpose: Verifies the API adapter can read structured Responses API text output.
class OpenAIReasoningClientTests(unittest.TestCase):
    def test_extract_response_text_from_output_blocks(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Diagnosis text."},
                    ],
                }
            ]
        }
        self.assertEqual(extract_response_text(response), "Diagnosis text.")


if __name__ == "__main__":
    unittest.main()
