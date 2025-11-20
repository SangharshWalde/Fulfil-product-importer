import time
import logging
import httpx
from . import models

TIMEOUT_SECS = 10
logger = logging.getLogger("app.webhooks")

def dispatch_event(db, event: str, payload: dict):
    items = db.query(models.Webhook).filter(models.Webhook.enabled == True, models.Webhook.event == event).all()
    for w in items:
        try:
            start = time.time()
            r = httpx.post(w.url, json={"event": event, "payload": payload}, timeout=TIMEOUT_SECS)
            w.last_status_code = r.status_code
            w.last_response_ms = int((time.time() - start) * 1000)
            try:
                db.commit()
            except Exception as e:
                try:
                    db.rollback()
                except Exception:
                    pass
                logger.error(str(e))
        except Exception as e:
            w.last_status_code = -1
            w.last_response_ms = None
            try:
                db.commit()
            except Exception as e2:
                try:
                    db.rollback()
                except Exception:
                    pass
                logger.error(str(e2))


def test_webhook(w: models.Webhook):
    try:
        start = time.time()
        r = httpx.post(w.url, json={"event": w.event, "payload": {"test": True}}, timeout=TIMEOUT_SECS)
        w.last_status_code = r.status_code
        w.last_response_ms = int((time.time() - start) * 1000)
        return {"status_code": r.status_code, "response_ms": w.last_response_ms}
    except Exception as e:
        w.last_status_code = -1
        w.last_response_ms = None
        logger.error(str(e))
        return {"error": str(e)}