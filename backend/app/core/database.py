"""
Configuracion del engine SQLAlchemy async para PostgreSQL via asyncpg.

IMPORTANTE: Railway provee DATABASE_URL con formato postgresql://...
asyncpg requiere postgresql+asyncpg://... — el reemplazo se hace aqui.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _build_async_url(raw_url: str) -> str:
    """Convierte postgresql:// a postgresql+asyncpg:// para asyncpg."""
    return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)


engine = create_async_engine(
    _build_async_url(settings.DATABASE_URL),
    echo=False,  # True solo en desarrollo local para ver SQL queries
    pool_pre_ping=True,  # Verifica conexion antes de usarla (evita errores con conexiones muertas)
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: inyecta sesion async de PostgreSQL.

    Uso:
        @router.get("/devices")
        async def list_devices(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
