from __future__ import annotations

from dataclasses import dataclass


# What: Sponsor domain knowledge extracted from AIPM engineering-management notes.
# Purpose: Converts PDF #2 into explicit, reviewable rules that the scheduler can use or report.

# What: Operation signature type.
# Purpose: Identifies a reusable D6/AIPM activity type across WBS orders.
OperationSignature = tuple[str, str, str, str]


# What: Sponsor-documented knowledge item.
# Purpose: Preserves source-page traceability for executable and advisory rules.
@dataclass(frozen=True)
class SponsorRule:
    rule_id: str
    category: str
    source_pdf: str
    source_pages: tuple[int, ...]
    statement: str
    implementation_status: str
    implementation_note: str


# What: Sponsor precedence constraint.
# Purpose: Represents an operation-order relation that can become a hard solver constraint.
@dataclass(frozen=True)
class SponsorPrecedenceRule:
    rule_id: str
    before: OperationSignature
    after: OperationSignature
    source_pages: tuple[int, ...]
    rationale: str


# What: Sponsor temporal lag constraint.
# Purpose: Represents start/finish spacing rules from planner heuristics in PDF #2.
@dataclass(frozen=True)
class SponsorTemporalRule:
    rule_id: str
    before: OperationSignature
    after: OperationSignature
    relation: str
    min_lag_minutes: int | None
    max_lag_minutes: int | None
    source_pages: tuple[int, ...]
    rationale: str


# What: Operation signatures currently present in the AIPM scheduling data.
# Purpose: Gives sponsor rules stable targets without relying on localized row order.
OPERATION_SIGNATURES: dict[str, OperationSignature] = {
    "specification": ("1091", "1091", "仕様", "設計"),
    "basic_design": ("1002", "1002", "基本設計(海配)", "設計"),
    "approval": ("1092", "1092", "承認", "設計"),
    "drawing_issue": ("1093", "1093", "出図", "生設"),
    "copper_bar_drawing": ("3003", "3003", "銅帯図", "生設"),
    "panel": ("4001", "4001", "ﾊﾟﾈﾙ", "工作"),
    "frame": ("4002", "4002", "枠組", "工作"),
    "painting": ("5010", "5010", "塗装", "塗装"),
    "assembly_frame_mount": ("7101", "7101", "組立枠組器具付(海組1)", "組立"),
    "wiring": ("7103", "7103", "配線(海組1)", "組立"),
    "check_finish": ("7111", "7111", "ﾁｪｯｸ仕上(海組1)", "組立"),
    "inspection": ("8102", "8102", "検査(検1)", "検査"),
    "witness_inspection": ("8103", "8103", "立会受検(検1)", "検査"),
    "completion": ("8104", "8104", "完成(検1)", "検査"),
    "shipment": ("9000", "9000", "出荷", "出荷"),
}


# What: Human-readable sponsor rule catalog from PDF #2.
# Purpose: Keeps executable and not-yet-executable sponsor knowledge visible for review.
SPONSOR_RULES: tuple[SponsorRule, ...] = (
    SponsorRule(
        "PDF2-DATA-001",
        "data-interface",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (1, 2, 4),
        "Oracle order files, D6 schedule outputs, resource data, and work/progress data are distinct planning inputs and outputs.",
        "advisory",
        "Current code identifies required CSV files by schema and produces AIPM artifacts; full Oracle/D6 automation remains future work.",
    ),
    SponsorRule(
        "PDF2-MASTER-001",
        "master-data",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (2, 3),
        "D6 calendars, resource calendars, capacities, activity masters, resource masters, alternative resource groups, and reference patterns are relevant master data.",
        "partially implemented",
        "Current code uses resource master capacity and a simplified work calendar; resource-specific calendars and alternative groups are not yet executable.",
    ),
    SponsorRule(
        "PDF2-PATTERN-001",
        "reference-pattern",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (3,),
        "Reference patterns define standard activity order, connections, work hours, and required quantities; example sequence includes 仕様 -> 基本設計 -> 承認 -> 出図 -> 銅帯図.",
        "implemented as precedence candidates",
        "Mapped sequence edges are supplied as sponsor precedence rules independent of runtime reference schedules.",
    ),
    SponsorRule(
        "PDF2-SCHED-001",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Customer due date is prioritized; planners adjust processes and consider outsourcing to meet the customer due date.",
        "partially implemented",
        "Current solver includes due-date-oriented targets and tardiness reporting, but outsourcing optimization is not implemented.",
    ),
    SponsorRule(
        "PDF2-SCHED-002",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Panel start should be set two days after frame start.",
        "implemented as temporal constraint",
        "Mapped to frame -> panel start-start minimum lag of 2 days when both activities exist in a WBS.",
    ),
    SponsorRule(
        "PDF2-SCHED-003",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Panel finish should be set 0 to 8 hours after frame finish.",
        "implemented as temporal constraint",
        "Mapped to frame -> panel finish-finish lag between 0 and 8 hours when both activities exist in a WBS.",
    ),
    SponsorRule(
        "PDF2-SCHED-004",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Avoid excessive early scheduling.",
        "partially implemented",
        "OR-Tools minimizes deviation from target timestamps, which discourages unnecessary movement, but maximum-earliness thresholds need sponsor confirmation.",
    ),
    SponsorRule(
        "PDF2-SCHED-005",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Do not leave too large a gap between fabrication/work and painting to avoid rust.",
        "implemented as precedence candidate",
        "Mapped as frame -> painting and painting -> assembly precedence; maximum-gap thresholds remain advisory.",
    ),
    SponsorRule(
        "PDF2-SCHED-006",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Inspection timing for main switchboards and monitoring panels should be aligned as much as possible.",
        "advisory",
        "Current data lacks reliable product-family linking for this cross-order alignment rule.",
    ),
    SponsorRule(
        "PDF2-SCHED-007",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Customer witness inspection has product-type timing restrictions.",
        "advisory",
        "Current code does not yet model product-type-specific witness inspection time windows.",
    ),
    SponsorRule(
        "PDF2-SCHED-008",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Special paint colors should be grouped with same-color orders when possible.",
        "advisory",
        "Current input data does not expose a normalized paint-color grouping key.",
    ),
    SponsorRule(
        "PDF2-SCHED-009",
        "scheduling-heuristic",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (6,),
        "Remote delivery should account for transportation period.",
        "partially implemented",
        "Transport operations are represented when present, but delivery-location-specific durations are not generalized.",
    ),
    SponsorRule(
        "PDF2-OUTSOURCE-001",
        "outsourcing-decision",
        "docs/2-AIPM工程管理フロー抽出_20260430.pdf",
        (7,),
        "Outsourcing decisions depend on customer, product, dimensions, paint/material specification, ship class, capacity, supplier capability, lead time, quality, cost, and prior performance.",
        "advisory",
        "Current code preserves internal/external classification and resource assignments; supplier selection is future work.",
    ),
)


# What: Sponsor precedence candidates from PDF #2.
# Purpose: Adds domain sequence rules that are independent of reference schedule sample size.
SPONSOR_PRECEDENCE_RULES: tuple[SponsorPrecedenceRule, ...] = (
    SponsorPrecedenceRule("PDF2-PATTERN-001A", OPERATION_SIGNATURES["specification"], OPERATION_SIGNATURES["basic_design"], (3,), "仕様 precedes 基本設計."),
    SponsorPrecedenceRule("PDF2-PATTERN-001B", OPERATION_SIGNATURES["basic_design"], OPERATION_SIGNATURES["approval"], (3,), "基本設計 precedes 承認."),
    SponsorPrecedenceRule("PDF2-PATTERN-001C", OPERATION_SIGNATURES["approval"], OPERATION_SIGNATURES["drawing_issue"], (3,), "承認 precedes 出図."),
    SponsorPrecedenceRule("PDF2-PATTERN-001D", OPERATION_SIGNATURES["drawing_issue"], OPERATION_SIGNATURES["copper_bar_drawing"], (3,), "出図 precedes 銅帯図."),
    SponsorPrecedenceRule("PDF2-FLOW-001", OPERATION_SIGNATURES["frame"], OPERATION_SIGNATURES["panel"], (6,), "Panel timing is controlled relative to frame timing."),
    SponsorPrecedenceRule("PDF2-FLOW-002", OPERATION_SIGNATURES["frame"], OPERATION_SIGNATURES["painting"], (6,), "Frame work should feed painting without excessive separation."),
    SponsorPrecedenceRule("PDF2-FLOW-003", OPERATION_SIGNATURES["painting"], OPERATION_SIGNATURES["assembly_frame_mount"], (6,), "Painting should precede assembly work."),
    SponsorPrecedenceRule("PDF2-FLOW-004", OPERATION_SIGNATURES["assembly_frame_mount"], OPERATION_SIGNATURES["wiring"], (6,), "Assembly/frame mounting should precede wiring."),
    SponsorPrecedenceRule("PDF2-FLOW-005", OPERATION_SIGNATURES["wiring"], OPERATION_SIGNATURES["check_finish"], (6,), "Wiring should precede check/finish."),
    SponsorPrecedenceRule("PDF2-FLOW-006", OPERATION_SIGNATURES["check_finish"], OPERATION_SIGNATURES["inspection"], (6,), "Check/finish should precede inspection."),
    SponsorPrecedenceRule("PDF2-FLOW-007", OPERATION_SIGNATURES["inspection"], OPERATION_SIGNATURES["witness_inspection"], (6,), "Internal inspection should precede witness inspection."),
    SponsorPrecedenceRule("PDF2-FLOW-008", OPERATION_SIGNATURES["witness_inspection"], OPERATION_SIGNATURES["completion"], (6,), "Witness inspection should precede completion."),
    SponsorPrecedenceRule("PDF2-FLOW-009", OPERATION_SIGNATURES["completion"], OPERATION_SIGNATURES["shipment"], (6,), "Completion should precede shipment."),
)


# What: Sponsor temporal constraints from PDF #2.
# Purpose: Applies explicit planner lag rules where current data supports them.
SPONSOR_TEMPORAL_RULES: tuple[SponsorTemporalRule, ...] = (
    SponsorTemporalRule("PDF2-SCHED-002", OPERATION_SIGNATURES["frame"], OPERATION_SIGNATURES["panel"], "start_start", 2 * 24 * 60, None, (6,), "Panel start should be two days after frame start."),
    SponsorTemporalRule("PDF2-SCHED-003", OPERATION_SIGNATURES["frame"], OPERATION_SIGNATURES["panel"], "finish_finish", 0, 8 * 60, (6,), "Panel finish should be 0 to 8 hours after frame finish."),
)


# What: Sponsor precedence-rule provider.
# Purpose: Returns operation-signature edges for the scheduler.
def sponsor_precedence_edges() -> set[tuple[OperationSignature, OperationSignature]]:
    return {(rule.before, rule.after) for rule in SPONSOR_PRECEDENCE_RULES}


# What: Sponsor temporal-rule provider.
# Purpose: Returns concrete temporal spacing constraints for OR-Tools.
def sponsor_temporal_rules() -> tuple[SponsorTemporalRule, ...]:
    return SPONSOR_TEMPORAL_RULES


# What: Rule implementation summary.
# Purpose: Gives reports concise counts of active versus advisory sponsor knowledge.
def sponsor_rule_summary() -> dict[str, int]:
    summary = {
        "total": len(SPONSOR_RULES),
        "implemented": 0,
        "partially_implemented": 0,
        "advisory": 0,
        "precedence_candidates": len(SPONSOR_PRECEDENCE_RULES),
        "temporal_constraints": len(SPONSOR_TEMPORAL_RULES),
    }
    for rule in SPONSOR_RULES:
        status = rule.implementation_status
        if status.startswith("implemented"):
            summary["implemented"] += 1
        elif status.startswith("partially"):
            summary["partially_implemented"] += 1
        else:
            summary["advisory"] += 1
    return summary

