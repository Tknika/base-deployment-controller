"""Docker Compose operation models."""
from typing import List

from pydantic import BaseModel, Field


class ComposeActionResponse(BaseModel):
    """Response after executing a docker-compose action (up/stop/restart)."""

    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Operation result message")
