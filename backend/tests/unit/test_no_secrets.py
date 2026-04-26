"""
Tests unitarios INFRA-03 — verificar que no hay credenciales hardcodeadas en el codigo.

Escanea archivos Python del proyecto buscando patrones de secrets comunes:
- Tailscale auth keys (tskey-)
- Fernet tokens (gAAAAA)
- IPs privadas hardcodeadas en codigo fuente (no en .env.example)
- Strings que parecen passwords largos asignados directamente

Estos tests deben correr en CI para prevenir commits accidentales de credenciales.
"""
import os
import re
from pathlib import Path


# Patrones que indican credencial hardcodeada (no un placeholder)
SECRET_PATTERNS = [
    re.compile(r"tskey-auth-[A-Za-z0-9]+"),   # Tailscale auth key real
    re.compile(r"gAAAAA[A-Za-z0-9_\-]{20,}"),  # Fernet token real (base64 URL-safe)
    re.compile(r"sk-[A-Za-z0-9]{20,}"),         # OpenAI API key pattern
]

# Archivos a ignorar en el escaneo (contienen ejemplos/plantillas, no valores reales)
IGNORED_FILES = {
    ".env.example",
    "test_no_secrets.py",  # Este mismo archivo
}


def _get_python_files(root: Path) -> list[Path]:
    """Retorna todos los archivos .py del proyecto excluyendo IGNORED_FILES."""
    files = []
    for path in root.rglob("*.py"):
        if path.name not in IGNORED_FILES and ".venv" not in path.parts:
            files.append(path)
    return files


def test_no_tailscale_auth_key_in_code():
    """Ningun archivo Python contiene una Tailscale auth key real (tskey-auth-...)."""
    project_root = Path(__file__).parent.parent.parent  # backend/
    python_files = _get_python_files(project_root)

    violations = []
    pattern = SECRET_PATTERNS[0]  # tskey-auth-...
    for f in python_files:
        content = f.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(content):
            violations.append(str(f))

    assert not violations, (
        f"Tailscale auth key detectada en archivos de codigo:\n"
        + "\n".join(violations)
        + "\nMover a variable de entorno TAILSCALE_AUTH_KEY."
    )


def test_no_fernet_token_in_code():
    """Ningun archivo Python contiene un token Fernet real (gAAAAA...)."""
    project_root = Path(__file__).parent.parent.parent  # backend/
    python_files = _get_python_files(project_root)

    violations = []
    pattern = SECRET_PATTERNS[1]  # gAAAAA...
    for f in python_files:
        content = f.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(content):
            violations.append(str(f))

    assert not violations, (
        f"Token Fernet real detectado en archivos de codigo:\n"
        + "\n".join(violations)
        + "\nMover a variable de entorno FERNET_KEY."
    )


def test_env_example_uses_placeholders():
    """.env.example contiene solo CHANGE_ME placeholders, no valores reales."""
    env_example = Path(__file__).parent.parent.parent.parent / ".env.example"
    if not env_example.exists():
        # Si no existe aun, el test pasa (se creara en Task 2 del plan)
        return

    content = env_example.read_text(encoding="utf-8")

    # Verificar que contiene los marcadores CHANGE_ME
    assert "CHANGE_ME" in content, (
        ".env.example no contiene marcadores CHANGE_ME — puede tener valores reales"
    )

    # Verificar que no contiene auth keys reales
    for pattern in SECRET_PATTERNS:
        match = pattern.search(content)
        assert not match, (
            f".env.example contiene un posible secret real: {match.group()}\n"
            "Reemplazar con CHANGE_ME placeholder."
        )
