"""Application builder for composing the FastAPI app and custom routers."""
from typing import List, Tuple

from fastapi import APIRouter, FastAPI

from .services.config import ConfigService
from .services.task_manager import TaskManager
from .services.status_event_manager import StatusEventManager
from .routers.api import APIRoutes
from .routers.environment import EnvRoutes
from .routers.container import ContainerRoutes
from .routers.deployment import DeploymentRoutes


class AppBuilder:
    """
    Builder for constructing a Base Deployment Controller FastAPI application.

    Allows registration of custom routers before building the final app.

    Args:
        compose_file: Path to Docker Compose file.
        env_file: Path to environment variables file.
        title: FastAPI application title.
        description: FastAPI application description.
        version: Application version string.
    """

    def __init__(
        self,
        compose_file: str = "compose.yaml",
        env_file: str = ".env",
        title: str = "Base Deployment Controller",
        description: str = "REST API for managing base deployment",
        version: str = "1.0.0",
    ) -> None:
        """
        Initialize the builder and register default routers.

        Args:
            compose_file: Path to Docker Compose file.
            env_file: Path to environment variables file.
            title: FastAPI application title.
            description: FastAPI application description.
            version: Application version string.
        """
        self.compose_file = compose_file
        self.env_file = env_file
        self.title = title
        self.description = description
        self.version = version
        self._custom_routers: List[Tuple[APIRouter, str]] = []

    def register_router(self, router: APIRouter, prefix: str = "") -> "AppBuilder":
        """
        Register a custom router to include when building the app.

        Args:
            router: Router instance to register.
            prefix: Optional path prefix for the router.

        Returns:
            AppBuilder instance for fluent chaining.
        """
        self._custom_routers.append((router, prefix))
        return self

    def build(self) -> FastAPI:
        """
        Build and return a FastAPI app with base and custom routers.

        Returns:
            FastAPI application instance.
        """
        app = FastAPI(
            title=self.title,
            description=self.description,
            version=self.version,
        )

        config_service = ConfigService(self.compose_file, self.env_file)
        task_manager = TaskManager(ttl=3600)
        status_events = StatusEventManager(config_service)
        
        api_routes = APIRoutes()
        env_routes = EnvRoutes(config_service, task_manager)
        container_routes = ContainerRoutes(config_service, task_manager, status_events)
        deployment_routes = DeploymentRoutes(config_service, task_manager)

        app.include_router(api_routes.router)
        app.include_router(env_routes.router)
        app.include_router(container_routes.router)
        app.include_router(deployment_routes.router)

        for router, prefix in self._custom_routers:
            app.include_router(router, prefix=prefix)

        return app
