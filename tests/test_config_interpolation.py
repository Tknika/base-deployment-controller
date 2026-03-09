"""Unit tests for compose interpolation behavior in ConfigService."""

from pathlib import Path

from base_deployment_controller.services.config import ConfigService


def test_container_name_interpolation_uses_env_file(tmp_path: Path) -> None:
    """Container names should be resolved using variables defined in .env."""
    compose_file = tmp_path / "compose.yaml"
    env_file = tmp_path / ".env"

    compose_file.write_text(
        """
services:
  mongo:
    image: mongo:6.0
    container_name: ${DEPLOYMENT_PREFIX}-mongo
""".strip()
    )
    env_file.write_text("DEPLOYMENT_PREFIX=stacka\n")

    config = ConfigService(compose_file=str(compose_file), env_file=str(env_file))

    assert config.get_container_name_by_service("mongo", resolved=True) == "stacka-mongo"


def test_shell_env_overrides_env_file_for_interpolation(tmp_path: Path, monkeypatch) -> None:
    """Shell environment variables should override values from the .env file."""
    compose_file = tmp_path / "compose.yaml"
    env_file = tmp_path / ".env"

    compose_file.write_text(
        """
services:
  mongo:
    image: mongo:6.0
    container_name: ${DEPLOYMENT_PREFIX}-mongo
""".strip()
    )
    env_file.write_text("DEPLOYMENT_PREFIX=filevalue\n")
    monkeypatch.setenv("DEPLOYMENT_PREFIX", "shellvalue")

    config = ConfigService(compose_file=str(compose_file), env_file=str(env_file))

    assert config.get_container_name_by_service("mongo", resolved=True) == "shellvalue-mongo"


def test_default_value_interpolation_supported(tmp_path: Path) -> None:
    """Default syntax ${VAR:-default} should be resolved when variable is missing."""
    compose_file = tmp_path / "compose.yaml"
    env_file = tmp_path / ".env"

    compose_file.write_text(
        """
services:
  web:
    image: nginx:latest
    container_name: ${DEPLOYMENT_PREFIX:-fallback}-web
""".strip()
    )
    env_file.write_text("")

    config = ConfigService(compose_file=str(compose_file), env_file=str(env_file))

    assert config.get_container_name_by_service("web", resolved=True) == "fallback-web"
