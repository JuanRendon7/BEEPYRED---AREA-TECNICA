from sqlalchemy import Integer, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class DeviceCredential(Base):
    """
    Credenciales de acceso a equipos de red — almacenadas encriptadas con Fernet.

    DEPLOY-03: Las credenciales NO se almacenan en texto plano.
    encrypted_password y encrypted_api_key contienen el resultado de
    security.encrypt_credential(plaintext) — siempre texto cifrado Fernet.
    """
    __tablename__ = "device_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    # Tipos de credencial: "ssh", "routeros_api", "snmp", "http_basic", "api_key"
    credential_type: Mapped[str] = mapped_column(String(50), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Texto cifrado Fernet — resultado de encrypt_credential(password)
    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Texto cifrado Fernet — resultado de encrypt_credential(api_key)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
