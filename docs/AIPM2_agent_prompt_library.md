# AIPM2 Agent Prompt Library

Copy-paste prompts for sponsor testing through LibreChat with the AIPM2 backend.

## How To Use

Open LibreChat, select the AIPM/AIPM2 assistant or action, upload the required input files, then paste one of the prompts below.

Current AIPM2 input rules:

- Three core CSV files are required: product/order, work/order activity, and resource master.
- The reference middle schedule is optional and must be used only for comparison, not for production scheduling.
- `actual_progress.csv` is optional and can be uploaded with the initial files or later as a progress scenario.
- File upload order does not matter; AIPM2 identifies inputs by schema and columns.
- If required files are missing or invalid, AIPM2 should stop and explain the issue rather than falling back to local sample files.

## Quick Start

| Use case | Prompt | Expected result |
|---|---|---|
| Check backend health | Check whether the AIPM2 backend is healthy before running the demo. | Confirms the backend is reachable. |
| Show strategies | Show me all AIPM scheduling strategy choices and explain when to use each one. | Presents available strategy options. |
| Default sponsor run | Run AIPM using my recent uploaded CSV files with strategy `ortools_precedence` and `use_openai=true`. | Runs the recommended production scheduling strategy. |
| Traceable run | Run AIPM using my recent uploaded CSV files. Before summarizing results, state the run ID, strategy, model, whether `use_openai` was true, and which files were used. | Produces an auditable sponsor-demo response. |

## File Upload Prompts

| Use case | Prompt | Expected result |
|---|---|---|
| Use recent uploads | Use the latest valid CSV files I uploaded in this conversation and run `ortools_precedence`. | Uses recent LibreChat uploads. |
| Limit to named files | Run AIPM using only these uploaded filenames: `[paste filenames]`. Use `ortools_precedence`. | Avoids confusion when duplicate uploads exist. |
| Missing-file check | Check whether the required AIPM2 CSV inputs are present. If anything is missing, tell me exactly what is missing and do not run. | Validates inputs before scheduling. |
| Ignore output files | Use only input CSV files for AIPM2 scheduling. Ignore uploaded report, findings, generated schedule, timing, divergence, or work-order output files. | Prevents generated artifacts from being reused as inputs. |
| Reference independence | Do not use the reference schedule to generate the production schedule. Use it only for comparison if provided. | Protects the production scheduler design. |

## Strategy Selection

| Strategy | Plain-language purpose | Suggested prompt |
|---|---|---|
| `ortools_precedence` | Recommended default. Uses resource capacity plus documented and extracted production rules. It does not use the reference schedule for live generation. | Run AIPM with strategy `ortools_precedence` and explain schedule quality, feasibility, and main risks. |
| `execution_reschedule` | Progress-aware rescheduling after workgroups submit `actual_progress.csv`. Preserves completed/in-progress work and adjusts unfinished work when needed. | Run AIPM with strategy `execution_reschedule` using my latest `actual_progress.csv` and explain what changed. |
| `ortools_cp` | Capacity-focused OR-Tools schedule without the full precedence rule set. | Run AIPM with strategy `ortools_cp` and compare it with `ortools_precedence`. |
| `baseline` | Simple deterministic schedule. Useful as a low-complexity comparison point. | Run AIPM with strategy `baseline` and compare it to the recommended strategy. |
| `reference_learning` | Research/benchmark strategy that uses reference-derived timing patterns. Not the preferred production strategy. | Run AIPM with strategy `reference_learning` and explain why it is for analysis rather than normal production scheduling. |
| `field_repair` | Research/benchmark strategy for repairing output fields using learned/reference-derived patterns. | Run AIPM with strategy `field_repair` and report field mismatch improvements. |
| `reference_replay` | Replays the supplied reference schedule for known rows. Useful only as an upper-bound benchmark. | Run AIPM with strategy `reference_replay` and explain why this is a benchmark, not a deployable scheduler. |

## Schedule Report Review

| Use case | Prompt | Expected result |
|---|---|---|
| Summarize schedule report | Open the AIPM2 schedule report from the latest run and summarize the dashboard, true schedule quality, feasibility validation, resource load, Gantt chart, process flow, AI diagnosis, and reference comparison if available. | Summarizes the main report. |
| Explain quality | Explain the schedule quality measures in the latest report. Separate true schedule-quality measures from reference-comparison measures. | Avoids treating reference matching as the primary quality score. |
| Explain timing gaps | Explain why the generated schedule differs from the reference schedule, focusing on load state, relief flags, dependency logic, and calendar/capacity assumptions. | Focuses on comparison diagnostics. |
| Review divergences | Fetch the divergence CSV from the latest AIPM2 run and list the top 10 rows by absolute timing error. | Uses the divergence artifact when a reference schedule exists. |
| Executive summary | Write a sponsor-ready summary of the latest AIPM2 run in five bullets: method, output, quality, limitations, and next step. | Creates a concise sponsor communication. |

## Process Management Prompts

| Use case | Prompt | Expected result |
|---|---|---|
| Open process panel | Open the process management report from the latest AIPM2 run and summarize execution status, exceptions, and work-order examples. | Uses the process-management report. |
| Generate work orders | From the latest AIPM2 run, generate work orders and show the critical or high-priority examples first. | Returns dispatch-ready examples. |
| Group by workgroup | Group the latest generated work orders by workgroup and list what each group should do next. | Produces workgroup-specific dispatch guidance. |
| Manager action list | Based on the latest process management report, list the manager actions needed today. | Turns execution findings into action items. |
| Work-order explanation | Explain one generated work order card field by field: ID, WBS, operation, resource, planned window, status, priority, risk, and instruction. | Helps sponsors understand the dispatch format. |

## Progress Scenario Prompts

| Use case | Prompt | Expected result |
|---|---|---|
| Get progress template | For the latest AIPM2 run, give me the progress-template CSV link so workgroups can report status. | Returns `/progress-template.csv`. |
| Upload progress with initial inputs | Run AIPM using my uploaded order, resource, and `actual_progress.csv` files. Use `ortools_precedence` and `use_openai=true`. | Creates schedule, process panel, work orders, and execution monitoring in one run. |
| Upload progress after a run | I uploaded `actual_progress.csv` for run ID `[paste run ID]`. Create a progress scenario and show the new process management report. | Creates a progress-aware scenario from the previous run. |
| Validate progress file | Check whether my `actual_progress.csv` has the required columns before running a progress scenario. | Reports missing or invalid progress columns. |
| Explain progress impact | Compare the process panel before and after my progress update. What changed and what work is now at risk? | Highlights delayed, blocked, completed, and shifted work. |

## Troubleshooting Prompts

| Problem | Prompt | Expected result |
|---|---|---|
| Missing files | The AIPM2 run failed because of file input problems. Diagnose which CSV files are missing or invalid and tell me how to fix the upload. | Focuses on input validation. |
| HTTP 500 | The AIPM2 backend returned HTTP 500. Check whether this is an OpenAI call problem, file parsing problem, or solver problem, and suggest the next debugging step. | Separates failure categories. |
| No AI diagnosis | The report says no LLM client is configured. Explain what that means and how to confirm whether the AIPM2 backend has `OPENAI_API_KEY`. | Explains server-side AI configuration. |
| Duplicate uploads | I see duplicate filenames in LibreChat uploads. Use the most recent valid input CSVs only and ignore generated output files. | Guides recent-file selection. |
| Report downloads | The AIPM2 report link downloads instead of opening in the browser. Use the `.html` report endpoint and explain which link should be opened. | Points users to the inline HTML endpoint. |

## Sponsor Demo Script

1. Open LibreChat on `https://semaa.site`.
2. Select the AIPM2 assistant/action.
3. Upload the three core input CSV files.
4. Optionally upload the reference middle schedule CSV for comparison.
5. Ask: `Show me all AIPM scheduling strategy choices and recommend one for sponsor testing.`
6. Ask: `Run AIPM using my recent uploaded CSV files with strategy ortools_precedence and use_openai=true.`
7. Open the schedule report and review dashboard, feasibility validation, resource load, Gantt chart, process flow, AI diagnosis, and reference comparison if available.
8. Open the process management report and review execution status plus generated work-order examples.
9. Ask: `Give me the progress-template CSV link for this run.`
10. Upload a demo `actual_progress.csv`.
11. Ask: `Create a progress scenario for this run and summarize what changed.`
12. Ask: `Create a sponsor-ready explanation of how AIPM2 supports planning, scheduling, work-order dispatch, progress monitoring, and controlled rescheduling.`

## Guardrails

| Guardrail | Prompt | Purpose |
|---|---|---|
| No hidden local fallback | Use only my uploaded input/progress files. If they are missing or invalid, stop and explain the issue. | Prevents accidental demo runs from old local files. |
| Reference independence | Do not use the reference schedule to generate the production schedule. Use it only for comparison if provided. | Keeps scheduling independent from reference data. |
| Artifact separation | Keep schedule quality in the schedule report and execution/work-order status in the process management report. | Keeps reports conceptually clean. |
| Traceability | State the run ID, strategy, model, whether `use_openai` was true, and which files were used before summarizing results. | Makes sponsor demos auditable. |
| Dispatch caution | Before saying work orders are ready to send, identify any feasibility, progress, or data-quality issues that need human review. | Avoids overclaiming operational readiness. |

## AIPM2 Artifacts

| Artifact | Typical endpoint |
|---|---|
| Schedule report | `/runs/{run_id}/report.html` or `/runs/{run_id}/agent_schedule_report.html` |
| Process management report | `/runs/{run_id}/process_management_report.html` |
| Generated schedule CSV | `/runs/{run_id}/schedule.csv` |
| AI/deterministic findings | `/runs/{run_id}/findings` |
| Divergence CSV, when reference exists | `/runs/{run_id}/divergences.csv` |
| Work-order HTML | `/runs/{run_id}/work_orders.html` |
| Work-order CSV | `/runs/{run_id}/work_orders.csv` |
| Progress template | `/runs/{run_id}/progress-template.csv` |
| Progress scenario upload | `/runs/{run_id}/progress` |

