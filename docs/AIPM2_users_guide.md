# AIPM2 User Guide

## Purpose

AIPM2 is an AI-assisted planning, scheduling, and process-management agent for product development process management. It is used through LibreChat and calls an AIPM2 backend service to create schedules, diagnose schedule quality, monitor execution progress, and produce updated work orders.

The current version is intended for sponsor testing and research validation. It is not yet a fully validated production scheduler.

## What AIPM2 Can Do

- Create a middle-level schedule from order, activity, and resource CSV files.
- Use encoded sponsor/domain rules from AIPM knowledge documents.
- Run OR-Tools scheduling strategies with resource and precedence constraints.
- Compare the generated schedule with a reference schedule when one is provided.
- Produce a schedule report with quality, feasibility, resource, Gantt, and process-flow views.
- Produce a process-management report from the current schedule and optional progress updates.
- Generate updated work orders when progress data is reported.
- Use backend GPT diagnosis when `use_openai=true` and the server has an OpenAI key.


### How Many Orders Can AIPM2 Process?

The current sponsor demo data contains three orders, but AIPM2 is not hard-coded to three orders. It reads all valid orders and activities present in the uploaded CSV files.

Practical guidance for sponsor testing:

- Current validated demo size: 3 orders and 86 generated schedule rows.
- Small pilot tests: tens of orders should be reasonable if the CSV format is consistent and the activity count remains moderate.
- Larger tests: hundreds of orders may require solver-time tuning, stronger batching rules, and server resource checks.
- Main scaling factor: number of activity rows, resource conflicts, precedence rules, and temporal constraints, not simply the number of orders.
- OR-Tools runs can become slower when many activities share constrained resources or when strict constraints are close to infeasible.

For sponsor review, the honest statement is:

```text
AIPM2 is designed to process more than the current three-order demo set, but the present version has only been validated on the available sponsor sample. The next validation step is to test progressively larger batches and record runtime, solver mode, feasibility warnings, and schedule quality.
```

## Required And Optional Files

### Required Core CSV Files

AIPM2 requires three core input files:

1. Product/order CSV
2. Work/order activity CSV
3. Resource master CSV

Upload order does not matter. AIPM2 identifies files by their columns/schema.

### Optional Files

Reference middle schedule CSV:

- Used only for comparison diagnostics.
- Not used to generate the production schedule.
- If omitted, the schedule still runs and reference-comparison sections show no reference provided.

`actual_progress.csv`:

- Used for process-management and execution monitoring.
- Can be uploaded with the initial input files or later as a progress scenario.
- Drives execution status, exceptions, and Updated Work Orders.

## Scheduling Strategies

### `ortools_precedence`

Recommended default for sponsor testing.

Uses OR-Tools with resource capacity and extracted production/domain precedence rules. The current objective is balanced:

- minimize order tardiness,
- minimize maximum tardiness,
- reduce makespan,
- preserve target-date/phase stability enough to avoid unrealistic compression.

If strict precedence + temporal constraints are infeasible, AIPM2 may run a relaxed solver mode. This must be reported clearly in the schedule report under `Solver mode` and `Solver warning`.

### `execution_reschedule`

Used when `actual_progress.csv` is supplied and the user wants a progress-aware scenario.

Preserves completed/in-progress work where possible and uses progress status to update execution monitoring and work-order status.

### `ortools_cp`

Capacity-focused OR-Tools strategy without the full production precedence rule set.

Useful for comparing capacity-only behavior against `ortools_precedence`.

### `baseline`

Simple deterministic baseline.

Useful for showing how much the richer strategies improve over a simple schedule construction.

### `reference_learning`

Research/benchmark strategy that learns timing offsets from the reference schedule.

Not recommended as the production scheduling strategy because live schedule generation should not depend on the reference schedule.

### `field_repair`

Research/benchmark strategy for repairing output status/flag fields.

Useful for analysis, not the preferred production schedule generator.

### `reference_replay`

Replays the supplied reference schedule for known rows.

This is an upper-bound benchmark only. It is not a general scheduler and should not be used as the production scheduling method.

## Reports And Artifacts

Each successful run returns artifact links.

### Schedule Report

Typical link:

```text
/runs/{run_id}/report.html
```

Main contents:

- Dashboard Summary
- Schedule Profile
- Schedule Quality
- Reference Comparison, if a reference schedule was provided
- AI Diagnosis
- Feasibility Validation
- Resource Load
- Gantt Chart
- Order Timelines
- Field Rule Diagnostics
- Timing Divergence Diagnostics, if a reference schedule was provided
- Process Flow

Important items to check:

- `Solver mode`
- `Solver warning`
- late orders
- total tardiness
- max tardiness
- makespan
- overload flags
- domain rule violations
- capacity conflicts

### Process Management Report

Typical link:

```text
/runs/{run_id}/process_management_report.html
```

Main contents:

- Execution Status
- Management Focus
- Immediate Actions
- Progress Coverage
- Execution Exceptions
- Updated Work Orders

The process-management report is about execution monitoring, not schedule-quality scoring.

### Updated Work Orders

Updated Work Orders are shown only when operations have actual progress updates.

The section includes work orders touched by statuses such as:

- completed
- in progress
- blocked
- delayed

If no progress rows are reported, this section is intentionally blank and explains why.

### Work Orders HTML / CSV

Typical links:

```text
/runs/{run_id}/work_orders.html
/runs/{run_id}/work_orders.csv
```

These are generated work-order artifacts. They can be used for reviewing dispatch instructions, but they should still be checked by a human before operational use.

### Progress Template

Typical link:

```text
/runs/{run_id}/progress-template.csv
```

Use this template so workgroups report progress with the correct schedule keys.

### Findings

Typical link:

```text
/runs/{run_id}/findings
```

Contains the text findings used in the report, including solver mode, solver warnings, deterministic metrics, and GPT diagnosis if available.

### Divergences CSV

Typical link:

```text
/runs/{run_id}/divergences.csv
```

Available when a reference schedule is provided. It lists generated-vs-reference timing differences.

## Understanding Solver Warnings

AIPM2 should never silently hide solver fallback or constraint relaxation.

If the strict model cannot be solved, the report should say what happened. Example:

```text
Solver mode: OR-Tools precedence-only relaxed mode.
Solver warning: OR-Tools precedence + temporal constraints failed...
Solver warning: AIPM relaxed the temporal lag constraints and reran OR-Tools with production precedence only.
```

This means the schedule was still generated, but with a relaxed constraint set. The warning should be discussed with the sponsor because it points to rules that may need adjustment.

## Known Limitations And Potential Issues

- The scheduler is research/demo grade and still needs sponsor validation.
- Some temporal rules may be too strict or incomplete, causing solver relaxation.
- Current resource calendars are simplified.
- Alternative resources and outsourcing decisions are not fully optimized.
- Product-type-specific inspection windows are not fully modeled.
- Paint color grouping and transportation/location-specific rules are not fully modeled.
- Reference comparison measures are secondary; they do not alone prove schedule quality.
- Without `actual_progress.csv`, process-management status is limited because no execution updates are available.
- Updated Work Orders will be blank when no progress rows match scheduled operations.
- Backend GPT diagnosis requires the server-side OpenAI key and network/certificate configuration.

## Good Demo Workflow

1. Upload the three required CSV files.
2. Optionally upload the reference schedule for comparison.
3. Ask AIPM2 to show available strategies.
4. Run `ortools_precedence` with `use_openai=true`.
5. Open the schedule report.
6. Check schedule quality, feasibility validation, solver mode, and solver warnings.
7. Open the process-management report.
8. If testing execution, upload `actual_progress.csv`.
9. Create a progress scenario or rerun with the progress file.
10. Review Updated Work Orders and management actions.

## Common Prompts

### Basic Health Check

```text
Check whether the AIPM2 backend is healthy.
```

### Show Strategies

```text
Show me all AIPM scheduling strategy choices and explain when to use each one.
```

### Recommended Schedule Run

```text
Run AIPM using my recent uploaded CSV files with strategy ortools_precedence and use_openai=true.
```

### Traceable Sponsor Run

```text
Run AIPM using my recent uploaded CSV files with strategy ortools_precedence and use_openai=true. Before summarizing, state the run ID, requested strategy, actual solver mode, solver warnings, model, and files used.
```

### No Local Fallback

```text
Use only my uploaded files. If the required files are missing or invalid, stop and explain exactly what is missing. Do not fall back to local sample files.
```

### Reference Independence

```text
Use the reference schedule only for comparison. Do not use the reference schedule to generate the production schedule.
```

### Explain Schedule Quality

```text
Explain the schedule quality measures in the latest report. Separate true schedule-quality measures from reference-comparison measures.
```

### Explain Solver Warnings

```text
Explain the solver mode and solver warnings in the latest AIPM2 report. What constraints were relaxed, and what does that mean for sponsor review?
```

### Process Management Review

```text
Open the process management report from the latest AIPM2 run and summarize execution status, management focus, execution exceptions, and updated work orders.
```

### Progress Template

```text
Give me the progress-template CSV link for the latest AIPM2 run.
```

### Progress Scenario

```text
I uploaded actual_progress.csv for run ID [paste run ID]. Create a progress scenario and show the new process management report.
```

### Updated Work Orders

```text
Show the updated work orders from the latest process-management report. If the section is empty, explain why.
```

### Sponsor Summary

```text
Create a sponsor-ready summary of the latest AIPM2 run: what files were used, what strategy ran, what solver mode was used, what warnings appeared, what the schedule quality says, and what process-management actions are recommended.
```

## Suggested Interpretation For Sponsors

AIPM2 should be described as:

```text
A reference-free planning and scheduling prototype that uses extracted sponsor process knowledge and OR-Tools optimization to generate explainable schedules, diagnose feasibility, monitor progress, and produce updated work orders. It is ready for sponsor testing and rule validation, but not yet a fully validated production scheduling system.
```
