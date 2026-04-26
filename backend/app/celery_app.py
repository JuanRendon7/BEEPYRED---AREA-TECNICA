from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "beepyred_noc",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.maintenance"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Bogota",
    enable_utc=True,
    # Celery beat: schedule de mantenimiento (Phase 2+)
    beat_schedule={},
)
