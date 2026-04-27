"""
Tests de schemas de inventario de equipos — INV-01, INV-02, INV-03, INV-04.

Estos tests validan los schemas Pydantic v2 — no requieren DB ni FastAPI app.
Los tests de endpoints CRUD con DB se haran en integration tests (Phase 3+).
"""
import pytest
from pydantic import ValidationError


def test_device_create_schema_valid(set_test_env_vars):
    """INV-01: DeviceCreate acepta campos minimos validos."""
    from app.schemas.device import DeviceCreate
    device = DeviceCreate(
        name="Router Torre Norte",
        ip_address="192.168.1.1",
        device_type="mikrotik",
    )
    assert device.name == "Router Torre Norte"
    assert device.ip_address == "192.168.1.1"
    assert device.site is None


def test_device_create_schema_with_site(set_test_env_vars):
    """INV-02: DeviceCreate acepta campo site para agrupacion geografica."""
    from app.schemas.device import DeviceCreate
    device = DeviceCreate(
        name="OLT Nodo Centro",
        ip_address="10.0.0.1",
        device_type="olt_vsol_gpon",
        site="Nodo Centro",
    )
    assert device.site == "Nodo Centro"


def test_device_create_schema_invalid_ip(set_test_env_vars):
    """INV-01: ip_address invalida lanza ValidationError."""
    from app.schemas.device import DeviceCreate
    with pytest.raises(ValidationError) as exc_info:
        DeviceCreate(
            name="Router",
            ip_address="999.999.999.999",
            device_type="mikrotik",
        )
    assert "ip_address" in str(exc_info.value).lower() or "value" in str(exc_info.value).lower()


def test_device_create_schema_name_required(set_test_env_vars):
    """INV-01: name es requerido en DeviceCreate."""
    from app.schemas.device import DeviceCreate
    with pytest.raises(ValidationError):
        DeviceCreate(ip_address="192.168.1.1", device_type="mikrotik")


def test_device_create_schema_name_not_empty(set_test_env_vars):
    """INV-01: name no puede ser string vacio o solo espacios."""
    from app.schemas.device import DeviceCreate
    with pytest.raises(ValidationError):
        DeviceCreate(name="   ", ip_address="192.168.1.1", device_type="mikrotik")


def test_device_create_schema_invalid_device_type(set_test_env_vars):
    """INV-01: device_type invalido lanza ValidationError."""
    from app.schemas.device import DeviceCreate
    with pytest.raises(ValidationError):
        DeviceCreate(
            name="Router",
            ip_address="192.168.1.1",
            device_type="cisco_invalid",
        )


def test_device_create_schema_ipv6_valid(set_test_env_vars):
    """INV-01: IPv6 es valida en ip_address."""
    from app.schemas.device import DeviceCreate
    device = DeviceCreate(
        name="Router IPv6",
        ip_address="2001:db8::1",
        device_type="mikrotik",
    )
    assert device.ip_address == "2001:db8::1"


def test_device_update_schema_all_optional(set_test_env_vars):
    """INV-03: DeviceUpdate sin campos es valido (PATCH semantics)."""
    from app.schemas.device import DeviceUpdate
    update = DeviceUpdate()
    assert update.name is None
    assert update.ip_address is None
    assert update.site is None


def test_device_update_schema_partial(set_test_env_vars):
    """INV-03: DeviceUpdate con solo name es valido."""
    from app.schemas.device import DeviceUpdate
    update = DeviceUpdate(name="Nuevo Nombre")
    assert update.name == "Nuevo Nombre"
    assert update.ip_address is None


def test_device_read_schema_has_required_fields(set_test_env_vars):
    """INV-04: DeviceRead tiene campos id, status, consecutive_failures."""
    from app.schemas.device import DeviceRead
    from app.models.device import DeviceType, DeviceStatus
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # Crear instancia directamente (simula respuesta de DB)
    read = DeviceRead(
        id=1,
        name="Test Router",
        ip_address="192.168.1.1",
        device_type=DeviceType.MIKROTIK,
        site="Torre Norte",
        status=DeviceStatus.UNKNOWN,
        is_active=True,
        consecutive_failures=0,
        last_seen_at=None,
        created_at=now,
        updated_at=now,
        parent_device_id=None,
        pon_port=None,
        notes=None,
    )
    assert read.id == 1
    assert read.status == DeviceStatus.UNKNOWN


def test_device_read_from_attributes_config(set_test_env_vars):
    """DeviceRead tiene model_config from_attributes=True para crear desde ORM."""
    from app.schemas.device import DeviceRead
    assert DeviceRead.model_config.get("from_attributes") is True


def test_all_device_types_valid(set_test_env_vars):
    """INV-01: todos los 7 tipos de equipo son validos en DeviceCreate."""
    from app.schemas.device import DeviceCreate
    from app.models.device import DeviceType
    for device_type in DeviceType:
        device = DeviceCreate(
            name=f"Test {device_type.value}",
            ip_address="10.0.0.1",
            device_type=device_type,
        )
        assert device.device_type == device_type
