"""
Endpoints de autenticacion: POST /auth/login, GET /auth/me.

POST /auth/login: recibe form OAuth2PasswordRequestForm (username + password),
    retorna {"access_token": "...", "token_type": "bearer"}.
GET /auth/me: retorna datos del usuario autenticado (requiere Bearer token).

SEGURIDAD — timing attack:
    Si el usuario no existe, igualmente se llama password_hash.verify() con
    un hash dummy para que el tiempo de respuesta sea identico al caso de
    password incorrecto. Esto previene enumeracion de usuarios.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    create_access_token,
    get_user_by_username,
    password_hash,
)
from app.core.database import get_db
from app.api.deps import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash dummy para timing attack mitigation — generado una vez al startup
_DUMMY_HASH = password_hash.hash("dummy_password_for_timing_protection")


@router.post("/login")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    AUTH-01: Iniciar sesion con username y password.
    Retorna JWT Bearer token con expiracion configurada en ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    user = await get_user_by_username(db, form_data.username)

    # Mitigacion timing attack: verificar siempre, incluso si user no existe
    if user is None:
        password_hash.verify(form_data.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contrasena incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not password_hash.verify(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contrasena incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo",
        )

    token = create_access_token(sub=user.username)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
async def get_me(current_user: CurrentUser) -> dict:
    """
    AUTH-03: Retorna datos del usuario autenticado.
    Requiere Bearer token valido. Retorna 401 sin token (protegido via CurrentUser dep).
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "is_active": current_user.is_active,
    }
