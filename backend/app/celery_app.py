from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "beepyred_noc",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    # Registrar los modulos de tasks para autodescubrimiento
    # app.tasks.polling: ICMP ping a todos los equipos (Phase 2)
    # app.tasks.maintenance: limpieza de metricas antiguas (Phase 3 — pendiente)
    include=[
        "app.tasks.polling",
        "app.tasks.mikrotik",
        "app.tasks.alerts",
        "app.tasks.maintenance",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Bogota",
    enable_utc=True,
    beat_schedule={
        # POLL-01: ping a todos los equipos cada POLL_INTERVAL_SECONDS (60s)
        # expires previene acumulacion si el ciclo anterior no termino (T-2-21)
        "poll-all-devices": {
            "task": "tasks.poll_all_devices",
            "schedule": settings.POLL_INTERVAL_SECONDS,
            "options": {
                # Si el task se retrasa mas de POLL_INTERVAL_SECONDS, descartar
                # para no acumular tareas en cola (evita doble polling)
                "expires": settings.POLL_INTERVAL_SECONDS - 5,
            },
        },
        # MK-01/02: recolectar metricas RouterOS de todos los Mikrotik activos
        "poll-mikrotik-devices": {
            "task": "tasks.poll_all_mikrotik",
            "schedule": settings.POLL_INTERVAL_SECONDS,
            "options": {
                "expires": settings.POLL_INTERVAL_SECONDS - 5,
            },
        },
        # MK-03/INC-04: limpieza diaria de datos historicos > 30 dias (3am hora Colombia)
        "cleanup-old-data": {
            "task": "tasks.cleanup_old_data",
            "schedule": crontab(hour=3, minute=0),  # 3am hora Colombia (UTC-5)
            "options": {"expires": 3600},  # si no se ejecuto en 1h, descartar
        },
    },
)
