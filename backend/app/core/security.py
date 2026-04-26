"""
Encriptacion Fernet para credenciales de equipos de red.

DEPLOY-03: Las credenciales (SSH passwords, API keys, etc.) se almacenan
encriptadas en la tabla device_credentials. Nunca en texto plano.

FERNET_KEY es un SecretStr en Settings — usar .get_secret_value() para obtener
el string. Nunca loggear settings.FERNET_KEY.

Generar una nueva FERNET_KEY:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

CRITICO: Si se pierde la FERNET_KEY, todas las credenciales almacenadas son
irrecuperables. Guardar en password manager (1Password, Bitwarden, etc.)
"""
from cryptography.fernet import Fernet

from app.core.config import settings


def _get_fernet() -> Fernet:
    """Crea instancia Fernet desde FERNET_KEY env var."""
    # .get_secret_value() expone el string interno del SecretStr
    return Fernet(settings.FERNET_KEY.get_secret_value().encode())


def encrypt_credential(plaintext: str) -> str:
    """
    Encripta credencial de equipo para almacenar en DB.

    Retorna: string base64 URL-safe cifrado con Fernet (incluye IV y MAC).
    El resultado varia en cada llamada aunque el plaintext sea el mismo
    (Fernet usa IV aleatorio por diseno).
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_credential(ciphertext: str) -> str:
    """
    Desencripta credencial de equipo recuperada de DB.

    Lanza: cryptography.fernet.InvalidToken si el ciphertext es invalido
    o fue cifrado con una key diferente.
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
