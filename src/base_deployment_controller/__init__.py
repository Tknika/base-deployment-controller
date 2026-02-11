"""Base Deployment Controller package entry point."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .services.config import ConfigService
from .services.task_manager import TaskManager
from .routers.api import APIRoutes
from .routers.environment import EnvRoutes
from .routers.container import ContainerRoutes
from .services.status_event_manager import StatusEventManager
from .services.deployment_status_monitor import DeploymentStatusMonitor
from .routers.deployment import DeploymentRoutes
from .builder import AppBuilder


def create_app(
    compose_file: str = "compose.yaml",
    env_file: str = ".env",
    title: str = "Base Deployment Controller",
    description: str = "REST API to control the basic operations of a deployment",
    version: str = "1.0.0",
) -> FastAPI:
    """
    Factory function to create a preconfigured FastAPI application.

    Args:
        compose_file: Path to compose.yaml file.
        env_file: Path to .env file.
        title: FastAPI application title.
        description: FastAPI application description.
        version: Application version string.

    Returns:
        FastAPI app ready to use or extend.
    """
    config_service = ConfigService(compose_file, env_file)
    task_manager = TaskManager(ttl=3600)  # 1 hour TTL for completed tasks
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: start cleanup task
        cleanup_task = asyncio.create_task(_cleanup_loop(task_manager))
        yield
        # Shutdown: cancel cleanup task
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    
    async def _cleanup_loop(task_manager: TaskManager):
        """Background loop for cleaning up old tasks."""
        while True:
            await asyncio.sleep(300)  # Run every 5 minutes
            await task_manager.cleanup_old_tasks()
    
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,
    )
    
    api_routes = APIRoutes()
    env_routes = EnvRoutes(config_service, task_manager)
    status_events = StatusEventManager(config_service)
    deployment_status_monitor = DeploymentStatusMonitor(
        config_service,
        status_events=status_events,
    )
    container_routes = ContainerRoutes(config_service, task_manager, status_events)
    deployment_routes = DeploymentRoutes(config_service, task_manager, deployment_status_monitor)

    app.include_router(api_routes.router)
    app.include_router(env_routes.router)
    app.include_router(container_routes.router)
    app.include_router(deployment_routes.router)

    return app


__all__ = [
    "ConfigService",
    "TaskManager",
    "APIRoutes",
    "EnvRoutes",
    "ContainerRoutes",
    "DeploymentRoutes",
    "AppBuilder",
    "create_app",
]
