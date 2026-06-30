# Local LibreChat + AIPM Setup

This guide runs LibreChat locally on the MacBook and connects it to the local AIPM backend before deploying to `semaa.site`.

## 1. Start the AIPM Backend

From the AIPM project folder:

```bash
cd /Users/yanjin/Library/CloudStorage/OneDrive-Personal/Codex/Aipm
LIBRECHAT_MONGO_URI=mongodb://127.0.0.1:27017/LibreChat \
LIBRECHAT_UPLOADS_DIR=/Users/yanjin/Codex/LibreChat/uploads \
OPENAI_API_KEY=replace-with-your-openai-key \
python -m uvicorn aipm_api:app --host 127.0.0.1 --port 8000
```

Alternatively, put `OPENAI_API_KEY=...` in the AIPM project `.env` file and start AIPM without typing the key:

```bash
LIBRECHAT_MONGO_URI=mongodb://127.0.0.1:27017/LibreChat \
LIBRECHAT_UPLOADS_DIR=/Users/yanjin/Codex/LibreChat/uploads \
python -m uvicorn aipm_api:app --host 127.0.0.1 --port 8000
```

If the key lives in another env file, such as the LibreChat folder's `.env`, point AIPM to it:

```bash
AIPM_ENV_FILE=/Users/yanjin/Codex/LibreChat/.env \
LIBRECHAT_MONGO_URI=mongodb://127.0.0.1:27017/LibreChat \
LIBRECHAT_UPLOADS_DIR=/Users/yanjin/Codex/LibreChat/uploads \
python -m uvicorn aipm_api:app --host 127.0.0.1 --port 8000
```

Omit the key only when you intentionally want deterministic/offline findings.

Check it:

```bash
curl http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok"}
```

## 2. Install LibreChat Locally

From a folder where you keep local development projects:

```bash
git clone https://github.com/danny-avila/LibreChat.git
cd LibreChat
cp .env.example .env
```

On Apple Silicon Macs, add this MongoDB override so MongoDB does not crash:

```yaml
# docker-compose.override.yml
services:
  mongodb:
    image: mongo:4.4.18
    ports:
      - "127.0.0.1:27017:27017"
  api:
    volumes:
      - type: bind
        source: ./librechat.yaml
        target: /app/librechat.yaml
```

## 3. Configure LibreChat to Allow the Local AIPM Action

Create `librechat.yaml` in the LibreChat folder:

```yaml
version: 1.3.5
cache: true

actions:
  allowedAddresses:
    - "host.docker.internal:8000"
```

Why `host.docker.internal`:

- LibreChat runs inside Docker.
- AIPM is running on the Mac host at `127.0.0.1:8000`.
- From inside Docker, the Mac host is reachable as `host.docker.internal`.

The AIPM OpenAPI URL for LibreChat Actions is:

```text
http://host.docker.internal:8000/openapi.json
```

## 4. Start LibreChat

From the LibreChat folder:

```bash
docker compose up -d
```

Open:

```text
http://localhost:3080
```

The first registered account becomes the admin account.

## 5. Add the AIPM Action in LibreChat

In LibreChat, add the AIPM Action:

1. Create or open an Agent.
2. Add an Action.
3. Paste the schema from:

```text
/Users/yanjin/Library/CloudStorage/OneDrive-Personal/Codex/Aipm/aipm_openapi_librechat.json
```

4. Select the AIPM action/tool.
5. Use `GET /strategies` when a user asks for strategy choices. Prefer the run endpoint:

```text
POST /runs/librechat-recent
```

## 6. Chatbox Upload Workflow

Upload the four CSV files in the LibreChat chatbox. For the sponsor workflow, the AIPM action should use recent LibreChat upload records, not pasted CSV contents. Then ask:

```text
Run the AIPM planning and scheduling agent using these uploaded files. Use ortools_precedence. Use the recent LibreChat uploads; do not ask me for file IDs.
```

This uses `POST /runs/librechat-recent`, where LibreChat passes visible filenames if it can see them:

```json
{
  "strategy": "ortools_precedence",
  "filenames": [
    "オーダ情報(作業情報).csv",
    "オーダ情報(製品情報).csv",
    "中日程工程.csv",
    "資源マスタ.csv"
  ]
}
```

File order does not matter because AIPM identifies each file from its CSV columns.

If LibreChat cannot see filenames either, it can omit `filenames`; AIPM will use the latest four recent CSV uploads from LibreChat MongoDB.

If LibreChat only offers `Text` or `Cancel`, choose `Text` for CSV files. AIPM will read the complete CSV text stored in LibreChat's recent file records instead of asking the LLM to paste the CSV into the action.

For Excel and other binary formats later, we will need LibreChat to preserve the original uploaded file bytes or add a LibreChat-side forwarding bridge.

## 7. Alternative Browser Upload Workflow

If the file-ID bridge cannot see the uploaded file during local debugging, use AIPM's direct upload page:

```text
http://127.0.0.1:8000/upload
```

For LibreChat follow-up:

```text
Explain the AIPM run results from this report URL: http://127.0.0.1:8000/runs/.../report
```

## 8. Local Files Workflow

For files already in AIPM `data/`, ask:

```text
Run the AIPM planning and scheduling agent using ortools_precedence. Use these file names:
オーダ情報(作業情報).csv
オーダ情報(製品情報).csv
中日程工程.csv
資源マスタ.csv
```

This uses `POST /runs/local-files`. Do not use this workflow for sponsors, because it bypasses the uploaded LibreChat attachments.

## 9. Troubleshooting

If LibreChat cannot reach AIPM:

```bash
curl http://127.0.0.1:8000/health
```

If that works on the Mac, test from inside the LibreChat API container:

```bash
docker compose exec api curl http://host.docker.internal:8000/health
```

If LibreChat fails on config:

```bash
docker compose logs api
```

If port `3080` is already in use, change the LibreChat API port mapping in `docker-compose.override.yml`.
