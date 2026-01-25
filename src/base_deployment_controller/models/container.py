"""Container models."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ContainerInfo(BaseModel):
    """Docker container information and service metadata."""

    name: str = Field(..., description="Container name")
    image: str = Field(..., description="Container image")
    status: str = Field(..., description="Container status")
    started_at: Optional[datetime] = Field(None, description="Container start time")
    ports: list[str] = Field(..., description="Exposed ports")
    depends_on: list[str] = Field(..., description="Service dependencies")


class ContainersInfoResponse(BaseModel):
    """Response with list of containers and their current status."""

    containers: list[ContainerInfo] = Field(..., description="List of containers")
