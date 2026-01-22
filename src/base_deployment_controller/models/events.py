"""
Event models for container status streaming via SSE.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ServiceState(str, Enum):
    """State of a service/container for status events."""

    NOT_STARTED = "not_started"
    PULLING = "pulling"
    PULLED = "pulled"
    CREATING = "creating"
    STARTING = "starting"
    STARTED = "started"
    STOPPING = "stopping"
    STOPPED = "stopped"
    REMOVING = "removing"
    REMOVED = "removed"
    ERROR = "error"


class ContainerStatusEvent(BaseModel):
    """Container status change event for SSE streaming."""

    container_name: str = Field(..., description="Docker container name")
    state: ServiceState = Field(..., description="New state")
    prev_state: Optional[ServiceState] = Field(None, description="Previous state if known")
    action: str = Field(..., description="Docker event action that triggered the state change")
    timestamp: datetime = Field(..., description="Event timestamp")
