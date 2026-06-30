# AIPM2 Deployment Guide for semaa.site

## Purpose

Deploy AIPM2 as a separate backend service on the DigitalOcean server that
already runs LibreChat at `https://semaa.site`.

## Target Architecture

- LibreChat remains the sponsor-facing front end.
- AIPM2 runs as a separate backend service.
- LibreChat calls AIPM2 through an OpenAPI Action.
- AIPM2 returns links to schedule reports, process reports, schedules,
  findings, divergences, and work orders.
- The production scheduling path is reference-free. A reference schedule, when
  uploaded, is used only for comparison diagnostics.
- Solver relaxations must never be silent. Reports must show the requested
  strategy, actual solver mode, and any solver warnings.

## Recommended Names

- GitHub repo: `yjin1/aipm2`
- Server folder: `/opt/aipm2`
- Container/service: `aipm2-agent`
- Public route: `https://semaa.site/aipm2`
- LibreChat action: `AIPM2`

## Clone the Repository

```bash
ssh USER@semaa.site
sudo mkdir -p /opt/aipm2
sudo chown -R "$USER":"$USER" /opt/aipm2
cd /opt/aipm2
git clone https://github.com/yjin1/aipm2.git .
```

## Configure Environment

Create `/opt/aipm2/.env`:

```env
OPENAI_API_KEY=replace-with-server-side-openai-key
OPENAI_BASE_URL=https://api.openai.com/v1
AIPM_PUBLIC_BASE_URL=https://semaa.site/aipm2
LIBRECHAT_MONGO_URI=mongodb://mongodb:27017/LibreChat
LIBRECHAT_CONTAINER_UPLOADS_DIR=/app/uploads
LIBRECHAT_UPLOADS_DIR=/app/librechat_uploads
LIBRECHAT_UPLOADS_HOST_DIR=/path/to/LibreChat/uploads
```

Do not commit `.env`.

## Run With Docker Compose

Option A: add AIPM2 to the existing LibreChat Compose stack:

```yaml
services:
  aipm2-agent:
    build:
      context: /opt/aipm2
      dockerfile: Dockerfile
    container_name: aipm2-agent
    restart: unless-stopped
    env_file:
      - /opt/aipm2/.env
    volumes:
      - /opt/aipm2/outputs:/app/outputs
      - ${LIBRECHAT_UPLOADS_HOST_DIR}:/app/librechat_uploads:ro
    expose:
      - "8000"
    depends_on:
      - mongodb
```

Then:

```bash
cd /path/to/LibreChat
docker compose up -d --build aipm2-agent
```

Option B: run AIPM2 with its own compose file:

```bash
cd /opt/aipm2
docker compose --env-file .env -f docker-compose.aipm.yml up -d --build
```

## Reverse Proxy

Expose AIPM2 at:

```text
https://semaa.site/aipm2
```

Nginx example:

```nginx
location /aipm2/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Test:

```bash
curl https://semaa.site/aipm2/health
```

Expected:

```json
{"status":"ok"}
```

## LibreChat Action

Use:

```text
https://semaa.site/aipm2/openapi.json
```

If using the static schema file `aipm_openapi_librechat.json`, update the
`servers.url` from local development to:

```json
"url": "https://semaa.site/aipm2"
```

Recommended LibreChat assistant instruction:

```text
You are AIPM2, a planning, scheduling, and process-management assistant.
Use the AIPM2 action for scheduling, strategy listing, report review, work
orders, and progress scenarios. Use strategy ortools_precedence unless the user
chooses another strategy. Set use_openai=true for sponsor runs. Do not ask users
for OpenAI keys. Use uploaded files only; if files are missing, explain the
missing inputs and stop. The three core CSV files are required: product/order,
work/order activity, and resource master. The reference schedule is optional and
must be used only for comparison, never for schedule generation. actual_progress.csv
is optional and supports execution monitoring and updated work orders. Always
state the run ID, requested strategy, actual solver mode, solver warnings, model,
and report links. Never hide fallback or constraint relaxation.
```

## Current AIPM2 Behavior To Verify

- Required inputs: product/order CSV, work/order activity CSV, and resource
  master CSV.
- Optional inputs: reference middle schedule CSV and `actual_progress.csv`.
- Recommended strategy: `ortools_precedence`.
- OR-Tools objective: balanced schedule quality, prioritizing tardiness,
  maximum tardiness, makespan, and then target-date stability.
- If the strict precedence + temporal model is infeasible, AIPM2 may run a
  relaxed solver mode, but it must report this clearly in AI Diagnosis/findings.
- Schedule report includes dashboard, schedule-quality measures, reference
  comparison when available, feasibility validation, AI diagnosis, resource
  load, Gantt chart, and process flow.
- Process-management report includes execution status, management focus,
  execution exceptions, and **Updated Work Orders**. Updated work orders are
  shown only for operations touched by `actual_progress.csv`; when no progress
  is reported, that section is intentionally blank with an explanation.

## Smoke Test

In LibreChat:

```text
Check whether the AIPM2 backend is healthy.
```

```text
Show me all AIPM scheduling strategy choices.
```

Upload the three core CSV files, then ask:

```text
Run AIPM using my recent uploaded CSV files with strategy ortools_precedence and use_openai=true.
```

Confirm returned links open:

```text
https://semaa.site/aipm2/runs/{run_id}/report.html
https://semaa.site/aipm2/runs/{run_id}/process_management_report.html
https://semaa.site/aipm2/runs/{run_id}/work_orders.html
```

In the schedule report, confirm:

```text
Solver mode: ...
Solver warning: ...
```

If solver warnings appear, they should explicitly say which constraint set
failed and which relaxed mode produced the schedule.

If testing process management, upload `actual_progress.csv` and confirm the
process report shows `Updated Work Orders`. Without progress updates, the
section should be blank and explain why.

## Update Later

```bash
cd /opt/aipm2
git pull origin main
docker compose --env-file .env -f docker-compose.aipm.yml up -d --build
curl https://semaa.site/aipm2/health
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `/aipm2/health` returns 404 | Proxy prefix is not stripped. | Check Nginx `proxy_pass` trailing slash. |
| Links point to `127.0.0.1` | `AIPM_PUBLIC_BASE_URL` is wrong. | Set it to `https://semaa.site/aipm2`. |
| LibreChat action cannot connect | OpenAPI server URL is wrong. | Use `https://semaa.site/aipm2` or internal Docker URL. |
| AIPM cannot find uploads | Mongo/upload volume settings are wrong. | Check `LIBRECHAT_MONGO_URI` and upload mount. |
| No AI diagnosis | Backend lacks OpenAI key. | Set `.env` and restart. |
| Report shows solver relaxation | Strict constraints were infeasible. | Read solver warnings; revise temporal/domain rules or accept the reported relaxed mode for demo. |
| Process report has no updated work orders | No progress rows matched scheduled operations. | Upload `actual_progress.csv` using the progress template for that run. |
