from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from aipm_data import AIPMDataset, build_middle_schedule, write_middle_schedule


# What: Command-line entry point for dataset validation and baseline schedule generation.
# Purpose: Gives users and future agents a simple executable interface around aipm_data.py.
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate AIPM CSV inputs and optionally generate a middle-level schedule CSV."
    )
    parser.add_argument("--data-dir", default="data", help="Folder containing the AIPM CSV files.")
    parser.add_argument(
        "--output",
        help="Optional output CSV path for a generated middle-level schedule.",
    )
    args = parser.parse_args()

    dataset = AIPMDataset.from_data_dir(args.data_dir)
    issues = dataset.validate()
    # Keep errors machine-visible through the process exit code while still printing all findings.
    severity_counts = Counter(issue.severity for issue in issues)

    print("AIPM dataset summary")
    print(f"- product orders: {len(dataset.product_orders)}")
    print(f"- work rows: {len(dataset.work_rows)}")
    print(f"- real activities: {len(dataset.activities)}")
    print(f"- resources: {len(dataset.resources)}")
    print(f"- reference schedule rows: {len(dataset.reference_schedule)}")

    if issues:
        print("\nValidation issues")
        for issue in issues:
            print(f"- {issue.severity}: {issue.message}")
    else:
        print("\nValidation issues: none")

    if args.output:
        # Generated output is a baseline schedule for later agent reasoning and comparison.
        rows = build_middle_schedule(dataset)
        output_path = Path(args.output)
        write_middle_schedule(rows, output_path)
        print(f"\nGenerated schedule: {output_path}")

    return 1 if severity_counts["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
