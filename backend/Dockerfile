# --- Stage base: compartido por web y worker -------------------------------------------
FROM python:3.12-slim AS base

WORKDIR /app

# Dependencias del sistema minimas
RUN apt-get update && apt-get install -y \
    curl \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# --- Stage web: FastAPI + Uvicorn -------------------------------------------------------
FROM base AS web
EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]

# --- Stage worker: Celery + Tailscale userspace VPN -------------------------------------
FROM base AS worker

# Instalar Tailscale — userspace mode (TS_USERSPACE=1), no requiere NET_ADMIN
# DECISION BLOQUEADA: Tailscale SaaS confirmado. Auth via TAILSCALE_AUTH_KEY env var.
RUN curl -fsSL https://tailscale.com/install.sh | sh

COPY scripts/start-worker.sh /start-worker.sh
RUN chmod +x /start-worker.sh

CMD ["/start-worker.sh"]

# --- Stage beat: Celery beat scheduler --------------------------------------------------
FROM base AS beat
CMD ["celery", "-A", "app.celery_app", "beat", "--loglevel=info", "--scheduler", "celery.beat:PersistentScheduler"]
