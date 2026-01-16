"""
Deployment management routes implemented with a class and dependency injection.
Manages deployment-wide operations: status, up, stop, down, restart, ping.
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..models.deployment import DeploymentMetadata, DeploymentStatus, DeploymentInfoResponse, DeploymentPingResponse, DeploymentActionResponse
from ..models.compose import ComposeActionResponse
from ..models.environment import EnvVariable
from ..services.config import ConfigService

logger = logging.getLogger(__name__)


class DeploymentRoutes:
    """
    Root deployment router built with dependency injection.

    Manages deployment-wide operations at the root endpoint and control endpoints:
    - GET / - Get deployment status with metadata and env-vars
    - POST /up - Start deployment
    - POST /stop - Stop deployment
    - POST /down - Down deployment (stop and remove containers)
    - POST /restart - Restart deployment
    - GET /ping - Health check

    Args:
        config: Instance of `ConfigService` for Compose and Docker access.

    Attributes:
        config: Injected configuration service.
        router: Instance of `APIRouter` with root endpoints.
    """

    def __init__(self, config: ConfigService) -> None:
        """
        Initialize deployment routes.

        Args:
            config: Configuration service instance for dependency injection.
        """
        self.config = config
        self.router = self._build_router()

    def _build_router(self) -> APIRouter:
        """
        Build and configure the router with deployment endpoints at root level.

        Returns:
            APIRouter configured with GET and POST handlers.
        """
        router = APIRouter(tags=["Deployment"])
        # Note: These routes will be registered without prefix in main.py
        # to mount them at root level: /, /ping, /up, /stop, /down, /restart
        router.add_api_route(
            "/",
            self.get_deployment_info,
            methods=["GET"],
        )
        router.add_api_route(
            "/ping",
            self.ping,
            methods=["GET"],
        )
        router.add_api_route(
            "/up",
            self.deploy_up,
            methods=["POST"],
        )
        router.add_api_route(
            "/stop",
            self.deploy_stop,
            methods=["POST"],
        )
        router.add_api_route(
            "/down",
            self.deploy_down,
            methods=["POST"],
        )
        router.add_api_route(
            "/restart",
            self.deploy_restart,
            methods=["POST"],
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
            metadata_dict: DeploymentMetadata = self.config.get_deployment_metadata()

            # Get status
            status: DeploymentStatus = self.config.get_deployment_status()

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
                metadata=metadata_dict,
                status=status,
                env_vars=env_vars)
        except Exception as e:
            logger.error(f"Failed to get deployment info: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to get deployment info: {e}"
            )

    async def ping(self) -> DeploymentPingResponse:
        """
        Health check endpoint.

        Returns:
            DeploymentPingResponse indicating API is operational.
        """
        logger.debug("Ping request received")
        return DeploymentPingResponse(success=True, message="API is operational")


    async def deploy_up(self) -> DeploymentActionResponse:
        """
        Start the deployment (docker compose up).

        Returns:
            DeploymentActionResponse with success status and message.

        Raises:
            HTTPException: If deployment startup fails.
        """
        try:
            logger.info("Starting deployment (up)")
            result: ComposeActionResponse = self.config.docker_compose_up()

            if not result.success:
                logger.error(f"Failed to start deployment: {result.message}")
                raise HTTPException(
                    status_code=500, detail=result.message
                )

            logger.info("Deployment started successfully")
            return DeploymentActionResponse(
                success=result.success,
                action="up",
                message=result.message
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error starting deployment: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to start deployment: {str(e)}"
            )

    async def deploy_stop(self) -> DeploymentActionResponse:
        """
        Stop the deployment (docker compose stop).

        Returns:
            DeploymentActionResponse with success status and message.

        Raises:
            HTTPException: If deployment stop fails.
        """
        try:
            logger.info("Stopping deployment")
            result: ComposeActionResponse = self.config.docker_compose_stop()

            if not result.success:
                logger.error(f"Failed to stop deployment: {result.message}")
                raise HTTPException(
                    status_code=500, detail=result.message
                )

            logger.info("Deployment stopped successfully")
            return DeploymentActionResponse(
                success=result.success,
                action="stop",
                message=result.message
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error stopping deployment: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to stop deployment: {str(e)}"
            )

    async def deploy_down(self) -> DeploymentActionResponse:
        """
        Down the deployment (docker compose down and remove volumes).

        Returns:
            DeploymentActionResponse with success status and message.

        Raises:
            HTTPException: If deployment down fails.
        """
        try:
            logger.info("Downing deployment (removing containers and volumes)")
            result: ComposeActionResponse = self.config.docker_compose_down()

            if not result.success:
                logger.error(f"Failed to down deployment: {result.message}")
                raise HTTPException(
                    status_code=500, detail=result.message
                )

            logger.info("Deployment downed successfully")
            return DeploymentActionResponse(
                success=result.success,
                action="down",
                message=result.message
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error downing deployment: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to down deployment: {str(e)}"
            )

    async def deploy_restart(self) -> DeploymentActionResponse:
        """
        Restart the deployment (docker compose down then up).

        Returns:
            DeploymentActionResponse with success status and message.

        Raises:
            HTTPException: If deployment restart fails.
        """
        try:
            logger.info("Restarting deployment")
            result: ComposeActionResponse = self.config.docker_compose_restart()

            if not result.success:
                logger.error(f"Failed to stop deployment (while restarting): {result.message}")
                raise HTTPException(
                    status_code=500, detail=result.message
                )

            logger.info("Deployment restarted successfully")
            return DeploymentActionResponse(
                success=result.success,
                action="restart",
                message=result.message
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error restarting deployment: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to restart deployment: {str(e)}"
            )
