"""
Tests unitarios para app.core.security — encriptacion Fernet de credenciales.

Requirement: DEPLOY-03 — Las credenciales de equipos se almacenan encriptadas en DB.
"""
import pytest
from cryptography.fernet import InvalidToken


def test_fernet_roundtrip():
    """encrypt + decrypt retorna el plaintext original exactamente."""
    from app.core.security import encrypt_credential, decrypt_credential

    plaintext = "admin123"
    encrypted = encrypt_credential(plaintext)
    decrypted = decrypt_credential(encrypted)

    assert decrypted == plaintext, f"Roundtrip fallo: esperaba '{plaintext}', obtuvo '{decrypted}'"


def test_fernet_ciphertext_not_plaintext():
    """El ciphertext no contiene el plaintext — no se almacena en texto plano."""
    from app.core.security import encrypt_credential

    plaintext = "supersecretpassword"
    encrypted = encrypt_credential(plaintext)

    assert plaintext not in encrypted, "FALLA CRITICA: plaintext visible en el ciphertext"
    assert encrypted != plaintext, "El ciphertext es identico al plaintext — encriptacion no aplicada"


def test_fernet_different_plaintexts_different_ciphertexts():
    """Plaintexts distintos producen ciphertexts distintos."""
    from app.core.security import encrypt_credential

    enc1 = encrypt_credential("password_uno")
    enc2 = encrypt_credential("password_dos")

    assert enc1 != enc2, "Dos passwords distintos produjeron el mismo ciphertext"


def test_fernet_invalid_token_raises():
    """Un ciphertext invalido debe lanzar una excepcion — no retornar basura silenciosamente."""
    from app.core.security import decrypt_credential

    with pytest.raises((InvalidToken, ValueError, Exception)):
        decrypt_credential("esto_no_es_un_token_fernet_valido")


def test_fernet_empty_string_roundtrip():
    """El string vacio tambien encripta y desencripta correctamente."""
    from app.core.security import encrypt_credential, decrypt_credential

    plaintext = ""
    encrypted = encrypt_credential(plaintext)
    decrypted = decrypt_credential(encrypted)

    assert decrypted == plaintext
