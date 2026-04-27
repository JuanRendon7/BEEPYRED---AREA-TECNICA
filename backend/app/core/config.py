"""
Configuracion centralizada de BEEPYRED NOC.

Todas las credenciales vienen de variables de entorno — NUNCA hardcodeadas.
Railway provee automaticamente: DATABASE_URL, REDIS_URL, PORT.
Las demas deben configurarse manualmente en Railway dashboard.

IMPORTANTE: Nunca loggear settings.FERNET_KEY ni settings.DATABASE_URL.
"""
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Ignorar variables extra del entorno (Railway inyecta muchas)
        extra="ignore",
    )

    # -- Base de datos ---------------------------------------------------------------
    # Railway provee DATABASE_URL automaticamente al agregar el addon PostgreSQL
    # Formato Railway: postgresql://user:pass@host:5432/dbname
    # Para asyncpg: reemplazar postgresql:// con postgresql+asyncpg:// en database.py
    DATABASE_URL: str

    # -- Redis -----------------------------------------------------------------------
    # Railway provee REDIS_URL automaticamente al agregar el addon Redis
    REDIS_URL: str

    # -- Seguridad -------------------------------------------------------------------
    # SECRET_KEY: usado para JWT en Phase 2. Generar con:
    #   python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: SecretStr

    # FERNET_KEY: cifrado de credenciales de equipos en DB. Generar con:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # CRITICO: si se pierde, todas las credenciales almacenadas son irrecuperables.
    FERNET_KEY: SecretStr

    # -- Tailscale VPN (INFRA-01) ----------------------------------------------------
    # Auth key efimera de Tailscale — generar en tailscale.com/admin/settings/keys
    # Solo el servicio worker necesita esta variable.
    # DECISION BLOQUEADA: Tailscale SaaS confirmado por el tecnico de BEEPYRED.
    TAILSCALE_AUTH_KEY: str = ""

    # -- Telegram (Phase 3 — incluir ahora para no redesplegar) ----------------------
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # -- Polling (Phase 2) -----------------------------------------------------------
    POLL_INTERVAL_SECONDS: int = 60
    MAX_CONCURRENT_CONNECTIONS: int = 50
    DEVICE_TIMEOUT_SECONDS: int = 10

    # -- Mikrotik RouterOS API (Phase 3) -----------------------------------------
    MIKROTIK_API_PORT: int = 8728

    # -- Umbrales de alerta (Phase 3) ------------------------------------------------
    CPU_ALERT_THRESHOLD_PCT: float = 90.0
    ONU_SIGNAL_MIN_DBM: float = -28.0
    CONSECUTIVE_FAILURES_THRESHOLD: int = 3
    # Tiempo de espera (segundos) antes de enviar alerta DOWN — anti-flapping debounce
    # Si el equipo se recupera dentro de este ventana, la alerta se suprime (ALERT-04)
    ALERT_DEBOUNCE_SECONDS: int = 120

    # -- Auth (Phase 2) --------------------------------------------------------------
    # Duracion del JWT. 1440 = 24 horas. El tecnico no hace login todos los dias.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    # Usuario admin inicial — creado por scripts/seed_admin.py en pre-deploy
    ADMIN_USERNAME: str = "admin"
    # SecretStr con default "changeme" — seed_admin.py valida que no sea "changeme" en produccion
    ADMIN_PASSWORD: SecretStr = SecretStr("changeme")

    # -- Railway auto-sets PORT ------------------------------------------------------
    PORT: int = 8000

    # -- Deploy (DEPLOY-02) — dominio personalizado BEEPYRED -------------------------
    # La configuracion DNS real se completa en Phase 6 en el Railway dashboard.
    # Esta variable documenta el dominio objetivo para referencia.
    CUSTOM_DOMAIN: str = ""


settings = Settings()
