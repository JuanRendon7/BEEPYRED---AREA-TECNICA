"""
Tests unitarios de modelos SQLAlchemy — verificacion de schema sin DB real.

Estos tests validan que los modelos tienen los tablenames y campos correctos
sin requerir una conexion PostgreSQL activa (tests de estructura, no de integracion).
"""
import pytest


def test_all_required_tablenames_exist():
    """Las 6 tablas requeridas estan definidas en los modelos."""
    from app.models.device import Device
    from app.models.device_credential import DeviceCredential
    from app.models.metric import Metric
    from app.models.alert import Alert
    from app.models.incident import Incident
    from app.models.onu import ONU

    required_tables = {"devices", "device_credentials", "metrics", "alerts", "incidents", "onus"}
    actual_tables = {
        Device.__tablename__,
        DeviceCredential.__tablename__,
        Metric.__tablename__,
        Alert.__tablename__,
        Incident.__tablename__,
        ONU.__tablename__,
    }

    assert actual_tables == required_tables, (
        f"Tablas faltantes o incorrectas.\n"
        f"Esperadas: {required_tables}\n"
        f"Actuales:  {actual_tables}"
    )


def test_device_credential_uses_encrypted_fields():
    """
    DeviceCredential NO tiene campo 'password' en plaintext.
    Tiene 'encrypted_password' y 'encrypted_api_key' para cumplir DEPLOY-03.
    """
    from app.models.device_credential import DeviceCredential
    from sqlalchemy import inspect

    mapper = inspect(DeviceCredential)
    column_names = {col.key for col in mapper.columns}

    # Debe tener campos con prefijo "encrypted_"
    assert "encrypted_password" in column_names, (
        "DeviceCredential no tiene campo 'encrypted_password' — las credenciales serian plaintext"
    )
    assert "encrypted_api_key" in column_names, (
        "DeviceCredential no tiene campo 'encrypted_api_key'"
    )

    # NO debe tener "password" sin prefijo (seria plaintext)
    assert "password" not in column_names, (
        "DeviceCredential tiene campo 'password' en plaintext — DEPLOY-03 violacion"
    )


def test_device_status_enum_values():
    """DeviceStatus tiene los 4 valores requeridos para el dashboard."""
    from app.models.device import DeviceStatus

    required_values = {"up", "down", "warning", "unknown"}
    actual_values = {e.value for e in DeviceStatus}

    assert actual_values == required_values, (
        f"DeviceStatus tiene valores incorrectos.\n"
        f"Esperados: {required_values}\n"
        f"Actuales:  {actual_values}"
    )


def test_device_type_enum_has_all_required_types():
    """DeviceType incluye todos los tipos de equipos de BEEPYRED."""
    from app.models.device import DeviceType

    required_types = {"mikrotik", "olt_vsol_gpon", "olt_vsol_epon", "onu", "ubiquiti", "mimosa", "other"}
    actual_types = {e.value for e in DeviceType}

    assert required_types.issubset(actual_types), (
        f"DeviceType falta tipos.\n"
        f"Requeridos: {required_types}\n"
        f"Actuales:   {actual_types}"
    )


def test_database_url_conversion():
    """_build_async_url convierte postgresql:// a postgresql+asyncpg://."""
    from app.core.database import _build_async_url

    raw = "postgresql://user:pass@host:5432/db"
    converted = _build_async_url(raw)

    assert converted == "postgresql+asyncpg://user:pass@host:5432/db", (
        f"URL no convertida correctamente: {converted}"
    )
    assert "postgresql+asyncpg" in converted
    # No debe tener el prefijo original sin asyncpg
    assert converted.count("postgresql://") == 0
