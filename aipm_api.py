from __future__ import annotations

import csv
import html
import io
import os
import shutil
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from openai_reasoning_client import load_env_file
from planning_scheduling_agent import PlanningSchedulingAgent, write_findings, write_timing_divergences


# What: Deployable FastAPI wrapper for the AIPM planning/scheduling agent.
# Purpose: Exposes the local agent as HTTP endpoints usable by LibreChat Actions or a web client.

# What: Local environment loader.
# Purpose: Makes API settings available from .env before module-level constants are initialized.
load_env_file(os.environ.get("AIPM_ENV_FILE", ".env"))

# What: Persistent API run folder.
# Purpose: Separates uploaded input files and generated artifacts by run ID.
RUNS_DIR = Path("outputs/api_runs")

# What: Public browser base URL for returned artifact links.
# Purpose: Lets LibreChat show links that open directly in the user's browser.
PUBLIC_BASE_URL = os.getenv("AIPM_PUBLIC_BASE_URL", "http://127.0.0.1:8000")

# What: LibreChat MongoDB connection string.
# Purpose: Lets AIPM resolve LibreChat upload file IDs into stored file metadata.
LIBRECHAT_MONGO_URI = os.getenv("LIBRECHAT_MONGO_URI", "mongodb://mongodb:27017/LibreChat")

# What: LibreChat upload path as recorded inside the LibreChat container.
# Purpose: Provides the prefix AIPM rewrites when locating files through a shared volume.
LIBRECHAT_CONTAINER_UPLOADS_DIR = os.getenv("LIBRECHAT_CONTAINER_UPLOADS_DIR", "/app/uploads")

# What: LibreChat upload path as mounted inside the AIPM container or local host.
# Purpose: Gives AIPM read access to original uploaded files when LibreChat stores them locally.
LIBRECHAT_UPLOADS_DIR = os.getenv("LIBRECHAT_UPLOADS_DIR", "/app/librechat_uploads")

# What: Generated artifact filename markers.
# Purpose: Prevents output files uploaded for discussion from being reused as schedule inputs.
GENERATED_ARTIFACT_NAME_MARKERS = (
    "agent_",
    "divergence",
    "divergences",
    "findings",
    "report",
    "schedule",
    "middle_schedule",
    "timing",
)

# What: Supported scheduling strategies for API callers.
# Purpose: Keeps the API contract aligned with PlanningSchedulingAgent.generate_schedule().
Strategy = Literal[
    "baseline",
    "reference_learning",
    "field_repair",
    "ortools_cp",
    "ortools_precedence",
    "reference_replay",
]

app = FastAPI(
    title="AIPM Planning and Scheduling Agent API",
    version="0.1.0",
    description=(
        "Runs the AIPM planning/scheduling agent on uploaded D6-style CSV files "
        "and returns visual reports, schedule CSVs, findings, and diagnostics."
    ),
)


# What: Run creation response.
# Purpose: Provides artifact URLs and key findings after an agent execution.
class RunResponse(BaseModel):
    run_id: str
    strategy: str
    model: str
    report_url: str
    schedule_url: str
    findings_url: str
    divergences_url: str
    findings: list[str]


# What: Strategy description response.
# Purpose: Lets LibreChat show user-friendly scheduling choices before running AIPM.
class StrategyInfo(BaseModel):
    strategy: Strategy
    label: str
    description: str
    recommended_for: str


# What: LibreChat-friendly local-file run request.
# Purpose: Lets Actions pass file names as JSON when LibreChat cannot forward binary uploads.
class LocalFilesRunRequest(BaseModel):
    strategy: Strategy = "ortools_precedence"
    model: str = "gpt-5.4-mini"
    use_openai: bool = False
    files: list[str] = Field(
        default_factory=list,
        description=(
            "CSV file names already available in the AIPM data folder. "
            "Order does not matter. If omitted, all CSV files in data/ are used."
        ),
    )


# What: One text-uploaded CSV file.
# Purpose: Carries LibreChat-readable CSV attachment content into the AIPM backend.
class CsvTextFile(BaseModel):
    filename: str
    content: str


# What: LibreChat text-file run request.
# Purpose: Lets users upload CSVs through LibreChat as text files and pass their contents to AIPM.
class CsvTextRunRequest(BaseModel):
    strategy: Strategy = "ortools_precedence"
    model: str = "gpt-5.4-mini"
    use_openai: bool = False
    files: list[CsvTextFile] = Field(
        description=(
            "CSV files uploaded through LibreChat as text. Include each original filename "
            "and the complete CSV text content."
        ),
        min_length=4,
    )


# What: LibreChat file-ID run request.
# Purpose: Lets LibreChat pass uploaded attachment IDs while AIPM retrieves the actual file records.
class LibreChatFilesRunRequest(BaseModel):
    strategy: Strategy = "ortools_precedence"
    model: str = "gpt-5.4-mini"
    use_openai: bool = False
    file_ids: list[str] = Field(
        min_length=4,
        description=(
            "LibreChat file_id values for the uploaded AIPM input files. "
            "Order does not matter, but each ID must refer to an uploaded CSV file."
        ),
    )


# What: Recent LibreChat upload run request.
# Purpose: Lets LibreChat run AIPM without exposing internal file IDs to the user.
class LibreChatRecentFilesRunRequest(BaseModel):
    strategy: Strategy = "ortools_precedence"
    model: str = "gpt-5.4-mini"
    use_openai: bool = True
    filenames: list[str] = Field(
        default_factory=list,
        description=(
            "Visible filenames from the user's recent LibreChat uploads. "
            "If omitted, AIPM uses the latest four CSV upload records."
        ),
    )
    max_age_minutes: int = Field(
        default=180,
        ge=1,
        le=1440,
        description="Only consider LibreChat uploads created within this many minutes.",
    )


# What: Health endpoint.
# Purpose: Allows DigitalOcean/LibreChat/reverse proxies to verify the service is alive.
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# What: Scheduling strategy catalog endpoint.
# Purpose: Gives LibreChat a concise menu of available AIPM strategies.
@app.get("/strategies", response_model=list[StrategyInfo])
def list_strategies() -> list[StrategyInfo]:
    return [
        StrategyInfo(
            strategy="ortools_precedence",
            label="OR-Tools precedence",
            description=(
                "Uses OR-Tools with learned/documented precedence constraints and deterministic "
                "post-processing. This is the strongest current general-purpose strategy."
            ),
            recommended_for="Default sponsor runs and comparison against the reference schedule.",
        ),
        StrategyInfo(
            strategy="ortools_cp",
            label="OR-Tools capacity",
            description=(
                "Uses a constraint-programming style scheduler focused on capacity/resource logic."
            ),
            recommended_for="Exploring resource-constrained alternatives.",
        ),
        StrategyInfo(
            strategy="field_repair",
            label="Field repair",
            description=(
                "Starts from a generated schedule and repairs fields that are commonly divergent."
            ),
            recommended_for="Diagnostics when timing is close but flags/status fields differ.",
        ),
        StrategyInfo(
            strategy="reference_learning",
            label="Reference learning",
            description=(
                "Learns patterns from the provided middle schedule and applies them to the input orders."
            ),
            recommended_for="Benchmarking against the provided reference schedule.",
        ),
        StrategyInfo(
            strategy="reference_replay",
            label="Reference replay",
            description=(
                "Replays the supplied reference schedule as closely as possible for known rows."
            ),
            recommended_for="Upper-bound sanity checks, not new unseen production scheduling.",
        ),
        StrategyInfo(
            strategy="baseline",
            label="Baseline",
            description=(
                "Simple deterministic baseline schedule without the richer constraint/reconciliation logic."
            ),
            recommended_for="Measuring how much the advanced strategies improve over a simple baseline.",
        ),
    ]


# What: Browser landing page.
# Purpose: Gives users a friendly entry point instead of a JSON 404 at the API root.
@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(_render_upload_page())


# What: Browser upload page.
# Purpose: Lets users upload CSV files directly when LibreChat cannot stream attachments to Actions.
@app.get("/upload", response_class=HTMLResponse)
def upload_page() -> HTMLResponse:
    return HTMLResponse(_render_upload_page())


# What: Browser upload handler.
# Purpose: Accepts true multipart CSV uploads, runs the agent, and returns result links.
@app.post("/upload", response_class=HTMLResponse)
async def upload_and_run(
    strategy: Strategy = Form("ortools_precedence"),
    model: str = Form("gpt-5.4-mini"),
    use_openai: bool = Form(False),
    files: list[UploadFile] = File(...),
) -> HTMLResponse:
    try:
        result = await _create_uploaded_run(
            strategy=strategy,
            model=model,
            use_openai=use_openai,
            named_uploads={},
            generic_uploads=files,
        )
    except HTTPException as exc:
        return HTMLResponse(_render_upload_page(error=str(exc.detail)), status_code=exc.status_code)
    return HTMLResponse(_render_upload_page(result=result))


# What: LibreChat text-file endpoint.
# Purpose: Runs the agent from CSV contents that LibreChat read from chatbox uploads.
@app.post("/runs/csv-text", response_model=RunResponse)
async def create_csv_text_run(request: Request) -> RunResponse:
    payload = await request.json()
    strategy = payload.get("strategy", "ortools_precedence")
    model = payload.get("model", "gpt-5.4-mini")
    use_openai = bool(payload.get("use_openai", False))
    files = _extract_csv_text_files(payload)

    run_id = uuid.uuid4().hex
    run_dir = RUNS_DIR / run_id
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    missing_content: list[str] = []
    for index, uploaded_file in enumerate(files, start=1):
        if uploaded_file.content.strip():
            filename = _safe_csv_filename(uploaded_file.filename, index)
            (data_dir / filename).write_text(
                _clean_csv_text(uploaded_file.content),
                encoding="utf-8-sig",
            )
            copied_count += 1
        else:
            missing_content.append(uploaded_file.filename)

    if copied_count < 4:
        raise HTTPException(
            status_code=400,
            detail=(
                "AIPM received fewer than four CSV files with complete text content. "
                "Do not send only filenames or attachment metadata. Missing content for: "
                + (", ".join(missing_content) if missing_content else "unknown files")
            ),
        )

    return _run_agent(
        data_dir=data_dir,
        run_dir=run_dir,
        strategy=strategy,
        model=model,
        use_openai=use_openai,
    )


# What: LibreChat file-ID endpoint.
# Purpose: Runs AIPM from files already uploaded through the LibreChat chatbox.
@app.post("/runs/librechat-files", response_model=RunResponse)
def create_librechat_files_run(request: LibreChatFilesRunRequest) -> RunResponse:
    run_id = uuid.uuid4().hex
    run_dir = RUNS_DIR / run_id
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    resolved_files = _resolve_librechat_file_ids(request.file_ids)
    if len(resolved_files) < 4:
        raise HTTPException(
            status_code=400,
            detail="Expected at least four LibreChat file IDs for the AIPM input set.",
        )

    for index, (source_path, filename, text_content) in enumerate(resolved_files, start=1):
        destination = data_dir / _safe_csv_filename(filename, index)
        if source_path is not None:
            shutil.copyfile(source_path, destination)
        else:
            destination.write_text(_librechat_text_to_csv(text_content or ""), encoding="utf-8-sig")

    return _run_agent(
        data_dir=data_dir,
        run_dir=run_dir,
        strategy=request.strategy,
        model=request.model,
        use_openai=request.use_openai,
    )


# What: Recent LibreChat upload endpoint.
# Purpose: Runs AIPM from the latest CSV uploads when LibreChat does not expose file IDs.
@app.post("/runs/librechat-recent", response_model=RunResponse)
def create_librechat_recent_run(request: LibreChatRecentFilesRunRequest) -> RunResponse:
    run_id = uuid.uuid4().hex
    run_dir = RUNS_DIR / run_id
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    resolved_files = _resolve_recent_librechat_files(
        filenames=request.filenames,
        max_age_minutes=request.max_age_minutes,
    )
    if len(resolved_files) < 4:
        raise HTTPException(
            status_code=400,
            detail=(
                "Expected at least four recent LibreChat CSV uploads. "
                "Upload the four AIPM CSV files in this conversation and try again."
            ),
        )

    for index, (source_path, filename, text_content) in enumerate(resolved_files, start=1):
        destination = data_dir / _safe_csv_filename(filename, index)
        if source_path is not None:
            shutil.copyfile(source_path, destination)
        else:
            destination.write_text(_librechat_text_to_csv(text_content or ""), encoding="utf-8-sig")

    return _run_agent(
        data_dir=data_dir,
        run_dir=run_dir,
        strategy=request.strategy,
        model=request.model,
        use_openai=request.use_openai,
    )


# What: LibreChat JSON run endpoint.
# Purpose: Runs the agent from local CSV files when LibreChat Actions only pass attachment names.
@app.post("/runs/local-files", response_model=RunResponse)
def create_local_files_run(request: LocalFilesRunRequest) -> RunResponse:
    run_id = uuid.uuid4().hex
    run_dir = RUNS_DIR / run_id
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    selected_files = _resolve_local_csv_files(request.files)
    if len(selected_files) < 4:
        raise HTTPException(
            status_code=400,
            detail=(
                "Expected at least four local CSV files. Put the product/order, work/order, "
                "resource master, and reference schedule CSVs in the AIPM data/ folder."
            ),
        )
    for source_path in selected_files:
        shutil.copyfile(source_path, data_dir / source_path.name)

    return _run_agent(
        data_dir=data_dir,
        run_dir=run_dir,
        strategy=request.strategy,
        model=request.model,
        use_openai=request.use_openai,
    )


# What: Agent run endpoint.
# Purpose: Accepts uploaded CSV files, executes the selected strategy, and writes run artifacts.
@app.post("/runs", response_model=RunResponse)
async def create_run(
    strategy: Strategy = Form("ortools_precedence"),
    model: str = Form("gpt-5.4-mini"),
    use_openai: bool = Form(True),
    product_order_csv: UploadFile | None = File(None),
    work_order_csv: UploadFile | None = File(None),
    resource_master_csv: UploadFile | None = File(None),
    reference_schedule_csv: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
) -> RunResponse:
    return await _create_uploaded_run(
        strategy=strategy,
        model=model,
        use_openai=use_openai,
        named_uploads={
            "product_order.csv": product_order_csv,
            "work_order.csv": work_order_csv,
            "resource_master.csv": resource_master_csv,
            "reference_schedule.csv": reference_schedule_csv,
        },
        generic_uploads=files or [],
    )


# What: Order-independent upload endpoint.
# Purpose: Lets LibreChat or a web client send all input CSVs as a generic file list.
@app.post("/runs/auto", response_model=RunResponse)
async def create_auto_run(
    strategy: Strategy = Form("ortools_precedence"),
    model: str = Form("gpt-5.4-mini"),
    use_openai: bool = Form(True),
    files: list[UploadFile] = File(...),
) -> RunResponse:
    return await _create_uploaded_run(
        strategy=strategy,
        model=model,
        use_openai=use_openai,
        named_uploads={},
        generic_uploads=files,
    )


# What: Shared uploaded-run builder.
# Purpose: Saves named and generic uploads before running the same core planning agent.
async def _create_uploaded_run(
    strategy: Strategy,
    model: str,
    use_openai: bool,
    named_uploads: dict[str, UploadFile | None],
    generic_uploads: list[UploadFile],
) -> RunResponse:
    run_id = uuid.uuid4().hex
    run_dir = RUNS_DIR / run_id
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    saved_count = 0
    for target_name, upload in named_uploads.items():
        if upload is None:
            continue
        await _save_upload(upload, data_dir / target_name)
        saved_count += 1
    for index, upload in enumerate(generic_uploads, start=1):
        safe_name = f"upload_{index}.csv"
        await _save_upload(upload, data_dir / safe_name)
        saved_count += 1
    if saved_count < 4:
        raise HTTPException(
            status_code=400,
            detail=(
                "Upload at least four CSV files: product/order, work/order, "
                "resource master, and reference middle schedule. File order does not matter."
            ),
        )

    return _run_agent(
        data_dir=data_dir,
        run_dir=run_dir,
        strategy=strategy,
        model=model,
        use_openai=use_openai,
    )


# What: Shared agent runner.
# Purpose: Executes the planner and returns a consistent API response for all run endpoints.
def _run_agent(
    data_dir: Path,
    run_dir: Path,
    strategy: Strategy,
    model: str,
    use_openai: bool,
) -> RunResponse:
    reasoning_client = None
    if use_openai:
        try:
            from openai_reasoning_client import OpenAIReasoningClient

            reasoning_client = OpenAIReasoningClient()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        agent = PlanningSchedulingAgent(
            data_dir=data_dir,
            reasoning_client=reasoning_client,
            model=model,
        )
        result = agent.solve(
            strategy=strategy,
            output_path=run_dir / "agent_middle_schedule.csv",
            report_path=run_dir / "agent_schedule_report.html",
        )
        findings_path = run_dir / "agent_findings.txt"
        divergences_path = run_dir / "agent_timing_divergences.csv"
        write_findings(result, findings_path)
        write_timing_divergences(result.analysis.divergences, divergences_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    run_id = run_dir.name
    return RunResponse(
        run_id=run_id,
        strategy=strategy,
        model=model if use_openai else "offline",
        report_url=_public_url(f"/runs/{run_id}/report.html"),
        schedule_url=_public_url(f"/runs/{run_id}/schedule.csv"),
        findings_url=_public_url(f"/runs/{run_id}/findings"),
        divergences_url=_public_url(f"/runs/{run_id}/divergences.csv"),
        findings=result.analysis.findings,
    )


# What: Report endpoint.
# Purpose: Returns the generated visual HTML report for one run.
@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
@app.get("/runs/{run_id}/report.html", response_class=HTMLResponse)
def get_report(run_id: str) -> FileResponse:
    return _inline_file_response(run_id, "agent_schedule_report.html", "text/html")


# What: Schedule CSV endpoint.
# Purpose: Returns the generated middle-level schedule CSV for one run.
@app.get("/runs/{run_id}/schedule.csv", response_class=Response)
def get_schedule(run_id: str) -> FileResponse:
    return _file_response(run_id, "agent_middle_schedule.csv", "text/csv")


# What: Findings endpoint.
# Purpose: Returns the text findings for one run.
@app.get("/runs/{run_id}/findings", response_class=PlainTextResponse)
def get_findings(run_id: str) -> FileResponse:
    return _file_response(run_id, "agent_findings.txt", "text/plain")


# What: Timing-divergence CSV endpoint.
# Purpose: Returns row-level timing diagnostics for one run.
@app.get("/runs/{run_id}/divergences.csv", response_class=Response)
def get_divergences(run_id: str) -> FileResponse:
    return _file_response(run_id, "agent_timing_divergences.csv", "text/csv")


# What: Run listing endpoint.
# Purpose: Lets operators inspect recent run IDs without shell access.
@app.get("/runs")
def list_runs() -> JSONResponse:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_ids = sorted([path.name for path in RUNS_DIR.iterdir() if path.is_dir()], reverse=True)
    return JSONResponse({"runs": run_ids})


# What: Upload saver.
# Purpose: Persists uploaded CSV files into the run-specific data directory.
async def _save_upload(upload: UploadFile, destination: Path) -> None:
    with destination.open("wb") as stream:
        while chunk := await upload.read(1024 * 1024):
            stream.write(chunk)


# What: Local CSV file resolver.
# Purpose: Maps LibreChat-provided attachment names to CSV files already present in AIPM data/.
def _resolve_local_csv_files(file_names: list[str]) -> list[Path]:
    available = list(Path("data").glob("*.csv"))
    if not file_names:
        return available

    selected: list[Path] = []
    available_by_name = {_normalize_filename(path.name): path for path in available}
    missing: list[str] = []
    for raw_name in file_names:
        name = Path(str(raw_name)).name
        match = available_by_name.get(_normalize_filename(name))
        if match is None:
            missing.append(name)
            continue
        if match not in selected:
            selected.append(match)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                "These files were named by LibreChat but are not present in AIPM data/: "
                + ", ".join(missing)
            ),
        )
    return selected


# What: LibreChat file-ID resolver.
# Purpose: Converts LibreChat attachment IDs into readable local paths through MongoDB metadata.
def _resolve_librechat_file_ids(file_ids: list[str]) -> list[tuple[Path | None, str, str | None]]:
    file_records = _load_librechat_file_records(file_ids)
    return _resolve_librechat_file_records(file_records, requested_file_ids=file_ids)


# What: Recent LibreChat upload resolver.
# Purpose: Finds the user's latest CSV uploads by visible filename when file IDs are hidden.
def _resolve_recent_librechat_files(
    filenames: list[str],
    max_age_minutes: int,
) -> list[tuple[Path | None, str, str | None]]:
    records = _load_recent_librechat_file_records(
        filenames=filenames,
        max_age_minutes=max_age_minutes,
    )
    if not records:
        raise HTTPException(
            status_code=400,
            detail=(
                "No recent LibreChat CSV uploads were found. "
                "Upload the AIPM CSV files in LibreChat and choose Text if prompted."
            ),
        )
    return _resolve_librechat_file_records(records)


# What: LibreChat file-record resolver.
# Purpose: Converts Mongo file documents into AIPM-readable upload payloads.
def _resolve_librechat_file_records(
    file_records: list[dict[str, Any]],
    requested_file_ids: list[str] | None = None,
) -> list[tuple[Path | None, str, str | None]]:
    resolved_files: list[tuple[Path | None, str, str | None]] = []
    missing_records: list[str] = []
    unusable_records: list[str] = []

    if requested_file_ids is None:
        ordered_records = file_records
    else:
        by_file_id = {str(record.get("file_id")): record for record in file_records}
        ordered_records = []
        for file_id in requested_file_ids:
            record = by_file_id.get(file_id)
            if not record:
                missing_records.append(file_id)
                continue
            ordered_records.append(record)

    for record in ordered_records:
        file_id = str(record.get("file_id") or "unknown")
        filename = str(record.get("filename") or f"{file_id}.csv")
        filepath = str(record.get("filepath") or "")
        source = str(record.get("source") or "unknown")
        text_content = str(record.get("text") or "")
        source_path = _librechat_storage_path(filepath)
        if not filename.lower().endswith(".csv"):
            unusable_records.append(f"{filename} ({file_id}) is not a CSV file.")
            continue
        if source_path.exists():
            resolved_files.append((source_path, filename, None))
            continue
        if text_content.strip():
            resolved_files.append((None, filename, text_content))
            continue
        if not source_path.exists():
            unusable_records.append(
                f"{filename} ({file_id}) was not found at {source_path}. "
                f"LibreChat recorded source={source}. Upload it as a file attachment "
                "that LibreChat keeps in local storage or as complete text."
            )
            continue

    if missing_records or unusable_records:
        details = []
        if missing_records:
            details.append("Missing LibreChat file IDs: " + ", ".join(missing_records))
        details.extend(unusable_records)
        raise HTTPException(status_code=400, detail=" ".join(details))

    return resolved_files


# What: LibreChat file metadata loader.
# Purpose: Reads the `files` collection without coupling AIPM to LibreChat application code.
def _load_librechat_file_records(file_ids: list[str]) -> list[dict[str, Any]]:
    try:
        from pymongo import MongoClient
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "The AIPM backend needs pymongo installed to read LibreChat file metadata. "
                "Install project requirements and restart the service."
            ),
        ) from exc

    try:
        client = MongoClient(LIBRECHAT_MONGO_URI, serverSelectionTimeoutMS=3000)
        database = client.get_default_database()
        return list(
            database.files.find(
                {"file_id": {"$in": file_ids}},
                {
                    "_id": 0,
                    "file_id": 1,
                    "filename": 1,
                    "filepath": 1,
                    "source": 1,
                    "text": 1,
                    "type": 1,
                },
            )
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read LibreChat file metadata from MongoDB: {exc}",
        ) from exc
    finally:
        try:
            client.close()
        except Exception:
            pass


# What: Recent LibreChat file metadata loader.
# Purpose: Finds fresh CSV uploads so users do not have to manually provide hidden file IDs.
def _load_recent_librechat_file_records(
    filenames: list[str],
    max_age_minutes: int,
) -> list[dict[str, Any]]:
    try:
        from pymongo import MongoClient
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "The AIPM backend needs pymongo installed to read LibreChat file metadata. "
                "Install project requirements and restart the service."
            ),
        ) from exc

    since = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    normalized_targets = {_normalize_filename(Path(name).name) for name in filenames if name}
    client = None
    try:
        client = MongoClient(LIBRECHAT_MONGO_URI, serverSelectionTimeoutMS=3000)
        database = client.get_default_database()
        query: dict[str, Any] = {
            "createdAt": {"$gte": since},
            "filename": {"$regex": r"\.csv$", "$options": "i"},
        }
        records = list(
            database.files.find(
                query,
                {
                    "_id": 0,
                    "file_id": 1,
                    "filename": 1,
                    "filepath": 1,
                    "source": 1,
                    "text": 1,
                    "type": 1,
                    "createdAt": 1,
                },
            ).sort("createdAt", -1)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read recent LibreChat file metadata from MongoDB: {exc}",
        ) from exc
    finally:
        if client is not None:
            client.close()

    latest_by_name: dict[str, dict[str, Any]] = {}
    for record in records:
        filename = str(record.get("filename") or "")
        normalized_name = _normalize_filename(filename)
        if _is_generated_artifact_name(normalized_name):
            continue
        if normalized_targets and normalized_name not in normalized_targets:
            continue
        latest_by_name.setdefault(normalized_name, record)

    selected = list(latest_by_name.values())
    if normalized_targets:
        missing = sorted(normalized_targets - set(latest_by_name))
        if missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    "These uploaded filenames were not found in recent LibreChat file records: "
                    + ", ".join(missing)
                ),
            )
        return selected

    return selected[:4]


# What: LibreChat storage path mapper.
# Purpose: Rewrites LibreChat's internal upload path to the path visible to AIPM.
def _librechat_storage_path(filepath: str) -> Path:
    container_prefix = LIBRECHAT_CONTAINER_UPLOADS_DIR.rstrip("/")
    visible_prefix = Path(LIBRECHAT_UPLOADS_DIR)
    if filepath.startswith(container_prefix + "/"):
        relative_path = filepath[len(container_prefix) + 1 :]
        return visible_prefix / relative_path
    return Path(filepath)


# What: Generated artifact detector.
# Purpose: Identifies AIPM output files that should not be treated as planning inputs.
def _is_generated_artifact_name(normalized_filename: str) -> bool:
    return any(marker in normalized_filename for marker in GENERATED_ARTIFACT_NAME_MARKERS)


# What: CSV text payload normalizer.
# Purpose: Accepts multiple LibreChat tool-call shapes instead of failing strict validation.
def _extract_csv_text_files(payload: dict[str, object]) -> list[CsvTextFile]:
    raw_files = payload.get("files") or payload.get("csv_files") or payload.get("uploaded_files") or []
    normalized_files: list[CsvTextFile] = []

    if isinstance(raw_files, dict):
        raw_files = [
            {"filename": filename, "content": content}
            for filename, content in raw_files.items()
        ]

    if not isinstance(raw_files, list):
        raise HTTPException(status_code=400, detail="Expected 'files' to be a list.")

    for index, raw_file in enumerate(raw_files, start=1):
        if isinstance(raw_file, str):
            normalized_files.append(CsvTextFile(filename=raw_file, content=""))
            continue
        if not isinstance(raw_file, dict):
            continue
        filename = (
            raw_file.get("filename")
            or raw_file.get("name")
            or raw_file.get("file_name")
            or f"upload_{index}.csv"
        )
        content = (
            raw_file.get("content")
            or raw_file.get("text")
            or raw_file.get("csv")
            or raw_file.get("data")
            or ""
        )
        normalized_files.append(CsvTextFile(filename=str(filename), content=str(content)))

    return normalized_files


# What: Filename normalization helper.
# Purpose: Handles macOS Japanese Unicode normalization differences in uploaded filenames.
def _normalize_filename(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


# What: CSV filename sanitizer.
# Purpose: Preserves useful uploaded names while avoiding paths and ensuring CSV extensions.
def _safe_csv_filename(value: str, index: int) -> str:
    filename = Path(value or f"upload_{index}.csv").name
    if not filename.lower().endswith(".csv"):
        filename = f"{filename}.csv"
    return filename or f"upload_{index}.csv"


# What: CSV text normalizer.
# Purpose: Removes common Markdown code-fence wrapping from text copied through chat context.
def _clean_csv_text(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text + "\n"


# What: LibreChat parsed-text CSV reconstructor.
# Purpose: Converts LibreChat's `column: value` upload text back into CSV rows for AIPM.
def _librechat_text_to_csv(value: str) -> str:
    text = _clean_csv_text(value)
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if "," in first_line or "\t" in first_line:
        return text

    rows: list[dict[str, str]] = []
    fields: list[str] = []
    current_row: dict[str, str] = {}
    first_key: str | None = None
    parsed_lines = 0

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        if ": " in raw_line:
            key, value_part = raw_line.split(": ", 1)
        elif raw_line.endswith(":"):
            key, value_part = raw_line[:-1], ""
        else:
            continue

        key = key.strip()
        if not key:
            continue
        parsed_lines += 1
        if first_key is None:
            first_key = key
        elif key == first_key and current_row:
            rows.append(current_row)
            current_row = {}

        if key not in fields:
            fields.append(key)
        current_row[key] = value_part

    if current_row:
        rows.append(current_row)

    if parsed_lines == 0 or not rows or len(fields) < 2:
        return text

    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


# What: Public URL formatter.
# Purpose: Converts internal artifact routes into absolute URLs suitable for LibreChat responses.
def _public_url(path: str) -> str:
    return f"{PUBLIC_BASE_URL}{path}"


# What: Upload page renderer.
# Purpose: Builds a small self-contained HTML interface for sponsor-friendly CSV uploads.
def _render_upload_page(
    result: RunResponse | None = None,
    error: str | None = None,
) -> str:
    strategies = [
        ("ortools_precedence", "OR-Tools precedence"),
        ("ortools_cp", "OR-Tools capacity"),
        ("field_repair", "Field repair"),
        ("reference_learning", "Reference learning"),
        ("baseline", "Baseline"),
        ("reference_replay", "Reference replay"),
    ]
    strategy_options = "\n".join(
        f'<option value="{_escape(value)}">{_escape(label)}</option>' for value, label in strategies
    )
    error_html = f'<div class="notice error">{_escape(error)}</div>' if error else ""
    result_html = _render_upload_result(result) if result else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AIPM Planning Agent Upload</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #5b6475;
      --line: #d9dfeb;
      --accent: #2563eb;
      --accent-dark: #1d4ed8;
      --error: #b42318;
      --ok-bg: #eefbf3;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    main {{
      width: min(920px, calc(100vw - 32px));
      margin: 32px auto;
    }}
    header {{
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      box-shadow: 0 16px 40px rgba(23, 32, 51, 0.08);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin: 18px 0;
    }}
    label {{
      display: block;
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 6px;
    }}
    input, select {{
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      font: inherit;
      background: #fff;
    }}
    input[type="file"] {{
      min-height: 120px;
      padding: 20px;
      border-style: dashed;
    }}
    .check {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 12px 0 18px;
      color: var(--muted);
    }}
    .check input {{
      width: 18px;
      min-height: 18px;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: white;
      padding: 12px 16px;
      font-weight: 800;
      cursor: pointer;
    }}
    button:hover {{ background: var(--accent-dark); }}
    .notice {{
      margin: 16px 0;
      padding: 12px 14px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fff;
    }}
    .error {{
      color: var(--error);
      border-color: #f3b4ad;
      background: #fff5f3;
    }}
    .result {{
      margin-top: 20px;
      background: var(--ok-bg);
    }}
    .links {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    a {{
      color: var(--accent-dark);
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    ul {{
      margin: 12px 0 0;
      padding-left: 20px;
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .grid, .links {{ grid-template-columns: 1fr; }}
      main {{ margin: 18px auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>AIPM Planning Agent</h1>
      <p>Upload the four CSV files in any order. The agent detects product, work, resource, and reference schedule files from their columns.</p>
    </header>
    <section class="panel">
      {error_html}
      <form method="post" action="/upload" enctype="multipart/form-data">
        <label for="files">CSV files</label>
        <input id="files" name="files" type="file" accept=".csv,text/csv" multiple required>
        <div class="grid">
          <div>
            <label for="strategy">Strategy</label>
            <select id="strategy" name="strategy">{strategy_options}</select>
          </div>
          <div>
            <label for="model">GPT model</label>
            <input id="model" name="model" value="gpt-5.4-mini">
          </div>
        </div>
        <label class="check">
          <input type="checkbox" name="use_openai" value="true">
          Use AIPM backend GPT diagnosis if OPENAI_API_KEY is configured
        </label>
        <button type="submit">Run AIPM Agent</button>
      </form>
      {result_html}
    </section>
  </main>
</body>
</html>"""


# What: Upload result renderer.
# Purpose: Presents generated artifacts and a short findings preview after an upload run.
def _render_upload_result(result: RunResponse) -> str:
    finding_items = "\n".join(f"<li>{_escape(item)}</li>" for item in result.findings[:6])
    return f"""
      <div class="notice result">
        <strong>Run completed</strong>
        <p>Run ID: {_escape(result.run_id)} | Strategy: {_escape(result.strategy)} | Model: {_escape(result.model)}</p>
        <div class="links">
          <a href="{_escape(result.report_url)}" target="_blank" rel="noreferrer">Open visual report</a>
          <a href="{_escape(result.schedule_url)}" target="_blank" rel="noreferrer">Download schedule CSV</a>
          <a href="{_escape(result.findings_url)}" target="_blank" rel="noreferrer">Open findings</a>
          <a href="{_escape(result.divergences_url)}" target="_blank" rel="noreferrer">Download divergences CSV</a>
        </div>
        <ul>{finding_items}</ul>
      </div>
    """


# What: HTML escaping helper.
# Purpose: Prevents uploaded names or findings from being interpreted as markup.
def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


# What: Run artifact response helper.
# Purpose: Serves files safely from the run output directory.
def _file_response(run_id: str, filename: str, media_type: str) -> FileResponse:
    path = RUNS_DIR / run_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Missing artifact: {filename}")
    return FileResponse(path, media_type=media_type, filename=filename)


# What: Inline artifact response helper.
# Purpose: Opens browser-viewable artifacts like HTML reports instead of downloading them.
def _inline_file_response(run_id: str, filename: str, media_type: str) -> FileResponse:
    path = RUNS_DIR / run_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Missing artifact: {filename}")
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# What: Local sample-data helper endpoint.
# Purpose: Supports quick internal testing by copying the checked-in sample files into an API run.
@app.post("/runs/sample", response_model=RunResponse)
def create_sample_run(
    strategy: Strategy = "ortools_precedence",
    model: str = "gpt-5.4-mini",
    use_openai: bool = False,
) -> RunResponse:
    run_id = uuid.uuid4().hex
    run_dir = RUNS_DIR / run_id
    data_dir = run_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    source_dir = Path("data")
    sample_csvs = list(source_dir.glob("*.csv"))
    if len(sample_csvs) < 4:
        raise HTTPException(status_code=500, detail="Expected at least four sample CSV files in data/")
    for source_path in sample_csvs:
        shutil.copyfile(source_path, data_dir / source_path.name)

    reasoning_client = None
    if use_openai:
        from openai_reasoning_client import OpenAIReasoningClient

        reasoning_client = OpenAIReasoningClient()

    agent = PlanningSchedulingAgent(data_dir=data_dir, reasoning_client=reasoning_client, model=model)
    result = agent.solve(
        strategy=strategy,
        output_path=run_dir / "agent_middle_schedule.csv",
        report_path=run_dir / "agent_schedule_report.html",
    )
    write_findings(result, run_dir / "agent_findings.txt")
    write_timing_divergences(result.analysis.divergences, run_dir / "agent_timing_divergences.csv")

    return RunResponse(
        run_id=run_id,
        strategy=strategy,
        model=model if use_openai else "offline",
        report_url=_public_url(f"/runs/{run_id}/report.html"),
        schedule_url=_public_url(f"/runs/{run_id}/schedule.csv"),
        findings_url=_public_url(f"/runs/{run_id}/findings"),
        divergences_url=_public_url(f"/runs/{run_id}/divergences.csv"),
        findings=result.analysis.findings,
    )
