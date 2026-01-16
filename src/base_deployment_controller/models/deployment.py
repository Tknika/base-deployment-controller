"""Deployment models."""
from enum import Enum

from .environment import EnvVariable
from pydantic import BaseModel, Field


class DeploymentStatus(str, Enum):
    """
    Deployment status enumeration.

    Values:
        running: All services running.
        partially_running: Some services running.
        stopped: No services running.
        unknown: Status cannot be determined.
    """

    RUNNING = "running"
    PARTIALLY_RUNNING = "partially_running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class DeploymentMetadata(BaseModel):
    """Deployment metadata from x-metadata section in compose.yaml."""

    id: str = Field(..., description="Deployment unique identifier")
    name: str = Field(..., description="Deployment name")
    description: str = Field(..., description="Deployment description")
    version: str = Field(..., description="Deployment version")
    author: str = Field(..., description="Deployment author")
    changelog: str = Field(..., description="Deployment changelog")
    documentation_url: str = Field(..., description="Documentation URL")


class DeploymentInfoResponse(BaseModel):
    """Response with basic deployment information."""

    metadata: DeploymentMetadata = Field(..., description="Deployment metadata")
    status: DeploymentStatus
    env_vars: dict[str, EnvVariable] = Field(..., description="List of environment variables")


class DeploymentPingResponse(BaseModel):
    """Response for deployment ping endpoint."""

    success: bool = Field(..., description="Ping success status")
    message: str = Field(..., description="Ping message")


class DeploymentActionResponse(BaseModel):
    """Response after performing a deployment action."""

    success: bool = Field(..., description="Action success status")
    action: str = Field(..., description="Action performed")
    message: str = Field(..., description="Status message")