"""
Deployment management routes implemented with a class and dependency injection.
Manages deployment-wide operations: status, up, stop, down, restart.
"""
import asyncio
import json
import logging
from typing import AsyncIterator, Dict, Set

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..models.deployment import DeploymentInfoResponse
from ..models.environment import EnvVariable
from ..models.task import TaskResponse, TaskDetail, TaskStatus
from ..services.config import ConfigService
from ..services.task_manager import TaskManager

logger = logging.getLogger(__name__)


class DeploymentRoutes:
    """
    Deployment router built with dependency injection.

    Manages deployment-wide operations:
    - GET /deployment - Get deployment status with metadata and env-vars
    - POST /deployment/up - Start deployment (async)
    - POST /deployment/stop - Stop deployment (async)
    - POST /deployment/down - Down deployment (async)
    - POST /deployment/kill - Kill deployment (async)
    - POST /deployment/restart - Restart deployment (async)
    - GET /deployment/tasks/{task_id} - Get task status
    - GET /deployment/tasks/{task_id}/stream - SSE stream of task progress

    Args:
        config: Instance of `ConfigService` for Compose and Docker access.
        task_manager: Instance of `TaskManager` for async operations.

    Attributes:
        config: Injected configuration service.
        task_manager: Injected task manager service.
        router: Instance of `APIRouter` with /deployment endpoints.
    """

    def __init__(self, config: ConfigService, task_manager: TaskManager) -> None:
        """
        Initialize deployment routes.

        Args:
            config: Configuration service instance for dependency injection.
            task_manager: Task manager instance for dependency injection.
        """
        self.config = config
        self.task_manager = task_manager
        self.router = self._build_router()

    def _build_router(self) -> APIRouter:
        """
        Build and configure the router with deployment endpoints.

        Returns:
            APIRouter configured with GET and POST handlers.
        """
        router = APIRouter(prefix="/deployment", tags=["Deployment"])

        # GET /deployment - deployment info
        router.add_api_route(
            "",
            self.get_deployment_info,
            methods=["GET"],
            response_model=DeploymentInfoResponse,
        )
        # POST /deployment/up - start deployment
        router.add_api_route(
            "/up",
            self.deploy_up,
            methods=["POST"],
            status_code=202,
        )
        # POST /deployment/stop - stop deployment
        router.add_api_route(
            "/stop",
            self.deploy_stop,
            methods=["POST"],
            status_code=202,
        )
        # POST /deployment/down - down deployment
        router.add_api_route(
            "/down",
            self.deploy_down,
            methods=["POST"],
            status_code=202,
        )
        # POST /deployment/kill - kill deployment
        router.add_api_route(
            "/kill",
            self.deploy_kill,
            methods=["POST"],
            status_code=202,
        )
        # POST /deployment/restart - restart deployment
        router.add_api_route(
            "/restart",
            self.deploy_restart,
            methods=["POST"],
            status_code=202,
        )
        # GET /deployment/tasks/{task_id} - get task status
        router.add_api_route(
            "/tasks/{task_id}",
            self.get_task_status,
            methods=["GET"],
            response_model=TaskDetail,
        )
        # GET /deployment/tasks/{task_id}/stream - SSE stream
        router.add_api_route(
            "/tasks/{task_id}/stream",
            self.stream_task_progress,
            methods=["GET"],
        )
        return router

    async def get_deployment_info(self) -> DeploymentInfoResponse:
        """
        Get deployment information with status, metadata, and environment variables.

        Returns:
            DeploymentInfoResponse with status, metadata, and env-vars fields.

        Raises:
            HTTPException: If unable to retrieve deployment information.
        """
        try:
            logger.debug("Fetching deployment info")

            # Get metadata
            metadata_dict = self.config.get_deployment_metadata()

            # Get status
            status = self.config.get_deployment_status()

            # Get environment variables
            schema = self.config.get_env_vars_schema()
            current_values = self.config.load_env_values()
            env_vars: dict[str, EnvVariable] = {}
            for var_name, var_schema in schema.items():
                default_val = var_schema.get("default", "")
                current_val = current_values.get(var_name)
                env_vars[var_name] = EnvVariable(
                    name=var_name,
                    description=var_schema.get("description", ""),
                    default=default_val,
                    value=current_val if current_val is not None else default_val,
                    type=var_schema.get("type", "string"),
                    advanced=var_schema.get("advanced", False),
                )

            logger.info("Successfully retrieved deployment info")
            return DeploymentInfoResponse(
                metadata=metadata_dict, status=status, env_vars=env_vars
            )
        except Exception as e:
            logger.error(f"Failed to get deployment info: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to get deployment info: {e}"
            )

    async def deploy_up(self, request: Request) -> Response:
        """
        Start the deployment (docker compose up) asynchronously.

        Returns 202 Accepted with task_id for tracking progress.

        Args:
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.
        """
        logger.info("Starting deployment (up) - asynchronous")

        # Create async task
        task_id = await self.task_manager.create_task(
            operation="up",
            func=lambda: self._execute_compose_up(task_id),
        )

        # Build Location header
        location = str(request.url_for("get_task_status", task_id=task_id))

        logger.info(f"Deployment up task created: {task_id}")

        # Return 202 Accepted
        return Response(
            status_code=202,
            content=TaskResponse(
                task_id=task_id, status=TaskStatus.RUNNING
            ).model_dump_json(),
            media_type="application/json",
            headers={"Location": location},
        )

    async def deploy_stop(self, request: Request) -> Response:
        """
        Stop the deployment (docker compose stop) asynchronously.

        Returns 202 Accepted with task_id for tracking progress.

        Args:
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.
        """
        logger.info("Stopping deployment - asynchronous")

        # Create async task
        task_id = await self.task_manager.create_task(
            operation="stop",
            func=lambda: self._execute_compose_stop(task_id),
        )

        # Build Location header
        location = str(request.url_for("get_task_status", task_id=task_id))

        logger.info(f"Deployment stop task created: {task_id}")

        # Return 202 Accepted
        return Response(
            status_code=202,
            content=TaskResponse(
                task_id=task_id, status=TaskStatus.RUNNING
            ).model_dump_json(),
            media_type="application/json",
            headers={"Location": location},
        )

    async def deploy_down(self, request: Request) -> Response:
        """
        Down the deployment (docker compose down) asynchronously.

        Returns 202 Accepted with task_id for tracking progress.

        Args:
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.
        """
        logger.info("Taking down deployment - asynchronous")

        # Create async task
        task_id = await self.task_manager.create_task(
            operation="down",
            func=lambda: self._execute_compose_down(task_id),
        )

        # Build Location header
        location = str(request.url_for("get_task_status", task_id=task_id))

        logger.info(f"Deployment down task created: {task_id}")

        # Return 202 Accepted
        return Response(
            status_code=202,
            content=TaskResponse(
                task_id=task_id, status=TaskStatus.RUNNING
            ).model_dump_json(),
            media_type="application/json",
            headers={"Location": location},
        )
    async def deploy_kill(self, request: Request) -> Response:
        """
        Kill the deployment (docker compose kill) asynchronously.

        Returns 202 Accepted with task_id for tracking progress.

        Args:
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.
        """
        logger.info("Killing deployment - asynchronous")

        # Create async task
        task_id = await self.task_manager.create_task(
            operation="kill",
            func=lambda: self._execute_compose_kill(task_id),
        )

        # Build Location header
        location = str(request.url_for("get_task_status", task_id=task_id))

        logger.info(f"Deployment kill task created: {task_id}")

        # Return 202 Accepted
        return Response(
            status_code=202,
            content=TaskResponse(
                task_id=task_id, status=TaskStatus.RUNNING
            ).model_dump_json(),
            media_type="application/json",
            headers={"Location": location},
        )

    async def deploy_restart(self, request: Request) -> Response:
        """
        Restart the deployment (docker compose stop + up) asynchronously.

        Returns 202 Accepted with task_id for tracking progress.

        Args:
            request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.
        """
        logger.info("Restarting deployment - asynchronous")

        # Create async task
        task_id = await self.task_manager.create_task(
            operation="restart",
            func=lambda: self._execute_compose_restart(task_id),
        )

        # Build Location header
        location = str(request.url_for("get_task_status", task_id=task_id))

        logger.info(f"Deployment restart task created: {task_id}")

        # Return 202 Accepted
        return Response(
            status_code=202,
            content=TaskResponse(
                task_id=task_id, status=TaskStatus.RUNNING
            ).model_dump_json(),
            media_type="application/json",
            headers={"Location": location},
        )

    async def get_task_status(self, task_id: str) -> TaskDetail:
        """
        Get the current status of a deployment task.

        Args:
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

    async def stream_task_progress(self, task_id: str) -> StreamingResponse:
        """
        Stream task progress updates via Server-Sent Events (SSE).

        Args:
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
                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def _execute_compose_up(self, task_id: str) -> None:
        """
        Execute docker compose up.

        Runs in thread executor. TaskManager auto-manages state transitions:
        PENDING -> RUNNING (on start) -> COMPLETED (success) or FAILED (exception).
        Any exception is caught and its message stored in task.error.
        """
        try:
            logger.info(f"[{task_id}] Executing compose up")
            result = self.config.docker_compose_up()
            if not result.success:
                raise Exception(result.message)
            logger.info(f"[{task_id}] Compose up completed successfully")

        except Exception as e:
            logger.error(f"[{task_id}] Error executing compose up: {e}")
            raise
            

    def _execute_compose_stop(self, task_id: str) -> None:
        """
        Execute docker compose stop.

        Runs in thread executor. TaskManager auto-manages state transitions:
        PENDING -> RUNNING (on start) -> COMPLETED (success) or FAILED (exception).
        Any exception is caught and its message stored in task.error.
        """
        try:
            logger.info(f"[{task_id}] Executing compose stop")
            result = self.config.docker_compose_stop()
            if not result.success:
                raise Exception(result.message)
            logger.info(f"[{task_id}] Compose stop completed successfully")

        except Exception as e:
            logger.error(f"[{task_id}] Error executing compose stop: {e}")
            raise

    def _execute_compose_down(self, task_id: str) -> None:
        """
        Execute docker compose down.

        Runs in thread executor. TaskManager auto-manages state transitions:
        PENDING -> RUNNING (on start) -> COMPLETED (success) or FAILED (exception).
        Any exception is caught and its message stored in task.error.
        """
        try:
            logger.info(f"[{task_id}] Executing compose down")
            result = self.config.docker_compose_down()
            if not result.success:
                raise Exception(result.message)
            logger.info(f"[{task_id}] Compose down completed successfully")

        except Exception as e:
            logger.error(f"[{task_id}] Error executing compose down: {e}")
            raise

    def _execute_compose_kill(self, task_id: str) -> None:
        """
        Execute docker compose kill.

        Runs in thread executor. TaskManager auto-manages state transitions:
        PENDING -> RUNNING (on start) -> COMPLETED (success) or FAILED (exception).
        Any exception is caught and its message stored in task.error.
        """
        try:
            logger.info(f"[{task_id}] Executing compose kill")
            result = self.config.docker_compose_kill()
            if not result.success:
                raise Exception(result.message)
            logger.info(f"[{task_id}] Compose kill completed successfully")

        except Exception as e:
            logger.error(f"[{task_id}] Error executing compose kill: {e}")
            raise

    def _execute_compose_restart(self, task_id: str) -> None:
        """
        Execute docker compose restart (stop + up).

        Runs in thread executor. TaskManager auto-manages state transitions:
        PENDING -> RUNNING (on start) -> COMPLETED (success) or FAILED (exception).
        Any exception is caught and its message stored in task.error.
        """
        try:
            logger.info(f"[{task_id}] Executing compose restart")
            stop_result = self.config.docker_compose_stop()
            if not stop_result.success:
                raise Exception(stop_result.message)
            up_result = self.config.docker_compose_up()
            if not up_result.success:
                raise Exception(up_result.message)
            logger.info(f"[{task_id}] Compose restart completed successfully")

        except Exception as e:
            logger.error(f"[{task_id}] Error executing compose restart: {e}")
            raise
