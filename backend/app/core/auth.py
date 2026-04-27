"""
Logica de autenticacion JWT para BEEPYRED NOC.

Usa PyJWT + pwdlib[argon2] — la pila oficial de FastAPI desde May 2024.
NO usa python-jose (abandonado) ni passlib (sin mantenimiento).

Refs:
- https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- PyJWT == import jwt (no from jose import jwt)
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()  # Argon2 por defecto
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(sub: str, expires_delta: timedelta | None = None) -> str:
    """Crea JWT firmado con SECRET_KEY. sub = username del tecnico."""
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": sub, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY.get_secret_value(), algorithm=ALGORITHM)


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """Busca usuario en DB por username. Retorna None si no existe."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependencia FastAPI: decodifica JWT y retorna el User activo.

    Lanza 401 si el token es invalido, expirado, o el usuario no existe.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[ALGORITHM],
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    user = await get_user_by_username(db, username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependencia FastAPI: valida que el usuario esta activo (is_active=True)."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo",
        )
    return current_user
