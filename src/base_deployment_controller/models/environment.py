"""Environment variable models."""
from pydantic import BaseModel, Field


class EnvVariable(BaseModel):
    """Environment variable model with metadata from x-env-vars schema."""

    name: str = Field(..., description="Variable name")
    description: str = Field(..., description="Variable description")
    default: str = Field(..., description="Default value")
    value: str = Field(..., description="Current value")
    type: str = Field(..., description="Type constraint")
    advanced: bool = Field(..., description="Is advanced variable")


class EnvVariablesResponse(BaseModel):
    """Response for listing all environment variables."""

    variables: list[EnvVariable] = Field(..., description="List of environment variables")


class BulkEnvUpdateRequest(BaseModel):
    """Request to update multiple environment variables in bulk."""

    variables: dict[str, str] = Field(..., description="Variables to update")
    recreate_services: bool = Field(
        default=True,
        description=(
            "Whether to recreate affected services after updating the variables."
        ),
    )


class EnvUpdateResponse(BaseModel):
    """Response after updating environment variables."""

    success: bool = Field(..., description="Update success status")
    updated: list[str] = Field(..., description="List of updated variables")
    message: str = Field(..., description="Status message")
    recreated_services: dict[str, bool] = Field(
        default_factory=dict, description="Services recreated and their status"
    )
