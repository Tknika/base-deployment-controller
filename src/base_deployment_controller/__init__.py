"""Base Deployment Controller package entry point."""
from fastapi import FastAPI

from .services.config import ConfigService
from .routers.environment import EnvRoutes
from .routers.container import ContainerRoutes
from .routers.deployment import DeploymentRoutes
from .builder import AppBuilder


def create_app(
    compose_file: str = "compose.yaml",
    env_file: str = ".env",
    include_routers: bool = True,
    title: str = "Base Deployment Controller",
    description: str = "REST API to control the basic operations of a deployment",
    version: str = "1.0.0",
) -> FastAPI:
    """
    Factory function to create a preconfigured FastAPI application.

    Args:
        compose_file: Path to compose.yaml file.
        env_file: Path to .env file.
        include_routers: If True, registers base routers (envs, containers, deployment).
        title: FastAPI application title.
        description: FastAPI application description.
        version: Application version string.

    Returns:
        FastAPI app ready to use or extend.
    """
    app = FastAPI(
        title=title,
        description=description,
        version=version,
    )

    if include_routers:
        config_service = ConfigService(compose_file, env_file)
        env_routes = EnvRoutes(config_service)
        container_routes = ContainerRoutes(config_service)
        deployment_routes = DeploymentRoutes(config_service)

        app.include_router(env_routes.router)
        app.include_router(container_routes.router)
        app.include_router(deployment_routes.router)

    return app


__all__ = [
    "ConfigService",
    "EnvRoutes",
    "ContainerRoutes",
    "DeploymentRoutes",
    "AppBuilder",
    "create_app",
]
