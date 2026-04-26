#!/bin/bash
set -e

echo "[start-worker] Iniciando tailscaled en modo userspace..."
# TS_USERSPACE=1 no requiere NET_ADMIN — compatible con Railway
# DECISIÓN BLOQUEADA: Tailscale userspace confirmado por el técnico de BEEPYRED
tailscaled --tun=userspace-networking --socks5-server=localhost:1055 --state=/tmp/tailscale-state &
TAILSCALE_PID=$!

echo "[start-worker] Esperando a que tailscaled arranque..."
sleep 3

echo "[start-worker] Autenticando con Tailscale..."
tailscale up \
  --authkey="${TAILSCALE_AUTH_KEY}" \
  --hostname="beepyred-noc-worker" \
  --accept-routes

echo "[start-worker] Tailscale conectado. Exportando proxy SOCKS5..."
export ALL_PROXY=socks5://localhost:1055
export HTTP_PROXY=socks5://localhost:1055
export HTTPS_PROXY=socks5://localhost:1055

echo "[start-worker] Iniciando Celery worker..."
exec celery -A app.celery_app worker --loglevel=info --concurrency=4
