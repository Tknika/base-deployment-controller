"""
Container management routes implemented with a class and dependency injection.
"""
import asyncio
import json
import logging
import threading
import time
from typing import AsyncIterator, Dict, Optional, Set

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from python_on_whales.exceptions import DockerException

from ..models.container import ContainerInfo, ContainersInfoResponse
from ..models.task import TaskResponse, TaskDetail, TaskStatus
from ..models.events import ContainerStatusEvent, ServiceState
from ..services.status_event_manager import StatusEventManager
from ..services.config import ConfigService
from ..services.task_manager import TaskManager

logger = logging.getLogger(__name__)


class ContainerRoutes:
    """
    Docker containers router built with dependency injection.

    Provides endpoints for retrieving container status, controlling containers asynchronously,
    and streaming container logs via WebSocket.

    Args:
        config: Instance of `ConfigService` for Compose and Docker access.
        task_manager: Instance of `TaskManager` for async operations.

    Attributes:
        config: Injected configuration service.
        task_manager: Injected task manager service.
        router: Instance of `APIRouter` with `/containers` endpoints.
    """

    def __init__(self, config: ConfigService, task_manager: TaskManager, status_events: StatusEventManager) -> None:
        """
        Initialize container routes.

        Args:
            config: Configuration service instance for dependency injection.
            task_manager: Task manager instance for dependency injection.
        """
        self.config = config
        self.task_manager = task_manager
        self.status_events = status_events
        self.router = self._build_router()

    def _build_router(self) -> APIRouter:
        """
        Build and configure the router with container management endpoints.

        Returns:
            APIRouter configured with GET and POST handlers for /containers.
        """
        router = APIRouter(prefix="/containers", tags=["Containers"])
        
        # IMPORTANT: Register specific routes BEFORE path parameter routes
        # to avoid /events being matched by /{container_name}
        
        # GET /containers - list all containers
        router.add_api_route(
            "",
            self.get_containers,
            methods=["GET"],
            response_model=ContainersInfoResponse,
        )
        # GET /containers/events - SSE container status events (MUST be before /{container_name})
        router.add_api_route(
            "/events",
            self.stream_container_events,
            methods=["GET"],
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
            status_code=202,
        )
        # POST /containers/<container_name>/stop - stop container
        router.add_api_route(
            "/{container_name}/stop",
            self.container_stop,
            methods=["POST"],
            status_code=202,
        )
        # POST /containers/<container_name>/restart - restart container
        router.add_api_route(
            "/{container_name}/restart",
            self.container_restart,
            methods=["POST"],
            status_code=202,
        )
        # GET /containers/<container_name>/tasks/{task_id} - get task status
        router.add_api_route(
            "/{container_name}/tasks/{task_id}",
            self.get_task_status,
            methods=["GET"],
            response_model=TaskDetail,
        )
        # GET /containers/<container_name>/tasks/{task_id}/stream - SSE stream
        router.add_api_route(
            "/{container_name}/tasks/{task_id}/stream",
            self.stream_task_progress,
            methods=["GET"],
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
            logger.info(
                f"Successfully retrieved status for {len(containers)} containers"
            )
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
        self, container_name: str, request: Request
    ) -> Response:
        """
        Start a container asynchronously.

        Returns 202 Accepted with task_id for tracking progress.

        Args:
            container_name: Name of the service/container from compose.yaml.
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.

        Raises:
            HTTPException: If service/container not found.
        """
        return await self._control_container_async(container_name, "start", request)

    async def container_stop(self, container_name: str, request: Request) -> Response:
        """
        Stop a container asynchronously.

        Returns 202 Accepted with task_id for tracking progress.

        Args:
            container_name: Name of the service/container from compose.yaml.
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.

        Raises:
            HTTPException: If service/container not found.
        """
        return await self._control_container_async(container_name, "stop", request)

    async def container_restart(
        self, container_name: str, request: Request
    ) -> Response:
        """
        Restart a container asynchronously.

        Returns 202 Accepted with task_id for tracking progress.

        Args:
            container_name: Name of the service/container from compose.yaml.
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.

        Raises:
            HTTPException: If service/container not found.
        """
        return await self._control_container_async(container_name, "restart", request)

    async def _control_container_async(
        self, container_name: str, action: str, request: Request
    ) -> Response:
        """
        Internal method to control a container asynchronously (start/stop/restart).

        Args:
            container_name: Name of the service/container from compose.yaml.
            action: Action to perform (start, stop, restart).
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.

        Raises:
            HTTPException: If service/container not found.
        """
        try:
            logger.debug(
                f"Async control request for container: {container_name}, action: {action}"
            )
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

            # Create async task
            task_id = await self.task_manager.create_task(
                operation=f"container_{action}",
                func=lambda: self._execute_container_action(
                    task_id, actual_container_name, action, container_name
                )
            )

            # Build Location header
            location = str(
                request.url_for(
                    "get_task_status", container_name=container_name, task_id=task_id
                )
            )

            logger.info(
                f"Container {action} task created for {container_name}: {task_id}"
            )

            # Return 202 Accepted
            return Response(
                status_code=202,
                content=TaskResponse(
                    task_id=task_id, status=TaskStatus.RUNNING
                ).model_dump_json(),
                media_type="application/json",
                headers={"Location": location},
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to create {action} task for {container_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to {action} container: {e}",
            )

    async def get_task_status(self, container_name: str, task_id: str) -> TaskDetail:
        """
        Get the current status of a container task.

        Args:
            container_name: Name of the service/container (for route consistency).
            task_id: The unique identifier of the task.

        Returns:
            TaskDetail with current task status, progress, and result.

        Raises:
            HTTPException: If task not found.
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return task

    async def stream_task_progress(
        self, container_name: str, task_id: str
    ) -> StreamingResponse:
        """
        Stream task progress updates via Server-Sent Events (SSE).

        Args:
            container_name: Name of the service/container (for route consistency).
            task_id: The unique identifier of the task.

        Returns:
            StreamingResponse with SSE stream of task updates.

        Raises:
            HTTPException: If task not found.
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        async def event_generator() -> AsyncIterator[str]:
            """Generate SSE events for task updates."""
            last_update = None

            while True:
                current_task = self.task_manager.get_task(task_id)
                if not current_task:
                    yield f"event: error\ndata: {json.dumps({'error': 'Task not found'})}\n\n"
                    break

                # Send update if task changed
                if current_task.model_dump() != last_update:
                    last_update = current_task.model_dump()
                    yield f"data: {current_task.model_dump_json()}\n\n"

                # If task completed or failed, send final event and stop
                if current_task.task_status in [
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                ]:
                    yield f"event: done\ndata: {current_task.model_dump_json()}\n\n"
                    break

                # Wait before next check
                await asyncio.sleep(0.2)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def container_logs(
        self, websocket: WebSocket, container_name: str
    ) -> None:
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
                    {
                        "error": f"Container '{actual_container_name}' not found in Docker"
                    }
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
                logger.error(
                    f"Failed to stream logs from {actual_container_name}: {e}"
                )
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

    def _execute_container_action(
        self, task_id: str, container_name: str, action: str, service_name: str
    ) -> None:
        """
        Execute container action (start/stop/restart).

        Runs in thread executor. TaskManager auto-manages state transitions:
        PENDING -> RUNNING (on start) -> COMPLETED (success) or FAILED (exception).
        Any exception is caught and its message stored in task.error.

        Args:
            task_id: Task identifier (for logging).
            container_name: Docker container name.
            action: Action (start/stop/restart).
            service_name: Service name (for logging).

        Raises:
            Exception: On docker error. Message stored in task.error.
        """
        try:
            client = self.config.get_docker_client()
            logger.info(f"[{task_id}] Executing container {action}")
            if action == "start":
                client.container.start(container_name)
            elif action == "stop":
                client.container.stop(container_name)
            elif action == "restart":
                client.container.restart(container_name)
            logger.info(f"[{task_id}] Container {action} completed successfully")

        except DockerException as e:
            logger.error(f"[{task_id}] Docker error while {action}ing {container_name}: {e}")
            raise Exception(f"Docker error: {e}")
        except Exception as e:
            logger.error(f"[{task_id}] Error executing {action} on {container_name}: {e}")
            raise

    async def stream_container_events(self) -> StreamingResponse:
        """
        SSE endpoint streaming global container status events (on-demand).
        
        Clients receive ContainerStatusEvent objects containing:
        - container_name: name of the container
        - state: current ServiceState
        - prev_state: previous state if known
        - action: Docker event action that triggered the change
        - timestamp: event timestamp
        
        The StatusEventManager starts listening to docker.system.events() when
        the first client connects and stops when the last client disconnects.
        """

        async def event_generator() -> AsyncIterator[str]:
            # Subscribe; start manager if first subscriber
            subscriber_q = self.status_events.subscribe()
            try:
                while True:
                    # Poll queue for events with async support
                    try:
                        event: ContainerStatusEvent = await self.status_events.get_event(subscriber_q)
                        logger.debug(f"Emitting container event: {event.container_name} -> {event.state}")
                        payload = event.model_dump_json()
                        yield f"{payload}\n"
                    except asyncio.CancelledError:
                        break
                    # Small sleep to prevent busy waiting
                    await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Container events generator error: {e}")
            finally:
                self.status_events.unsubscribe(subscriber_q)
                logger.debug("Container events subscriber disconnected")

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
