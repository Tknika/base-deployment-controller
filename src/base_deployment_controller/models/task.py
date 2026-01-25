"""
Task management models for async operations.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a background task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskResponse(BaseModel):
    """Initial response when creating a background task."""

    task_id: str = Field(..., description="Unique identifier for the task")
    status: TaskStatus = Field(..., description="Current status of the task")


class TaskDetail(BaseModel):
    """Detailed information about a task's execution."""

    task_id: str = Field(..., description="Unique identifier for the task")
    task_status: TaskStatus = Field(..., description="Overall task status")
    operation: str = Field(..., description="Operation being performed (up, down, start, stop, etc.)")
    error: Optional[str] = Field(None, description="Error message if task failed")
    created_at: datetime = Field(..., description="When the task was created")
    updated_at: datetime = Field(..., description="Last update timestamp")
    completed_at: Optional[datetime] = Field(None, description="When the task completed (success or failure)")