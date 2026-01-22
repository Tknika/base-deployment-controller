"""
Environment variables routes implemented with a class and dependency injection.
"""
import asyncio
import json
import logging
import threading
import time
from typing import AsyncIterator, Dict, Optional, Set

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..models.environment import (
    EnvVariable,
    EnvVariablesResponse,
    BulkEnvUpdateRequest,
    EnvUpdateResponse,
)
from ..models.task import TaskResponse, TaskDetail, TaskStatus
from ..services.config import ConfigService
from ..services.task_manager import TaskManager

logger = logging.getLogger(__name__)


class EnvRoutes:
    """
    Environment variables router built with dependency injection.

    Provides endpoints for retrieving and updating environment variables
    defined in the compose.yaml x-env-vars schema. Updates are async when
    services need to be restarted.

    Args:
        config: Instance of `ConfigService` for file access and validation.
        task_manager: Instance of `TaskManager` for async operations.

    Attributes:
        config: Injected configuration service.
        task_manager: Injected task manager service.
        router: Instance of `APIRouter` with `/envs` endpoints.
    """

    def __init__(self, config: ConfigService, task_manager: TaskManager) -> None:
        """
        Initialize environment routes.

        Args:
            config: Configuration service instance for dependency injection.
            task_manager: Task manager instance for dependency injection.
        """
        self.config = config
        self.task_manager = task_manager
        self.router = self._build_router()

    def _build_router(self) -> APIRouter:
        """
        Build and configure the router with environment variable endpoints.

        Returns:
            APIRouter configured with GET and PUT handlers for /envs.
        """
        router = APIRouter(prefix="/envs", tags=["Environment Variables"])
        router.add_api_route(
            "",
            self.get_environment_variables,
            methods=["GET"],
            response_model=EnvVariablesResponse,
        )
        router.add_api_route(
            "",
            self.update_environment_variables,
            methods=["PUT"],
            status_code=202,
        )
        # GET /envs/tasks/{task_id} - get task status
        router.add_api_route(
            "/tasks/{task_id}",
            self.get_task_status,
            methods=["GET"],
            response_model=TaskDetail,
        )
        # GET /envs/tasks/{task_id}/stream - SSE stream
        router.add_api_route(
            "/tasks/{task_id}/stream",
            self.stream_task_progress,
            methods=["GET"],
        )
        return router

    async def get_environment_variables(self) -> EnvVariablesResponse:
        """
        Get all environment variables with their metadata and current values.

        Combines schema from x-env-vars in compose.yaml with current values from .env file.

        Returns:
            EnvVariablesResponse with list of all variables.

        Raises:
            HTTPException: If unable to load environment variables.
        """
        try:
            logger.debug("Fetching environment variables schema and current values")
            schema = self.config.get_env_vars_schema()
            current_values = self.config.load_env_values()
            variables = []
            for var_name, var_schema in schema.items():
                default_val = var_schema.get("default", "")
                current_val = current_values.get(var_name)
                value = current_val if current_val is not None else default_val
                variables.append(
                    EnvVariable(
                        name=var_name,
                        description=var_schema.get("description", ""),
                        default=default_val,
                        value=value,
                        type=var_schema.get("type", "string"),
                        advanced=var_schema.get("advanced", False),
                    )
                )
            logger.info(f"Successfully fetched {len(variables)} environment variables")
            return EnvVariablesResponse(variables=variables)
        except Exception as e:
            logger.error(f"Failed to load environment variables: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to load environment variables: {e}"
            )

    async def update_environment_variables(
        self, request: BulkEnvUpdateRequest, fastapi_request: Request
    ) -> Response:
        """
        Update environment variables in .env file asynchronously.

        When restart_services is True, the operation runs asynchronously
        and returns 202 Accepted with a task_id.

        Args:
            request: Bulk update request with variables and restart flag.
            fastapi_request: FastAPI request object (for building Location header).

        Returns:
            Response with 202 status and TaskResponse body.

        Raises:
            HTTPException: If validation fails or variables cannot be updated.
        """
        try:
            schema = self.config.get_env_vars_schema()
            updates = request.variables
            logger.debug(
                "Bulk environment update request with %d variables", len(updates)
            )

            # Validate all variables first
            for var_name, var_value in updates.items():
                if var_name not in schema:
                    logger.warning(f"Attempted to add unknown variable: {var_name}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Variable '{var_name}' not found in schema. Cannot add new variables.",
                    )
                var_schema = schema[var_name]
                try:
                    self.config.validate_variable_value(
                        var_name, var_value, var_schema["type"]
                    )
                    logger.debug(
                        f"Validated variable {var_name} with value: {var_value}"
                    )
                except ValueError as e:
                    logger.warning(f"Validation failed for {var_name}: {e}")
                    raise HTTPException(status_code=400, detail=str(e))

            logger.info(f"Updating {len(updates)} environment variables")

            # Create async task for update + restart
            task_id = await self.task_manager.create_task(
                operation="env_update",
                func=lambda: self._execute_env_update(
                    task_id, updates, request.restart_services
                ),
            )

            # Build Location header
            location = str(fastapi_request.url_for("get_task_status", task_id=task_id))

            logger.info(f"Environment update task created: {task_id}")

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
            logger.error(f"Failed to create env update task: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to update environment variables: {e}"
            )

    async def get_task_status(self, task_id: str) -> TaskDetail:
        """
        Get the current status of an environment update task.

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

    # Helper methods for executing environment operations

    # Service event monitoring removed; use /containers/events SSE for container status changes.

    def _execute_env_update(
        self,
        task_id: str,
        updates: dict[str, str],
        restart_services: bool,
    ) -> EnvUpdateResponse:
        """
        Execute environment variable update with optional service restart.

        Runs in thread executor. TaskManager auto-manages state transitions:
        PENDING -> RUNNING (on start) -> COMPLETED (success) or FAILED (exception).
        Any exception is caught and its message stored in task.error.

        Args:
            task_id: Task identifier (for logging).
            updates: Dict of variables to update.
            restart_services: Whether to restart affected services.

        Returns:
            EnvUpdateResponse with update results.

        Raises:
            Exception: On update/restart failure. Message stored in task.error.
        """
        try:
            # Update .env file
            logger.info(f"[{task_id}] Updating {len(updates)} environment variables")
            self.config.update_env_file(updates)

            # Build updated variables list for response
            updated_var_names = list(updates.keys())

            # Restart services if requested
            restart_results: dict[str, bool] = {}
            if restart_services:
                # Compute affected services and restart via ConfigService
                affected_services = self.config.get_affected_services(updated_var_names)
                logger.info(f"[{task_id}] Restarting {len(affected_services)} affected services")
                restart_results = self.config.restart_services(affected_services)

            logger.info(f"[{task_id}] Environment update completed successfully")
            return EnvUpdateResponse(
                success=True,
                message=f"Updated {len(updates)} environment variables",
                updated=updated_var_names,
                restarted_services=restart_results,
            )
        except Exception as e:
            logger.error(f"[{task_id}] Error executing environment update: {e}")
            return EnvUpdateResponse(
                success=False,
                message=f"Failed to update environment variables: {str(e)}",
                updated=[],
                restarted_services={},
            )

    # Service-state updates removed; tasks no longer track per-service states.
