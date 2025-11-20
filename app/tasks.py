import csv
import sys
import os
import logging
from datetime import datetime
from typing import Callable

from .database import SessionLocal
from . import models
from .webhooks import dispatch_event

logger = logging.getLogger("app.tasks")
BATCH_SIZE = int(os.getenv("IMPORT_BATCH_SIZE", "2000"))
csv.field_size_limit(sys.maxsize)

def _update_job(db, job_id: str, **kwargs):
    try:
        job = db.get(models.JobProgress, job_id)
        if not job:
            job = models.JobProgress(id=job_id)
            db.add(job)
        for k, v in kwargs.items():
            setattr(job, k, v)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(str(e))

def _process_row(db, row: dict):
    sku = (row.get("sku") or "").strip()
    if not sku:
        return False
    name = (row.get("name") or sku).strip()
    description = (row.get("description") or "").strip()
    try:
        sku_lower = sku.lower()
        existing = db.query(models.Product).filter(models.Product.sku_lower == sku_lower).one_or_none()
        if existing:
            existing.sku = sku
            existing.sku_lower = sku_lower
            existing.name = name
            existing.description = description
            existing.updated_at = datetime.utcnow()
        else:
            p = models.Product(
                sku=sku,
                sku_lower=sku_lower,
                name=name,
                description=description,
                active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(p)
        return True
    except Exception as e:
        logger.error(str(e))
        return False

# Local background importer (FastAPI runtime)
def import_csv_background(job_id: str, csv_path: str):
    db = SessionLocal()
    try:
        _update_job(db, job_id, stage="parsing", status="running", started_at=datetime.utcnow())
        # Count rows first to show total
        total = 0
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            headers = [h.strip().lower() for h in (reader.fieldnames or [])]
            if "sku" not in headers:
                _update_job(db, job_id, stage="failed", status="failed", error_message="CSV must include header 'sku'", finished_at=datetime.utcnow())
                return
            for _ in reader:
                total += 1
        _update_job(db, job_id, total_rows=total, stage="importing")

        processed = 0
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            batch = 0
            for row in reader:
                ok = _process_row(db, row)
                if ok:
                    batch += 1
                    processed += 1
                if batch >= BATCH_SIZE:
                    try:
                        db.commit()
                    except Exception as e:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        _update_job(db, job_id, stage="failed", status="failed", error_message=str(e), finished_at=datetime.utcnow())
                        logger.error(str(e))
                        return
                    batch = 0
                    _update_job(db, job_id, processed_rows=processed)
            if batch:
                try:
                    db.commit()
                except Exception as e:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    _update_job(db, job_id, stage="failed", status="failed", error_message=str(e), finished_at=datetime.utcnow())
                    logger.error(str(e))
                    return
        _update_job(db, job_id, processed_rows=processed, stage="completed", status="completed", finished_at=datetime.utcnow())
        # Notify webhooks
        dispatch_event(db, "import.completed", {"job_id": job_id, "processed": processed, "total": total})
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        _update_job(db, job_id, stage="failed", status="failed", error_message=str(e), finished_at=datetime.utcnow())
        logger.error(str(e))
    finally:
        db.close()

# Celery task wrapper
try:
    from .celery_app import celery
    @celery.task(name="import_csv_task")
    def import_csv_task(job_id: str, csv_path: str):
        import_csv_background(job_id, csv_path)
except Exception:
    # Celery not available in local preview
    pass