"""
Script de seed del usuario admin inicial para BEEPYRED NOC.

Uso (como Railway pre-deploy command o primer deploy):
    cd backend && python scripts/seed_admin.py

Variables de entorno requeridas:
    DATABASE_URL   — Railway PostgreSQL addon
    SECRET_KEY     — para JWT (Settings lo requiere)
    FERNET_KEY     — para credenciales (Settings lo requiere)
    ADMIN_USERNAME — usuario del tecnico (default: "admin")
    ADMIN_PASSWORD — contrasena del tecnico (OBLIGATORIO cambiar)

SEGURIDAD: el script verifica que ADMIN_PASSWORD != "changeme" en produccion.
"""
import asyncio
import sys

from app.core.config import settings
from app.core.auth import password_hash, get_user_by_username
from app.core.database import AsyncSessionLocal
from app.models.user import User


async def seed_admin() -> None:
    admin_password = settings.ADMIN_PASSWORD.get_secret_value()

    # Verificar que la contrasena fue cambiada del default
    if admin_password == "changeme":
        print("ERROR: ADMIN_PASSWORD no puede ser 'changeme' en produccion.")
        print("Configura ADMIN_PASSWORD en Railway dashboard o .env")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        existing = await get_user_by_username(db, settings.ADMIN_USERNAME)
        if existing:
            print(f"Usuario '{settings.ADMIN_USERNAME}' ya existe — nada que hacer.")
            return

        hashed = password_hash.hash(admin_password)
        user = User(
            username=settings.ADMIN_USERNAME,
            hashed_password=hashed,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        print(f"Usuario '{settings.ADMIN_USERNAME}' creado exitosamente.")


if __name__ == "__main__":
    asyncio.run(seed_admin())
