"""
Fixtures compartidas para los tests de BEEPYRED NOC Phase 1.

La FERNET_KEY de test es una key valida generada solo para tests.
NO usar esta key en produccion.
"""
import pytest
from cryptography.fernet import Fernet


# Key de test — valida para Fernet pero nunca usada en produccion
TEST_FERNET_KEY = Fernet.generate_key().decode()
TEST_SECRET_KEY = "test_secret_key_only_for_unit_tests_32ch"


@pytest.fixture(autouse=True)
def set_test_env_vars(monkeypatch):
    """
    Inyectar variables de entorno para que Settings no falle en tests unitarios.
    Los tests unitarios no requieren PostgreSQL ni Redis reales.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://testuser:testpass@localhost:5432/testdb")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("FERNET_KEY", TEST_FERNET_KEY)


@pytest.fixture
def fernet_key() -> str:
    """Key Fernet valida para tests de security.py."""
    return TEST_FERNET_KEY


# -- Fixtures de auth (Phase 2) --------------------------------------------------
TEST_ADMIN_USERNAME = "admin_test"
TEST_ADMIN_PASSWORD = "TestPassword123!"


@pytest.fixture
def admin_username() -> str:
    return TEST_ADMIN_USERNAME


@pytest.fixture
def admin_password() -> str:
    return TEST_ADMIN_PASSWORD


@pytest.fixture
def valid_token(set_test_env_vars) -> str:
    """JWT valido firmado con TEST_SECRET_KEY para tests."""
    from app.core.auth import create_access_token
    return create_access_token(TEST_ADMIN_USERNAME)


@pytest.fixture
def auth_headers(valid_token) -> dict:
    """Headers HTTP con Bearer token para tests de endpoints protegidos."""
    return {"Authorization": f"Bearer {valid_token}"}
