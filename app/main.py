import os
import shutil
import uuid
import logging
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import Generator

from .database import get_db, init_db
from . import models
from . import tasks
from .schemas import ProductCreate, ProductUpdate, ProductOut, PaginatedProducts, WebhookCreate, WebhookUpdate, WebhookOut, JobStatus
from .webhooks import test_webhook

APP_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Acme Product Importer")
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")

# Initialize DB on startup
@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def index():
    index_path = os.path.join(APP_DIR, "static", "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

# --------------------- Product CRUD ---------------------
@app.get("/products", response_model=PaginatedProducts)
def list_products(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sku: str | None = None,
    name: str | None = None,
    description: str | None = None,
    active: bool | None = None,
):
    q = db.query(models.Product)
    if sku:
        q = q.filter(models.Product.sku_lower == sku.lower())
    if name:
        q = q.filter(models.Product.name.ilike(f"%{name}%"))
    if description:
        q = q.filter(models.Product.description.ilike(f"%{description}%"))
    if active is not None:
        q = q.filter(models.Product.active == active)
    total = q.count()
    items = q.order_by(models.Product.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedProducts(total=total, page=page, page_size=page_size, items=[ProductOut.model_validate(i) for i in items])

@app.post("/products", response_model=ProductOut)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    sku_lower = payload.sku.lower()
    existing = db.query(models.Product).filter(models.Product.sku_lower == sku_lower).one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists (case-insensitive)")
    p = models.Product(
        sku=payload.sku,
        sku_lower=sku_lower,
        name=payload.name,
        description=payload.description or "",
        active=payload.active if payload.active is not None else True,
    )
    try:
        db.add(p)
        db.commit()
        db.refresh(p)
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logging.getLogger("app.main").error(str(e))
        raise HTTPException(status_code=500, detail="Database error")
    return ProductOut.model_validate(p)

@app.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    p = db.get(models.Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.sku and payload.sku.lower() != p.sku_lower:
        if db.query(models.Product).filter(models.Product.sku_lower == payload.sku.lower()).first():
            raise HTTPException(status_code=400, detail="SKU already exists (case-insensitive)")
        p.sku = payload.sku
        p.sku_lower = payload.sku.lower()
    if payload.name is not None:
        p.name = payload.name
    if payload.description is not None:
        p.description = payload.description
    if payload.active is not None:
        p.active = payload.active
    try:
        db.commit()
        db.refresh(p)
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logging.getLogger("app.main").error(str(e))
        raise HTTPException(status_code=500, detail="Database error")
    return ProductOut.model_validate(p)

@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(models.Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        db.delete(p)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logging.getLogger("app.main").error(str(e))
        raise HTTPException(status_code=500, detail="Database error")
    return {"ok": True}

@app.delete("/products")
def delete_all_products(db: Session = Depends(get_db)):
    try:
        db.query(models.Product).delete()
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logging.getLogger("app.main").error(str(e))
        raise HTTPException(status_code=500, detail="Database error")
    return {"ok": True}

# --------------------- Upload & Progress ---------------------
@app.post("/upload", response_model=JobStatus)
def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Save uploaded file to disk
    job_id = str(uuid.uuid4())
    dest_path = os.path.join(UPLOAD_DIR, f"{job_id}.csv")
    with open(dest_path, "wb") as out:
        try:
            file.file.seek(0)
        except Exception:
            pass
        shutil.copyfileobj(file.file, out)
    # Create job
    job = models.JobProgress(id=job_id, stage="queued", status="queued", processed_rows=0, total_rows=0)
    try:
        db.add(job)
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logging.getLogger("app.main").error(str(e))
        raise HTTPException(status_code=500, detail="Database error")
    # Dispatch background import (Celery-aware, with local fallback)
    use_celery = os.getenv("USE_CELERY", "false").lower() == "true"
    if use_celery:
        from .tasks import import_csv_task
        import_csv_task.delay(job_id, dest_path)
    else:
        tasks.import_csv_background(job_id, dest_path)
    return JobStatus(id=job_id, stage=job.stage, status=job.status, processed_rows=job.processed_rows, total_rows=job.total_rows, error_message=None)

@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.get(models.JobProgress, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(id=job.id, stage=job.stage, status=job.status, processed_rows=job.processed_rows, total_rows=job.total_rows, error_message=job.error_message)

@app.get("/jobs/{job_id}/events")
def stream_job_events(job_id: str, db: Session = Depends(get_db)):
    def event_gen() -> Generator[bytes, None, None]:
        import time
        last = None
        while True:
            job = db.get(models.JobProgress, job_id)
            if not job:
                yield f"data: {JobStatus(id=job_id, stage='unknown', status='unknown', processed_rows=0, total_rows=0).model_dump_json()}\n\n".encode()
                break
            payload = JobStatus(id=job.id, stage=job.stage, status=job.status, processed_rows=job.processed_rows, total_rows=job.total_rows, error_message=job.error_message).model_dump_json()
            if payload != last:
                yield f"data: {payload}\n\n".encode()
                last = payload
            if job.status in ("completed", "failed"):
                break
            time.sleep(0.5)
    return StreamingResponse(event_gen(), media_type="text/event-stream")

# --------------------- Webhooks ---------------------
@app.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(db: Session = Depends(get_db)):
    items = db.query(models.Webhook).order_by(models.Webhook.id.desc()).all()
    return [WebhookOut.model_validate(i) for i in items]

@app.post("/webhooks", response_model=WebhookOut)
def create_webhook(payload: WebhookCreate, db: Session = Depends(get_db)):
    w = models.Webhook(url=payload.url, event=payload.event, enabled=payload.enabled)
    db.add(w)
    db.commit()
    db.refresh(w)
    return WebhookOut.model_validate(w)

@app.put("/webhooks/{webhook_id}", response_model=WebhookOut)
def update_webhook(webhook_id: int, payload: WebhookUpdate, db: Session = Depends(get_db)):
    w = db.get(models.Webhook, webhook_id)
    if not w:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if payload.url is not None:
        w.url = payload.url
    if payload.event is not None:
        w.event = payload.event
    if payload.enabled is not None:
        w.enabled = payload.enabled
    db.commit()
    db.refresh(w)
    return WebhookOut.model_validate(w)

@app.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Webhook, webhook_id)
    if not w:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(w)
    db.commit()
    return {"ok": True}

@app.post("/webhooks/{webhook_id}/test")
def test_webhook_trigger(webhook_id: int, db: Session = Depends(get_db)):
    w = db.get(models.Webhook, webhook_id)
    if not w:
        raise HTTPException(status_code=404, detail="Webhook not found")
    result = test_webhook(w)
    try:
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logging.getLogger("app.main").error(str(e))
        raise HTTPException(status_code=500, detail="Database error")
    return result