# AIPM Agent Deployment

This project can run locally on a MacBook and can also be deployed as a Dockerized FastAPI service for LibreChat or a standalone web client.

## Local API Smoke Test

```bash
python -m uvicorn aipm_api:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
```

For browser-based CSV upload:

```text
http://127.0.0.1:8000/upload
```

Run the built-in sample data:

```bash
curl -X POST "http://127.0.0.1:8000/runs/sample?strategy=ortools_precedence&use_openai=false"
```

## Docker Run

```bash
docker compose -f docker-compose.aipm.yml up -d --build
```

The API will be available at:

```text
http://localhost:8000
```

## DigitalOcean + LibreChat Deployment

Recommended deployment on `semaa.site`:

1. Copy this project folder to the DigitalOcean server.
2. Put it beside the existing LibreChat Docker Compose project, or add the `aipm-agent` service to the existing compose stack.
3. Set `OPENAI_API_KEY` in the server `.env` file or DigitalOcean secret mechanism. Use `.env.aipm.example` as the template.
4. Do not ask sponsors to paste API keys in the browser for production use.
5. Keep the AIPM API private on the Docker network if LibreChat is the only caller.
6. Mount LibreChat's `uploads` folder read-only into the AIPM container and point AIPM to the LibreChat MongoDB service.
7. Register the sponsor-facing action schema from `aipm_openapi_librechat.json` in LibreChat. For a same-compose server deployment, change the schema server URL from `http://host.docker.internal:8000` to `http://aipm-agent:8000`.

This conversion does not change local development. You can keep editing and running the MacBook files directly; the Docker/API wrapper simply gives the same agent a stable HTTP interface for sponsors.

### One-Interface Sponsor Workflow

The sponsor workflow should stay inside LibreChat:

1. The sponsor opens the AIPM LibreChat agent.
2. The sponsor uploads the four planning CSV files in the chatbox. If LibreChat offers only `Text` or `Cancel`, the sponsor chooses `Text` for CSV files.
3. The agent calls `POST /runs/librechat-recent` with visible filenames if available. If filenames are not exposed, AIPM uses the latest four recent CSV uploads.
4. AIPM reads the LibreChat file metadata from MongoDB, copies the uploaded files from the shared upload volume, runs the selected scheduling strategy, and returns report links.
5. The sponsor opens the generated HTML report, schedule CSV, findings, or divergence CSV from the returned links.

This is the preferred path for next week's sponsor test. It avoids forcing users into a second AIPM upload page and avoids sending large CSV contents through the LLM context window. For CSV files, AIPM can read the complete text stored in LibreChat's file record by `file_id`; for Excel and other binary files, we will need preserved upload bytes or a LibreChat-side file forwarding bridge.

### LibreChat Compose Service

When AIPM is added to the same Docker Compose project as LibreChat, use this service shape:

```yaml
services:
  aipm-agent:
    build:
      context: /path/to/Aipm
      dockerfile: Dockerfile
    container_name: aipm-agent
    restart: unless-stopped
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://api.openai.com/v1}
      AIPM_PUBLIC_BASE_URL: https://semaa.site/aipm
      LIBRECHAT_MONGO_URI: mongodb://mongodb:27017/LibreChat
      LIBRECHAT_CONTAINER_UPLOADS_DIR: /app/uploads
      LIBRECHAT_UPLOADS_DIR: /app/librechat_uploads
    volumes:
      - /path/to/Aipm/outputs:/app/outputs
      - ./uploads:/app/librechat_uploads:ro
    expose:
      - "8000"
    depends_on:
      - mongodb
```

For local Mac testing from LibreChat Docker to a host-run AIPM backend, keep the schema server as `http://host.docker.internal:8000`. For a server deployment where AIPM runs in Docker beside LibreChat, use `http://aipm-agent:8000`.

## API Endpoints

- `GET /health`
- `GET /strategies`
- `GET /`
- `GET /upload`
- `POST /upload`
- `POST /runs/csv-text`
- `POST /runs/librechat-files`
- `POST /runs/librechat-recent`
- `POST /runs/local-files`
- `POST /runs`
- `POST /runs/auto`
- `POST /runs/sample`
- `GET /runs`
- `GET /runs/{run_id}/report`
- `GET /runs/{run_id}/schedule.csv`
- `GET /runs/{run_id}/findings`
- `GET /runs/{run_id}/divergences.csv`

## LibreChat Integration Shape

LibreChat should call the AIPM API as an Agent Action. The AIPM API exposes OpenAPI automatically at:

```text
http://aipm-agent:8000/openapi.json
```

Use `ortools_precedence` as the default strategy for sponsor demonstrations.

For sponsor-facing LibreChat chatbox uploads, use `POST /runs/librechat-recent`. Upload the CSVs in LibreChat and have the action pass visible filenames if it can see them. If it cannot see filenames, AIPM will use the latest four CSV upload records from LibreChat MongoDB. This is the reliable one-interface workflow. For sponsor runs, set `use_openai=true` and start AIPM with `OPENAI_API_KEY` so the AI diagnosis layer runs.

Use `GET /strategies` when the sponsor wants to choose a strategy. For the main demo, recommend `ortools_precedence`, but allow users to pick any listed strategy.

`POST /runs/librechat-files` remains available for a future tighter integration if LibreChat exposes attachment `file_id` values directly to the action.

`POST /runs/csv-text` remains available only as a debugging fallback. It is not the preferred sponsor workflow because it depends on LibreChat/LLM context carrying complete CSV contents.

For local LibreChat Action testing against files already in the AIPM folder, use `POST /runs/local-files`. This endpoint expects the CSV files to already exist in the AIPM `data/` folder and accepts their names as JSON.

For reliable local file upload, use the AIPM browser upload page at `http://127.0.0.1:8000/upload`. This page sends a true multipart upload to the AIPM backend and immediately returns links to the generated artifacts.

For production with a dedicated upload form or another client that can send true multipart uploads, use `POST /runs/auto` with the repeated form field name `files`. The order of those uploaded files does not matter; the API saves them and the agent detects file type by CSV headers/columns. The API returns links for the generated HTML report, schedule CSV, findings text, and timing-divergence CSV. The server-side AIPM container should hold the OpenAI key, so sponsors only interact through LibreChat.

For local Mac testing, returned artifact links use `http://127.0.0.1:8000` because those links are opened by the user's browser on the Mac. LibreChat itself calls the API through `http://host.docker.internal:8000`.

The older `POST /runs` endpoint remains available for clients that prefer named fields:

```text
product_order_csv
work_order_csv
resource_master_csv
reference_schedule_csv
```

For internal demos using the sample data mounted from this repository, call:

```text
POST http://aipm-agent:8000/runs/sample?strategy=ortools_precedence&use_openai=true
```

For deterministic no-LLM testing, use:

```text
POST http://aipm-agent:8000/runs/sample?strategy=ortools_precedence&use_openai=false
```

## Smoke Test Results

Verified locally on the MacBook:

- `GET /health` returns `{"status":"ok"}`.
- `GET /openapi.json` returns the LibreChat-readable OpenAPI spec.
- `GET /upload` returns the browser upload page.
- `POST /upload` accepts browser multipart CSV uploads and returns artifact links.
- `POST /runs/csv-text` accepts CSV contents from LibreChat text-file uploads and returns artifact links.
- `POST /runs/sample?strategy=ortools_precedence&use_openai=false` generates report, schedule, findings, and divergence artifacts.
- `POST /runs/local-files` accepts JSON file names for LibreChat Action testing.
- `POST /runs/auto` accepts generic multipart CSV uploads in arbitrary order and returns artifact links.
- `POST /runs` accepts named multipart CSV uploads and returns artifact links.
- Existing Python test suite passes: `17` tests.

## Notes

- The existing `aipm_agent_app.py` remains the lightweight local browser UI.
- The deployable service is `aipm_api.py`.
- Both use the same core agent code in `planning_scheduling_agent.py`.
