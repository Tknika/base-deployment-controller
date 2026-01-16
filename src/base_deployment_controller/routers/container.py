"""
Container management routes implemented with a class and dependency injection.
"""
import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from python_on_whales.exceptions import DockerException

from ..models.container import (
    ContainerInfo,
    ContainersInfoResponse,
    ContainerControlResponse,
)
from ..services.config import ConfigService

logger = logging.getLogger(__name__)


class ContainerRoutes:
    """
    Docker containers router built with dependency injection.

    Provides endpoints for retrieving container status, controlling containers,
    and streaming container logs via WebSocket.

    Args:
        config: Instance of `ConfigService` for Compose and Docker access.

    Attributes:
        config: Injected configuration service.
        router: Instance of `APIRouter` with `/containers` endpoints.
    """

    def __init__(self, config: ConfigService) -> None:
        """
        Initialize container routes.

        Args:
            config: Configuration service instance for dependency injection.
        """
        self.config = config
        self.router = self._build_router()

    def _build_router(self) -> APIRouter:
        """
        Build and configure the router with container management endpoints.

        Returns:
            APIRouter configured with GET and POST handlers for /containers.
        """
        router = APIRouter(prefix="/containers", tags=["Containers"])
        # GET /containers - list all containers
        router.add_api_route(
            "",
            self.get_containers,
            methods=["GET"],
            response_model=ContainersInfoResponse,
        )
        # GET /containers/<container_name> - get specific container info
        router.add_api_route(
            "/{container_name}",
            self.get_container,
            methods=["GET"],
            response_model=ContainerInfo,
        )
        # POST /containers/<container_name>/start - start container
        router.add_api_route(
            "/{container_name}/start",
            self.container_start,
            methods=["POST"],
            response_model=ContainerControlResponse,
        )
        # POST /containers/<container_name>/stop - stop container
        router.add_api_route(
            "/{container_name}/stop",
            self.container_stop,
            methods=["POST"],
            response_model=ContainerControlResponse,
        )
        # POST /containers/<container_name>/restart - restart container
        router.add_api_route(
            "/{container_name}/restart",
            self.container_restart,
            methods=["POST"],
            response_model=ContainerControlResponse,
        )
        # WebSocket /containers/<container_name>/logs - stream container logs
        router.websocket("/{container_name}/logs")(self.container_logs)
        return router

    async def get_containers(self) -> ContainersInfoResponse:
        """
        Get status of all containers defined in compose.yaml.

        Returns:
            ContainersInfoResponse with list of containers and their current states.

        Raises:
            HTTPException: If unable to retrieve container information from Docker.
        """
        try:
            logger.debug("Fetching container status from Docker")
            services = self.config.compose_services
            client = self.config.get_docker_client()
            containers = []
            for service_name, service_config in services.items():
                container_name = service_config.get("container_name", service_name)
                ports = service_config.get("expose", [])
                try:
                    if not client.container.exists(container_name):
                        containers.append(
                            ContainerInfo(
                                name=service_name,
                                image=service_config.get("image", ""),
                                status="Container not created",
                                started_at=None,
                                ports=ports,
                                depends_on=self.config.get_service_dependencies(
                                    service_name
                                ),
                            )
                        )
                        continue
                    container_inspect = client.container.inspect(container_name)
                    status = container_inspect.state.status or "unknown"
                    started_at = container_inspect.state.started_at
                except DockerException as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Docker error while inspecting {container_name}: {e}",
                    )
                containers.append(
                    ContainerInfo(
                        name=service_name,
                        image=service_config.get("image", ""),
                        status=status,
                        started_at=started_at,
                        ports=ports,
                        depends_on=self.config.get_service_dependencies(service_name),
                    )
                )
            logger.info(f"Successfully retrieved status for {len(containers)} containers")
            return ContainersInfoResponse(containers=containers)
        except Exception as e:
            logger.error(f"Failed to get container status: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to get container status: {e}"
            )

    async def get_container(self, container_name: str) -> ContainerInfo:
        """
        Get information about a specific container.

        Args:
            container_name: Name of the service/container from compose.yaml.

        Returns:
            ContainerInfo with container information.

        Raises:
            HTTPException: If service/container not found.
        """
        try:
            logger.debug(f"Fetching info for container: {container_name}")
            services = self.config.compose_services
            if container_name not in services:
                logger.warning(f"Service not found: {container_name}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Service '{container_name}' not found in compose.yaml",
                )
            service_config = services[container_name]
            actual_container_name = service_config.get("container_name", container_name)
            client = self.config.get_docker_client()

            if not client.container.exists(actual_container_name):
                logger.warning(f"Container not found: {actual_container_name}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Container '{actual_container_name}' not found in Docker",
                )

            container_inspect = client.container.inspect(actual_container_name)
            logger.info(f"Successfully retrieved info for {container_name}")
            return ContainerInfo(
                name=container_name,
                image=service_config.get("image", ""),
                status=container_inspect.state.status or "unknown",
                started_at=container_inspect.state.started_at,
                ports=service_config.get("expose", []),
                depends_on=self.config.get_service_dependencies(container_name),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get container info: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to get container info: {e}"
            )

    async def container_start(
        self, container_name: str
    ) -> ContainerControlResponse:
        """
        Start a container.

        Args:
            container_name: Name of the service/container from compose.yaml.

        Returns:
            ContainerControlResponse with action result.

        Raises:
            HTTPException: If service/container not found or action fails.
        """
        return await self._control_container(container_name, "start")

    async def container_stop(
        self, container_name: str
    ) -> ContainerControlResponse:
        """
        Stop a container.

        Args:
            container_name: Name of the service/container from compose.yaml.

        Returns:
            ContainerControlResponse with action result.

        Raises:
            HTTPException: If service/container not found or action fails.
        """
        return await self._control_container(container_name, "stop")

    async def container_restart(
        self, container_name: str
    ) -> ContainerControlResponse:
        """
        Restart a container.

        Args:
            container_name: Name of the service/container from compose.yaml.

        Returns:
            ContainerControlResponse with action result.

        Raises:
            HTTPException: If service/container not found or action fails.
        """
        return await self._control_container(container_name, "restart")

    async def _control_container(
        self, container_name: str, action: str
    ) -> ContainerControlResponse:
        """
        Internal method to control a container (start/stop/restart).

        Args:
            container_name: Name of the service/container from compose.yaml.
            action: Action to perform (start, stop, restart).

        Returns:
            ContainerControlResponse with action result.

        Raises:
            HTTPException: If service/container not found or action fails.
        """
        try:
            logger.debug(f"Control request for container: {container_name}, action: {action}")
            services = self.config.compose_services
            if container_name not in services:
                logger.warning(f"Service not found: {container_name}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Service '{container_name}' not found in compose.yaml",
                )
            service_config = services[container_name]
            actual_container_name = service_config.get("container_name", container_name)
            client = self.config.get_docker_client()
            if not client.container.exists(actual_container_name):
                logger.warning(f"Container not found: {actual_container_name}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Container '{actual_container_name}' not found in Docker",
                )

            logger.info(f"Executing {action} on container: {actual_container_name}")
            try:
                if action == "start":
                    client.container.start(actual_container_name)
                elif action == "stop":
                    client.container.stop(actual_container_name)
                elif action == "restart":
                    client.container.restart(actual_container_name)
                logger.info(f"Container {actual_container_name} {action}ed successfully")
            except DockerException as e:
                logger.error(
                    f"Docker error while executing {action} on {actual_container_name}: {e}"
                )
                raise HTTPException(status_code=500, detail=f"Docker error: {e}")
            return ContainerControlResponse(
                success=True,
                container=container_name,
                action=action,
                message=f"Container {action}ed successfully",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to {action} container {container_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to {action} container: {e}",
            )

    async def container_logs(self, websocket: WebSocket, container_name: str) -> None:
        """
        Stream container logs in real-time via WebSocket.

        Args:
            websocket: WebSocket connection.
            container_name: Name of the service/container from compose.yaml.
        """
        logger.info(
            f"WebSocket connection established for logs of container: {container_name}"
        )
        await websocket.accept()
        try:
            services = self.config.compose_services
            if container_name not in services:
                logger.warning(
                    f"WebSocket logs requested for non-existent service: {container_name}"
                )
                await websocket.send_json(
                    {"error": f"Service '{container_name}' not found in compose.yaml"}
                )
                await websocket.close()
                return
            actual_container_name = self.config.get_container_name_by_service(
                container_name
            )
            client = self.config.get_docker_client()
            if not client.container.exists(actual_container_name):
                logger.warning(
                    f"WebSocket logs requested for non-existent container: {actual_container_name}"
                )
                await websocket.send_json(
                    {"error": f"Container '{actual_container_name}' not found in Docker"}
                )
                await websocket.close()
                return

            try:
                # Stream all logs (historical + follow new logs in real-time)
                logger.debug(f"Starting log stream for {actual_container_name}")

                # Get log generator - this call is fast and non-blocking
                log_generator = client.container.logs(
                    actual_container_name,
                    follow=True,
                    stream=True,
                )

                for log_line in log_generator:
                    # Decode bytes to text
                    text_line = (
                        log_line.decode("utf-8")
                        if isinstance(log_line, (bytes, bytearray))
                        else str(log_line)
                    )

                    # Send to WebSocket client
                    await websocket.send_text(text_line)

                    # Yield control to allow other coroutines to run
                    await asyncio.sleep(0)

            except DockerException as e:
                logger.error(f"Failed to stream logs from {actual_container_name}: {e}")
                await websocket.send_json({"error": f"Failed to stream logs: {e}"})
        except WebSocketDisconnect:
            logger.debug(f"WebSocket client disconnected for {container_name}")
        except Exception as e:
            logger.error(
                f"Unexpected error in WebSocket handler for {container_name}: {e}"
            )
            try:
                await websocket.send_json({"error": f"Failed to stream logs: {e}"})
            except:
                pass
        finally:
            try:
                await websocket.close()
            except:
                pass
            logger.info(f"WebSocket connection closed for {container_name}")
