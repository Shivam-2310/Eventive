from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.domain import admin_service
from app.domain.ingestion import csv_importer, json_importer
from app.infra.db import SessionLocal, get_db
from app.models.admin import IngestionJob

router = APIRouter(prefix="/ingest", tags=["ingest"])


def _new_job(db: Session, source_type: str, filename: str | None) -> IngestionJob:
    job = IngestionJob(source_type=source_type, filename=filename, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _run_job(job_id: int, source_type: str, content: bytes) -> None:
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if not job:
            return
        job.status = "running"
        db.commit()
        try:
            if source_type == "events_csv":
                stats = csv_importer.import_events_csv(db, content)
            elif source_type == "speakers_csv":
                stats = csv_importer.import_speakers_csv(db, content)
            elif source_type == "json":
                stats = json_importer.import_json_bundle(db, content)
            else:
                raise ValueError(f"unknown source_type: {source_type}")
            job.status = "success"
            job.stats = json.dumps(stats)
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:500]
        finally:
            job.finished_at = datetime.utcnow()
            db.commit()
            admin_service.log_admin_action(
                db,
                actor_user_id=None,
                action="ingest_run",
                target_type="ingestion_job",
                target_id=job.id,
                payload={"source_type": source_type, "status": job.status},
            )
    finally:
        db.close()


def _serialize(job: IngestionJob) -> dict:
    stats = None
    if job.stats:
        try:
            stats = json.loads(job.stats)
        except Exception:
            stats = None
    return {
        "id": job.id,
        "source_type": job.source_type,
        "filename": job.filename,
        "status": job.status,
        "stats": stats,
        "error": job.error,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_events_csv(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expected .csv")
    content = await file.read()
    job = _new_job(db, "events_csv", file.filename)
    background.add_task(_run_job, job.id, "events_csv", content)
    return {"job_id": job.id, "status": job.status}


@router.post("/speakers", status_code=status.HTTP_202_ACCEPTED)
async def ingest_speakers_csv(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expected .csv")
    content = await file.read()
    job = _new_job(db, "speakers_csv", file.filename)
    background.add_task(_run_job, job.id, "speakers_csv", content)
    return {"job_id": job.id, "status": job.status}


@router.post("/json", status_code=status.HTTP_202_ACCEPTED)
async def ingest_json_bundle(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    job = _new_job(db, "json", file.filename)
    background.add_task(_run_job, job.id, "json", content)
    return {"job_id": job.id, "status": job.status}


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)) -> list[dict]:
    from sqlalchemy import select

    rows = list(db.execute(select(IngestionJob).order_by(IngestionJob.id.desc()).limit(50)).scalars().all())
    return [_serialize(r) for r in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(IngestionJob, job_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return _serialize(row)
