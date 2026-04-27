"""
Dependencias FastAPI reutilizables para BEEPYRED NOC.

Importar CurrentUser en cualquier router para proteger endpoints:
    @router.get("/protected")
    async def endpoint(user: CurrentUser) -> dict:
        return {"username": user.username}
"""
from typing import Annotated
from fastapi import Depends
from app.core.auth import get_current_active_user
from app.models.user import User

# Alias tipado para usar en Depends sin repetir la importacion
CurrentUser = Annotated[User, Depends(get_current_active_user)]
