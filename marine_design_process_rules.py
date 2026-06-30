from __future__ import annotations


# What: Documented marine-design process rules extracted from the regulation flowchart.
# Purpose: Supplies explicit workflow knowledge that complements schedule-derived inference.

# What: Known operation signatures in the current AIPM activity data.
# Purpose: Provides stable identifiers for mapping document flow steps to schedule activities.
OPERATION_SIGNATURES = {
    "basic_design": ("1002", "1002", "基本設計(海配)", "設計"),
    "specification": ("1091", "1091", "仕様", "設計"),
    "approval": ("1092", "1092", "承認", "設計"),
    "drawing_issue": ("1093", "1093", "出図", "生設"),
    "software": ("2001", "2001", "ｿﾌﾄ作成(海配)", "ｿﾌﾄ"),
    "sheet_metal_drawing": ("3001", "3001", "板金加工図", "生設"),
    "internal_assembly_drawing": ("3002", "3002", "内部組立図", "生設"),
    "copper_bar_drawing": ("3003", "3003", "銅帯図", "生設"),
    "parts": ("9900", "9900", "部品", "部品"),
}

# What: Flowchart-derived conceptual process nodes.
# Purpose: Preserves the source workflow even where not every step maps to a current CSV operation.
DOCUMENTED_PROCESS_NODES = [
    {
        "id": "quote_request",
        "label": "引合依頼",
        "source_pages": [6],
        "mapped_operation": None,
        "purpose": "Start of hard-design business flow from estimate request.",
    },
    {
        "id": "estimate_spec_review",
        "label": "見積仕様内容の検討",
        "source_pages": [6],
        "mapped_operation": None,
        "purpose": "Check whether delivery, technical requirements, and cost assumptions are feasible.",
    },
    {
        "id": "contract",
        "label": "契約の成立",
        "source_pages": [6],
        "mapped_operation": None,
        "purpose": "Contract agreement before formal order/design execution.",
    },
    {
        "id": "work_order_received",
        "label": "工事命令書の受理",
        "source_pages": [6],
        "mapped_operation": None,
        "purpose": "Formal receipt of work order.",
    },
    {
        "id": "customer_spec_received",
        "label": "客先仕様書入手",
        "source_pages": [6],
        "mapped_operation": "specification",
        "purpose": "Input customer/order specifications into design planning.",
    },
    {
        "id": "order_spec_confirmation",
        "label": "注文仕様書内容の確認",
        "source_pages": [6],
        "mapped_operation": "specification",
        "purpose": "Confirm order specification content; handle changes before design review.",
    },
    {
        "id": "design_review",
        "label": "設計審査（デザインレビュー）",
        "source_pages": [6],
        "mapped_operation": "basic_design",
        "purpose": "Review product requirements and unresolved order/specification requirements.",
    },
    {
        "id": "assignee_assignment",
        "label": "担当者割当",
        "source_pages": [7],
        "mapped_operation": None,
        "purpose": "Assign responsible design staff.",
    },
    {
        "id": "design_instruction",
        "label": "設計指示書作成・設計担当者へ指示",
        "source_pages": [7],
        "mapped_operation": "basic_design",
        "purpose": "Clarify design inputs and record them in the design plan.",
    },
    {
        "id": "drawing_need_decision",
        "label": "協議図・打合せ図・参考図等の出図必要か",
        "source_pages": [7],
        "mapped_operation": "drawing_issue",
        "purpose": "Decide whether discussion/reference/external drawings are required.",
    },
    {
        "id": "drawing_creation",
        "label": "協議図、打合せ図、参考図、外形納入品図の作成",
        "source_pages": [7],
        "mapped_operation": "drawing_issue",
        "purpose": "Create drawings for review and issue control.",
    },
    {
        "id": "drawing_check_approval",
        "label": "照査（検図）・承認",
        "source_pages": [7, 8],
        "mapped_operation": "approval",
        "purpose": "Check and approve drawings before issue or revision.",
    },
    {
        "id": "issue_management",
        "label": "出図管理表を作成・図書を作成し出図する",
        "source_pages": [7, 8],
        "mapped_operation": "drawing_issue",
        "purpose": "Create issue-management table and issue documents/drawings.",
    },
    {
        "id": "customer_approval",
        "label": "客先より承認を得る",
        "source_pages": [7, 8],
        "mapped_operation": "approval",
        "purpose": "Obtain customer approval for issued drawings.",
    },
    {
        "id": "delivery_drawing",
        "label": "納入品図作成",
        "source_pages": [7, 8],
        "mapped_operation": "drawing_issue",
        "purpose": "Create delivery drawings after customer/required approvals.",
    },
    {
        "id": "design_verification",
        "label": "設計検証・チェックリストによるチェック",
        "source_pages": [7],
        "mapped_operation": "approval",
        "purpose": "Verify that design inputs and checklist requirements are satisfied.",
    },
    {
        "id": "revision_decision",
        "label": "納入品図に対して変更が必要か",
        "source_pages": [8],
        "mapped_operation": None,
        "purpose": "Decision gate for revised drawings.",
    },
    {
        "id": "revision_issue",
        "label": "改正図を作成・承認・出図",
        "source_pages": [8],
        "mapped_operation": "drawing_issue",
        "purpose": "Create, approve, and issue revised drawings when needed.",
    },
    {
        "id": "parts_arrangement",
        "label": "部品先行手配・購入依頼表作成・データ入力",
        "source_pages": [9],
        "mapped_operation": "parts",
        "purpose": "Arrange parts and enter procurement/arrangement data.",
    },
]

# What: Flowchart-derived conceptual edges.
# Purpose: Captures documented predecessor/successor relationships from pages 6-9.
DOCUMENTED_PROCESS_EDGES = [
    ("quote_request", "estimate_spec_review", "normal"),
    ("estimate_spec_review", "contract", "normal"),
    ("contract", "work_order_received", "normal"),
    ("work_order_received", "customer_spec_received", "normal"),
    ("customer_spec_received", "order_spec_confirmation", "normal"),
    ("order_spec_confirmation", "design_review", "if no estimate-spec change or after change communication"),
    ("design_review", "assignee_assignment", "normal"),
    ("assignee_assignment", "design_instruction", "normal"),
    ("design_instruction", "drawing_need_decision", "normal"),
    ("drawing_need_decision", "drawing_creation", "if drawings required"),
    ("drawing_creation", "drawing_check_approval", "normal"),
    ("drawing_check_approval", "issue_management", "normal"),
    ("issue_management", "customer_approval", "normal"),
    ("customer_approval", "delivery_drawing", "normal"),
    ("delivery_drawing", "design_verification", "normal"),
    ("delivery_drawing", "revision_decision", "normal"),
    ("revision_decision", "revision_issue", "if revision needed"),
    ("design_review", "parts_arrangement", "parts can be arranged after design review / drawing branch"),
    ("drawing_check_approval", "parts_arrangement", "parts arrangement can follow approved drawing branch"),
]


# What: Documented precedence edges mapped to current schedule operation signatures.
# Purpose: Gives OR-Tools explicit design-flow precedence constraints where mapping is reliable.
def documented_precedence_edges() -> set[
    tuple[tuple[str, str, str, str], tuple[str, str, str, str]]
]:
    mapped_edges = set()
    node_by_id = {node["id"]: node for node in DOCUMENTED_PROCESS_NODES}
    for before_node_id, after_node_id, _condition in DOCUMENTED_PROCESS_EDGES:
        before_operation = node_by_id[before_node_id]["mapped_operation"]
        after_operation = node_by_id[after_node_id]["mapped_operation"]
        if not before_operation or not after_operation or before_operation == after_operation:
            continue
        mapped_edges.add(
            (
                OPERATION_SIGNATURES[before_operation],
                OPERATION_SIGNATURES[after_operation],
            )
        )
    return mapped_edges
