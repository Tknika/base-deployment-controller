"""API root endpoint models."""
from pydantic import BaseModel, Field


class APIInfoResponse(BaseModel):
    """Response with general API information."""

    name: str = Field(..., description="API name")
    status: str = Field(..., description="API status")
    message: str = Field(..., description="Status message")
