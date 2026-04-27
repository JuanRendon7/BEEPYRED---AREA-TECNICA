"""
Servicio de alertas Telegram para BEEPYRED NOC.

ALERT-02: Envia mensaje DOWN con nombre, IP, sitio, timestamp.
ALERT-03: Envia mensaje UP con duracion de la caida.

Patron outbound-only — sin webhook. El bot envia mensajes pero no recibe.
Usar `async with Bot(token) as bot:` — inicializa/cierra la sesion HTTP correctamente.
Parse mode HTML: mas predecible que Markdown para mensajes programaticos.

SEGURIDAD (T-3-07): No loggear TELEGRAM_BOT_TOKEN bajo ninguna circunstancia.
Guard: si token o chat_id vacios, loggea advertencia y retorna sin error —
el sistema no debe crashear si Telegram no esta configurado.
"""
import logging
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Seam de inyeccion para tests — permite mockear la clase Bot sin parchear
# la libreria telegram directamente en el import del modulo
# ---------------------------------------------------------------------------

def _get_bot_class():
    """
    Retorna la clase Bot de python-telegram-bot.
    Extraido en funcion para facilitar mocking en tests unitarios.
    """
    from telegram import Bot  # noqa: PLC0415 — import diferido intencional
    return Bot


# ---------------------------------------------------------------------------
# Formateadores de mensajes (funciones puras — sin dependencias externas)
# ---------------------------------------------------------------------------

def format_down_message(
    device_name: str,
    ip: str,
    site: str | None,
    timestamp: datetime,
) -> str:
    """
    ALERT-02: Formato HTML para mensaje de equipo caido.
    Incluye nombre, IP en etiqueta code, sitio y timestamp UTC.

    Retorna string HTML listo para parse_mode='HTML' de Telegram.
    """
    ts = timestamp.strftime("%d/%m/%Y %H:%M:%S")
    site_str = site or "Sin sitio"
    return (
        f"\U0001f534 <b>EQUIPO CAIDO</b>\n"
        f"<b>Nombre:</b> {device_name}\n"
        f"<b>IP:</b> <code>{ip}</code>\n"
        f"<b>Sitio:</b> {site_str}\n"
        f"<b>Hora:</b> {ts} UTC"
    )


def format_up_message(
    device_name: str,
    ip: str,
    site: str | None,
    duration_seconds: int,
) -> str:
    """
    ALERT-03: Formato HTML para mensaje de equipo recuperado.
    Incluye nombre, IP, sitio y duracion de la caida formateada.

    Formato de duracion:
    - Con horas:    "Xh Xm Xs"
    - Sin horas:    "Xm Xs"

    Retorna string HTML listo para parse_mode='HTML' de Telegram.
    """
    mins, secs = divmod(duration_seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        duration_str = f"{hours}h {mins}m {secs}s"
    else:
        duration_str = f"{mins}m {secs}s"

    site_str = site or "Sin sitio"
    return (
        f"\U0001f7e2 <b>EQUIPO RECUPERADO</b>\n"
        f"<b>Nombre:</b> {device_name}\n"
        f"<b>IP:</b> <code>{ip}</code>\n"
        f"<b>Sitio:</b> {site_str}\n"
        f"<b>Duracion caida:</b> {duration_str}"
    )


# ---------------------------------------------------------------------------
# Envio de alerta
# ---------------------------------------------------------------------------

async def send_telegram_alert(text: str) -> None:
    """
    Envia un mensaje al chat configurado en TELEGRAM_CHAT_ID.

    Guard (T-3-07): si TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID estan vacios,
    loggea advertencia y retorna sin error — no bloquea el ciclo de alertas.
    El token NUNCA se loggea.

    Usa `async with Bot(token) as bot:` para inicializar la sesion HTTP
    interna de python-telegram-bot v21 correctamente.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.warning(
            "Telegram alert suppressed: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured"
        )
        return

    Bot = _get_bot_class()
    async with Bot(token=token) as bot:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
        )
