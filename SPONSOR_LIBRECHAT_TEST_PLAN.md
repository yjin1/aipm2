# AIPM Sponsor LibreChat Test Plan

## Goal

Sponsors should use one interface only: the AIPM agent inside LibreChat.

## Sponsor Workflow

1. Open the AIPM agent in LibreChat.
2. Upload the four AIPM input CSV files in the chatbox. If LibreChat asks `Text` or `Cancel`, choose `Text` for this CSV-only test.
3. Ask: `Run the AIPM planning and scheduling agent with ortools_precedence.`
4. The LibreChat action calls AIPM with the visible filenames, or with no filenames if they are not exposed.
5. AIPM returns links to:
   - HTML schedule report
   - generated middle schedule CSV
   - findings text
   - timing divergences CSV

## Deployment Requirements

- LibreChat and AIPM should run in the same Docker Compose stack or same Docker network.
- AIPM must be able to reach LibreChat MongoDB:
  - `LIBRECHAT_MONGO_URI=mongodb://mongodb:27017/LibreChat`
- AIPM must have read-only access to LibreChat's upload folder:
  - LibreChat records paths under `/app/uploads`
  - AIPM sees the same files under `/app/librechat_uploads`
- The AIPM action schema should use:
  - `POST /runs/librechat-recent`
  - operation ID `run_aipm_with_recent_librechat_uploads`

## LibreChat Agent Instructions

Use these instructions for the AIPM LibreChat agent:

```text
You are the AIPM planning and scheduling assistant.

When the user uploads AIPM input files and asks you to run the planner, call the AIPM action `run_aipm_with_recent_librechat_uploads`.

If the user asks what strategies are available, call `list_aipm_strategy_choices` and show the choices before running.
If the user has not selected a strategy, briefly show the strategy choices and recommend `ortools_precedence`.

Pass the visible uploaded filenames in `filenames` if you can see them.
If you cannot see filenames, omit `filenames` and let AIPM use the latest four CSV uploads.
Do not ask the user for LibreChat file IDs.
Do not paste CSV contents into the action.
Do not use AIPM local data-folder files unless the user explicitly asks for a local-file debug run.

Use strategy `ortools_precedence` by default.
Set use_openai to true for sponsor runs. The AIPM backend must be started with OPENAI_API_KEY so the AI diagnosis layer runs.

After the action returns, summarize the findings and show the report, schedule, findings, and divergences links.
```

## Pre-Test Checklist

- `GET /health` returns `{"status":"ok"}`.
- LibreChat action schema is created from `aipm_openapi_librechat.json`.
- Old duplicate AIPM actions are deleted from the LibreChat agent.
- AIPM can read LibreChat file metadata from MongoDB.
- AIPM can read uploaded files from the shared upload volume.
- A test run with four CSV uploads returns an HTML report link.

## Known Failure Mode

For CSV files, AIPM can read either the original uploaded file from LibreChat storage or the complete text stored in LibreChat's file record. For Excel and other binary formats, the workflow must preserve original uploaded bytes or use a LibreChat-side forwarding bridge.
