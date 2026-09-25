"""StudyPilot API - AI study planner for college students."""
from __future__ import annotations

import io
import logging
import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import ai_features, llm
from .models import (
    CoachRequest,
    CoachResponse,
    ExplainRequest,
    ExplainResponse,
    ParsedSyllabus,
    PlanRequest,
    PlanResponse,
    QuizRequest,
    QuizResponse,
    SyllabusText,
)
from .scheduler import build_plan

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="StudyPilot API",
    version="1.0.0",
    description="Turns a syllabus + exam dates into an adaptive, spaced-repetition study plan.",
)

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ai": llm.enabled(), "model": llm.model_name() if llm.enabled() else None}


@app.post("/api/syllabus/parse", response_model=ParsedSyllabus)
async def parse_syllabus(body: SyllabusText) -> ParsedSyllabus:
    subjects, source = await ai_features.parse_syllabus(body.text, date.today())
    if not subjects:
        raise HTTPException(422, "Couldn't find any topics. Put one subject per line with topics as bullets or comma-separated.")
    return ParsedSyllabus(subjects=subjects, source=source)


@app.post("/api/syllabus/upload", response_model=ParsedSyllabus)
async def upload_syllabus(file: UploadFile = File(...)) -> ParsedSyllabus:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 8 MB)")
    name = (file.filename or "").lower()
    if name.endswith(".pdf") or raw[:4] == b"%PDF":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:30])
        except Exception as e:  # noqa: BLE001 - any parse failure is a user error here
            raise HTTPException(422, f"Couldn't read that PDF: {e}") from e
    else:
        text = raw.decode("utf-8", errors="ignore")
    if len(text.strip()) < 3:
        raise HTTPException(422, "No text found in the file (scanned PDFs aren't supported yet).")
    subjects, source = await ai_features.parse_syllabus(text[:40_000], date.today())
    if not subjects:
        raise HTTPException(422, "Couldn't find any topics in that file.")
    return ParsedSyllabus(subjects=subjects, source=source)


@app.post("/api/plan", response_model=PlanResponse)
def plan(req: PlanRequest) -> PlanResponse:
    return build_plan(req)


@app.post("/api/quiz", response_model=QuizResponse)
async def quiz(req: QuizRequest) -> QuizResponse:
    questions, source = await ai_features.make_quiz(req.subject, req.topic, req.mastery, req.num_questions)
    return QuizResponse(subject=req.subject, topic=req.topic, questions=questions, source=source)


@app.post("/api/explain", response_model=ExplainResponse)
async def explain(req: ExplainRequest) -> ExplainResponse:
    md, source = await ai_features.explain_topic(req.subject, req.topic, req.question, req.mastery)
    return ExplainResponse(markdown=md, source=source)


@app.post("/api/coach", response_model=CoachResponse)
async def coach(req: CoachRequest) -> CoachResponse:
    msg, source = await ai_features.coach_message(req)
    return CoachResponse(message=msg, source=source)


# Serve the built React app (single-service deploy). Skipped in dev if not built.
DIST = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = (DIST / full_path).resolve()
        if full_path and candidate.is_file() and DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
