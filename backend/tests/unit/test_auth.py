"""
Tests de autenticacion JWT — AUTH-01, AUTH-02, AUTH-03.

Usa PyJWT directamente para verificar tokens (mismo algoritmo que auth.py).
No requiere DB real — las funciones de auth.py son puras o mockeables.
"""
from datetime import timedelta

import jwt
import pytest
from pwdlib import PasswordHash

# Importar solo despues de que conftest inyecta env vars (autouse fixture)


def test_create_access_token_returns_decodable_jwt(valid_token):
    """AUTH-01/02: token creado por create_access_token es decodificable."""
    from app.core.auth import ALGORITHM
    from app.core.config import settings
    payload = jwt.decode(
        valid_token,
        settings.SECRET_KEY.get_secret_value(),
        algorithms=[ALGORITHM],
    )
    assert payload["sub"] == "admin_test"
    assert "exp" in payload


def test_token_expiry_raises(set_test_env_vars):
    """AUTH-02: token expirado lanza ExpiredSignatureError."""
    from app.core.auth import create_access_token, ALGORITHM
    from app.core.config import settings
    expired_token = create_access_token("admin", expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.exceptions.ExpiredSignatureError):
        jwt.decode(
            expired_token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[ALGORITHM],
        )


def test_verify_password_correct(set_test_env_vars):
    """AUTH-01: password correcto pasa verificacion Argon2."""
    from app.core.auth import password_hash
    hashed = password_hash.hash("Password123!")
    assert password_hash.verify("Password123!", hashed) is True


def test_verify_password_wrong(set_test_env_vars):
    """AUTH-01: password incorrecto falla verificacion."""
    from app.core.auth import password_hash
    hashed = password_hash.hash("Password123!")
    assert password_hash.verify("WrongPassword", hashed) is False


def test_user_model_tablename(set_test_env_vars):
    """User model tiene tablename correcto."""
    from app.models.user import User
    assert User.__tablename__ == "users"


def test_user_model_has_required_fields(set_test_env_vars):
    """User model tiene columnas: id, username, hashed_password, is_active, created_at."""
    from app.models.user import User
    columns = {c.name for c in User.__table__.columns}
    assert {"id", "username", "hashed_password", "is_active", "created_at"}.issubset(columns)


def test_user_username_is_unique(set_test_env_vars):
    """User.username tiene constraint UNIQUE."""
    from app.models.user import User
    username_col = User.__table__.c["username"]
    assert username_col.unique is True


def test_access_token_expire_minutes_setting(set_test_env_vars):
    """AUTH-02: ACCESS_TOKEN_EXPIRE_MINUTES disponible en Settings con default 1440."""
    from app.core.config import settings
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 1440


def test_algorithm_is_hs256(set_test_env_vars):
    """Algoritmo JWT es HS256 (no RS256 — no se necesita clave publica en v1)."""
    from app.core.auth import ALGORITHM
    assert ALGORITHM == "HS256"


def test_oauth2_scheme_token_url(set_test_env_vars):
    """oauth2_scheme.tokenUrl apunta a /auth/login para OpenAPI docs correctos."""
    from app.core.auth import oauth2_scheme
    assert oauth2_scheme.model.flows.password.tokenUrl == "/auth/login"
