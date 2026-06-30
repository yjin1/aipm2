# AIPM2 Sponsor Demo Script

## Purpose

This script demonstrates AIPM2 on `https://semaa.site`, with LibreChat as the
sponsor-facing front end and AIPM2 as the backend planning, scheduling, and
process-management service.

## Demo Process

1. Open `https://semaa.site`.
2. Log in and select the AIPM2 assistant/action.
3. Ask AIPM2 to check backend health.
4. Ask AIPM2 to list available scheduling strategies.
5. Upload the three required CSV files:
   - product/order CSV
   - work/order activity CSV
   - resource master CSV
6. Optionally upload the reference middle schedule CSV for comparison only.
7. Run `ortools_precedence` with `use_openai=true`.
8. Open the main schedule report.
9. Review dashboard, schedule quality, feasibility validation, AI diagnosis,
   resource load, Gantt chart, and process flow.
10. Open the process management report.
11. Review execution status and generated work-order examples.
12. Open or download work orders as HTML/CSV.
13. Generate/download the progress template.
14. Upload a demo `actual_progress.csv`.
15. Create a progress scenario using `execution_reschedule`.
16. Review what changed in execution status, work orders, and risk.
17. Close with sponsor-ready summary of capabilities, limitations, and next
   data/rule needs.

## Key Prompts

```text
Check whether the AIPM2 backend is healthy before running the demo.
```

```text
Show me all AIPM scheduling strategy choices and explain when to use each one.
```

```text
Run AIPM using my recent uploaded CSV files with strategy ortools_precedence and use_openai=true.
Before summarizing results, state the run ID, strategy, model, whether use_openai was true, and which files were used.
```

```text
Open the AIPM report from the latest run and summarize the dashboard, schedule quality, feasibility validation, resource load, Gantt chart, process flow, and AI diagnosis for a sponsor audience.
```

```text
Open the process management report from the latest AIPM run and summarize execution status, exceptions, and work-order examples.
```

```text
For the latest AIPM run, give me the progress-template CSV link so workgroups can report status.
```

```text
I uploaded actual_progress.csv for run ID [paste run ID]. Create a progress scenario and show the new process management report.
```

## Guardrails to Demonstrate

- Use uploaded files only; do not fall back to local sample data.
- Use the reference schedule only for comparison, not production scheduling.
- State the run ID, strategy, model, `use_openai` setting, and files used.
- Do not claim work orders are ready for real dispatch without human review.
- Separate schedule quality from reference matching.

## Expected Artifact Links

```text
https://semaa.site/aipm2/runs/{run_id}/report.html
https://semaa.site/aipm2/runs/{run_id}/process_management_report.html
https://semaa.site/aipm2/runs/{run_id}/schedule.csv
https://semaa.site/aipm2/runs/{run_id}/findings
https://semaa.site/aipm2/runs/{run_id}/divergences.csv
https://semaa.site/aipm2/runs/{run_id}/work_orders.html
https://semaa.site/aipm2/runs/{run_id}/work_orders.csv
https://semaa.site/aipm2/runs/{run_id}/progress-template.csv
```

## Closing Message

AIPM2 currently demonstrates a closed-loop planning process: it reads sponsor
CSV inputs, generates a middle-level schedule, validates and explains that
schedule, produces work-order examples, accepts progress updates, and creates
execution scenarios. The next improvements are richer calendars, more sponsor
rules, stronger schedule optimization, better LibreChat file storage integration,
Excel support, and validation against more historical cases.

