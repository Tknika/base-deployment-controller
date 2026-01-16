"""
Environment variables routes implemented with a class and dependency injection.
"""
import logging

from fastapi import APIRouter, HTTPException

from ..models.environment import (
    EnvVariable,
    EnvVariablesResponse,
    BulkEnvUpdateRequest,
    EnvUpdateResponse,
)
from ..services.config import ConfigService

logger = logging.getLogger(__name__)


class EnvRoutes:
    """
    Environment variables router built with dependency injection.

    Provides endpoints for retrieving and updating environment variables
    defined in the compose.yaml x-env-vars schema.

    Args:
        config: Instance of `ConfigService` for file access and validation.

    Attributes:
        config: Injected configuration service.
        router: Instance of `APIRouter` with `/envs` endpoints.
    """

    def __init__(self, config: ConfigService) -> None:
        """
        Initialize environment routes.

        Args:
            config: Configuration service instance for dependency injection.
        """
        self.config = config
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
            response_model=EnvUpdateResponse,
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
        self, request: BulkEnvUpdateRequest
    ) -> EnvUpdateResponse:
        """
        Update environment variables in .env file.

        Args:
            request: Bulk update request.

        Returns:
            EnvUpdateResponse with list of updated variables and restart results.

        Raises:
            HTTPException: If validation fails or variables cannot be updated.
        """
        try:
            schema = self.config.get_env_vars_schema()
            updates = request.variables
            logger.debug(
                "Bulk environment update request with %d variables", len(updates)
            )
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
                    logger.debug(f"Validated variable {var_name} with value: {var_value}")
                except ValueError as e:
                    logger.warning(f"Validation failed for {var_name}: {e}")
                    raise HTTPException(status_code=400, detail=str(e))
            logger.info(f"Updating {len(updates)} environment variables")
            self.config.update_env_file(updates)

            # Restart affected services
            affected_services = self.config.get_affected_services(list(updates.keys()))
            logger.debug(f"Affected services: {affected_services}")
            restart_results: dict[str, bool] = {}
            if request.restart_services:
                restart_results = self.config.restart_services(affected_services)
                logger.info(
                    "Successfully updated %d variables. Restart results: %s",
                    len(updates),
                    restart_results,
                )
            else:
                logger.info(
                    "Successfully updated %d variables. Restart skipped by request",
                    len(updates),
                )

            return EnvUpdateResponse(
                success=True,
                updated=list(updates.keys()),
                message="Variables updated successfully",
                restarted_services=restart_results,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to update variables: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to update variables: {e}"
            )
