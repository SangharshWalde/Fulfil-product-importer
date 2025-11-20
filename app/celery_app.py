import os
from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery = Celery("product_importer", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

@celery.task
def ping():
    return "pong"