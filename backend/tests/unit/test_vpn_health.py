"""
Tests unitarios INFRA-01 — verificar configuracion Tailscale en start-worker.sh.

Estos tests son de estructura (no de integracion): verifican que el script
start-worker.sh contiene las directivas correctas de Tailscale userspace.
No requieren tailscaled corriendo ni acceso a la red ISP.

DECISION BLOQUEADA: Tailscale SaaS con TAILSCALE_AUTH_KEY confirmado por el tecnico.
"""
from pathlib import Path


def _get_start_worker_content() -> str:
    """Lee el contenido de start-worker.sh."""
    script = Path(__file__).parent.parent.parent / "scripts" / "start-worker.sh"
    assert script.exists(), (
        f"start-worker.sh no encontrado en {script}\n"
        "Task 1 de Plan 01 debe crear este archivo."
    )
    return script.read_text(encoding="utf-8")


def test_start_worker_uses_tailscale_userspace():
    """start-worker.sh usa --tun=userspace-networking (no kernel mode que requiere NET_ADMIN)."""
    content = _get_start_worker_content()
    assert "--tun=userspace-networking" in content, (
        "start-worker.sh debe usar '--tun=userspace-networking' para Tailscale userspace.\n"
        "Railway bloquea NET_ADMIN — el modo kernel de Tailscale no funciona."
    )


def test_start_worker_uses_tailscale_auth_key_env_var():
    """start-worker.sh autentica con Tailscale usando la variable TAILSCALE_AUTH_KEY (no hardcoded)."""
    content = _get_start_worker_content()
    assert "${TAILSCALE_AUTH_KEY}" in content, (
        "start-worker.sh debe usar ${TAILSCALE_AUTH_KEY} para la autenticacion Tailscale.\n"
        "El valor real de la key viene del entorno Railway — nunca hardcodeado."
    )


def test_start_worker_exports_socks5_proxy():
    """start-worker.sh exporta ALL_PROXY=socks5://localhost:1055 para que los collectors lo usen."""
    content = _get_start_worker_content()
    assert "ALL_PROXY=socks5://localhost:1055" in content, (
        "start-worker.sh debe exportar ALL_PROXY=socks5://localhost:1055.\n"
        "Los collectors (librouteros, asyncssh) necesitan este proxy para conectar via Tailscale."
    )


def test_start_worker_launches_celery_worker():
    """start-worker.sh lanza 'celery worker' al final (despues de Tailscale)."""
    content = _get_start_worker_content()
    assert "celery" in content and "worker" in content, (
        "start-worker.sh debe lanzar el Celery worker despues de inicializar Tailscale."
    )


def test_dockerfile_has_tailscale_in_worker_stage():
    """El stage 'worker' del Dockerfile instala tailscale (no en el stage base ni web)."""
    dockerfile = Path(__file__).parent.parent.parent / "Dockerfile"
    assert dockerfile.exists(), (
        f"Dockerfile no encontrado en {dockerfile}\n"
        "Task 1 de Plan 01 debe crear este archivo."
    )
    content = dockerfile.read_text(encoding="utf-8")

    # Verificar que existe el stage worker
    assert "AS worker" in content, "Dockerfile debe tener un stage 'AS worker'"

    # Verificar que tailscale se instala en el Dockerfile
    assert "tailscale" in content.lower(), (
        "Dockerfile debe instalar tailscale en el stage worker."
    )
