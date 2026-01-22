"""
API root endpoints for health check and general information.
"""
import logging

from fastapi import APIRouter

from ..models.api import APIInfoResponse

logger = logging.getLogger(__name__)


class APIRoutes:
    """
    API root router for general endpoints.

    Provides basic health checks and API information at the root path.

    Attributes:
        router: Instance of `APIRouter` with root endpoints.
    """

    def __init__(self) -> None:
        """Initialize API root routes."""
        self.router = self._build_router()

    def _build_router(self) -> APIRouter:
        """
        Build and configure the router with root endpoints.

        Returns:
            APIRouter configured with root handlers.
        """
        router = APIRouter(tags=["API"])

        # GET / - API health check and info
        router.add_api_route(
            "/",
            self.get_api_info,
            methods=["GET"],
            response_model=APIInfoResponse,
        )

        return router

    async def get_api_info(self) -> APIInfoResponse:
        """
        Get API health status and general information.

        Returns:
            APIInfoResponse indicating API is operational.
        """
        logger.debug("API info endpoint requested")
        return APIInfoResponse(
            name="Base Deployment Controller",
            status="operational",
            message="API is active and operational",
        )
