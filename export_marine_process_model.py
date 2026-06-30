from __future__ import annotations

import json
from pathlib import Path

from marine_design_process_rules import (
    DOCUMENTED_PROCESS_EDGES,
    DOCUMENTED_PROCESS_NODES,
    documented_precedence_edges,
)


# What: Marine design process model exporter.
# Purpose: Writes the flowchart-derived workflow model to JSON for review and editing.
def main() -> int:
    output = Path("outputs/marine_design_process_model.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    model = {
        "source_document": "docs/3-Marine Order Design Management Regulations.pdf",
        "source_pages_used": [6, 7, 8, 9],
        "nodes": DOCUMENTED_PROCESS_NODES,
        "edges": [
            {"from": before, "to": after, "condition": condition}
            for before, after, condition in DOCUMENTED_PROCESS_EDGES
        ],
        "mapped_precedence_edges": [
            {
                "before": list(before),
                "after": list(after),
            }
            for before, after in sorted(documented_precedence_edges())
        ],
    }
    output.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
