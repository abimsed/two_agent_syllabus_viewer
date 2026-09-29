from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent_backend import TwoAgentRunner
from pdf_pipeline import process_pdf


BASE = Path(__file__).resolve().parent

UPLOAD_DIR = BASE / "data" / "uploads"
RENDER_DIR = BASE / "data" / "rendered"

# NEW:
# Completed syllabus analyses will be saved here.
RESULTS_DIR = BASE / "data" / "results"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RENDER_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


app = FastAPI(title="Two-Agent Syllabus Lens")

app.mount(
    "/static",
    StaticFiles(directory=BASE / "static"),
    name="static",
)

templates = Jinja2Templates(
    directory=BASE / "templates"
)


# In-memory prototype stores.
# Replace with SQLite/Redis for multi-user deployment.
DOCUMENTS = {}
JOBS = {}

JOBS_LOCK = threading.Lock()


def update_job(job_id: str, **changes):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(changes)


def save_analysis_result(payload: dict) -> Path:
    """
    Save the complete syllabus analysis to a JSON file.

    This includes:
    - detected syllabus topics
    - PDF anchor information
    - Abi's reactions
    - Tim's reactions
    - concern categories
    - concern severity
    - confidence
    - immediate next steps
    """

    document_id = payload["document_id"]

    output_path = (
        RESULTS_DIR
        / f"{document_id}_syllabus_analysis.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return output_path


def run_analysis_job(
    job_id: str,
    local_path: Path,
):
    try:

        def pdf_progress(
            stage: str,
            progress: int,
            detail: str,
        ):
            update_job(
                job_id,
                status="running",
                stage=stage,
                detail=detail,
                progress=progress,
            )

        processed = process_pdf(
            local_path,
            RENDER_DIR,
            progress_callback=pdf_progress,
        )

        update_job(
            job_id,
            status="running",
            stage="Loading student agents",
            detail="Initializing Abi and Tim",
            progress=32,
        )

        runner = TwoAgentRunner()

        mode = (
            "mock"
            if runner.mock
            else "live"
        )

        total_calls = max(
            1,
            len(processed.topic_matches) * 2,
        )

        def agent_progress(
            agent: str,
            topic: str,
            completed: int,
            total: int,
        ):
            total = max(
                1,
                total or total_calls,
            )

            # Agent generation owns the
            # 34%-94% portion of the progress bar.
            pct = 34 + round(
                (completed / total) * 60
            )

            if completed < total:
                detail = (
                    f"{agent} is reading: {topic}"
                )
            else:
                detail = (
                    f"Completed {completed} of "
                    f"{total} student reactions"
                )

            update_job(
                job_id,
                status="running",
                stage="Simulating student reactions",
                detail=detail,
                progress=min(pct, 94),
                reactions_completed=completed,
                reactions_total=total,
            )

        reactions = runner.run_document(
            processed.topic_matches,
            progress_callback=agent_progress,
        )

        update_job(
            job_id,
            status="running",
            stage="Preparing results",
            detail=(
                "Connecting reactions "
                "to their PDF anchors"
            ),
            progress=97,
        )

        payload = {
            "document_id": (
                processed.document_id
            ),

            "filename": (
                JOBS[job_id].get(
                    "filename",
                    processed.filename,
                )
            ),

            "page_sizes": (
                processed.page_sizes
            ),

            "page_count": (
                len(
                    processed.rendered_pages
                )
            ),

            "topics": reactions,

            "agent_mode": mode,
        }

        # Keep the result available to the frontend.
        DOCUMENTS[
            processed.document_id
        ] = payload

        # NEW:
        # Save the complete result permanently to JSON.
        result_path = save_analysis_result(
            payload
        )

        update_job(
            job_id,
            status="complete",
            stage="Analysis complete",
            detail=(
                f"{len(reactions)} syllabus "
                f"concepts analyzed by Abi and Tim"
            ),
            progress=100,
            document_id=processed.document_id,

            # NEW:
            # Useful for debugging / future analysis.
            result_file=str(result_path),
        )

    except Exception as exc:
        update_job(
            job_id,
            status="error",
            stage="Analysis stopped",
            detail=str(exc),
            error=f"Analysis failed: {exc}",
        )


@app.get(
    "/",
    response_class=HTMLResponse,
)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
        },
    )


@app.post("/api/upload")
async def upload_pdf(
    file: UploadFile = File(...),
):
    if (
        not file.filename
        or not file.filename.lower().endswith(
            ".pdf"
        )
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Please upload a PDF syllabus."
            ),
        )

    job_id = uuid.uuid4().hex[:12]

    safe_name = Path(
        file.filename
    ).name

    local_path = (
        UPLOAD_DIR
        / f"{job_id}_{safe_name}"
    )

    with local_path.open(
        "wb"
    ) as out:
        shutil.copyfileobj(
            file.file,
            out,
        )

    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "stage": "Upload complete",
            "detail": (
                "Starting syllabus analysis"
            ),
            "progress": 3,
            "filename": safe_name,
            "reactions_completed": 0,
            "reactions_total": 0,
        }

    worker = threading.Thread(
        target=run_analysis_job,
        args=(
            job_id,
            local_path,
        ),
        daemon=True,
    )

    worker.start()

    return JSONResponse(
        {
            "job_id": job_id,
        },
        status_code=202,
    )


@app.get("/api/job/{job_id}")
def get_job(
    job_id: str,
):
    with JOBS_LOCK:
        job = JOBS.get(
            job_id
        )

        if not job:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Analysis job not found."
                ),
            )

        return dict(job)


@app.get(
    "/api/document/{document_id}"
)
def get_document(
    document_id: str,
):
    if document_id not in DOCUMENTS:
        raise HTTPException(
            status_code=404,
            detail=(
                "Document not found "
                "in this prototype session."
            ),
        )

    return DOCUMENTS[
        document_id
    ]


@app.get(
    "/rendered/"
    "{document_id}/"
    "{page_number}.png"
)
def rendered_page(
    document_id: str,
    page_number: int,
):
    path = (
        RENDER_DIR
        / document_id
        / f"page_{page_number}.png"
    )

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Rendered page not found."
            ),
        )

    return FileResponse(
        path,
        media_type="image/png",
    )