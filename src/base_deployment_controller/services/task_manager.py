"""
Task manager for executing Docker operations asynchronously.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from ..models.task import TaskDetail, TaskStatus

logger = logging.getLogger(__name__)


class TaskManager:
    """
    Manages background tasks for Docker operations.

    Executes blocking Docker commands in a thread pool executor to avoid
    blocking FastAPI's event loop. Tracks task state, service states, and
    provides cleanup for completed tasks.

    Attributes:
        tasks: Dictionary mapping task_id to TaskDetail.
        ttl: Time-to-live for completed tasks before cleanup (seconds).
    """

    def __init__(self, ttl: int = 3600):
        """
        Initialize task manager.

        Args:
            ttl: Time-to-live in seconds for completed tasks (default: 1 hour).
        """
        self.tasks: Dict[str, TaskDetail] = {}
        self.ttl = ttl
        self._lock = asyncio.Lock()
        logger.info(f"TaskManager initialized with TTL={ttl}s")

    async def create_task(
        self,
        operation: str,
        func: Callable[[], Any],
    ) -> str:
        """
        Create and start a background task.

        Args:
            operation: Operation name (e.g., "up", "down", "start", "stop").
            func: Synchronous function to execute (Docker command).

        Returns:
            task_id: Unique identifier for the created task.
        """
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with self._lock:
            self.tasks[task_id] = TaskDetail(
                task_id=task_id,
                task_status=TaskStatus.PENDING,
                operation=operation,
                error=None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            )

        logger.info(f"Task {task_id} created for operation '{operation}'")

        # Start background execution
        asyncio.create_task(self._execute_task(task_id, func))

        return task_id

    async def _execute_task(self, task_id: str, func: Callable[[], Any]) -> None:
        """
        Execute a task in a thread pool executor.

        Args:
            task_id: Task identifier.
            func: Synchronous function to execute.
        """
        try:
            # Update status to running
            await self._update_task_status(task_id, TaskStatus.RUNNING)
            logger.debug(f"Task {task_id} starting execution")

            # Execute blocking function in executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, func)

            # Mark as completed
            await self._update_task_status(
                task_id, TaskStatus.COMPLETED, completed=True
            )
            logger.info(f"Task {task_id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            await self._update_task_status(
                task_id, TaskStatus.FAILED, error=str(e), completed=True
            )

    async def _update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: Optional[str] = None,
        completed: bool = False,
    ) -> None:
        """
        Update task status.

        Args:
            task_id: Task identifier.
            status: New task status.
            error: Optional error message.
            completed: Whether the task is completed.
        """
        async with self._lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                task.task_status = status
                task.updated_at = datetime.now(timezone.utc)
                if error:
                    task.error = error
                if completed:
                    task.completed_at = datetime.now(timezone.utc)
                logger.debug(f"Task {task_id} status updated to {status}")

    def get_task(self, task_id: str) -> Optional[TaskDetail]:
        """
        Retrieve task details (synchronous for simplicity).

        Args:
            task_id: Task identifier.

        Returns:
            TaskDetail if found, None otherwise.
        """
        return self.tasks.get(task_id)

    async def cleanup_old_tasks(self) -> None:
        """
        Remove completed tasks older than TTL.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.ttl)
        async with self._lock:
            to_remove = [
                task_id
                for task_id, task in self.tasks.items()
                if task.completed_at and task.completed_at < cutoff
            ]
            for task_id in to_remove:
                del self.tasks[task_id]
                logger.debug(f"Cleaned up task {task_id}")

            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} old tasks")

    async def get_task_stream(self, task_id: str):
        """
        Generator for SSE streaming of task updates.

        Args:
            task_id: Task identifier.

        Yields:
            TaskDetail snapshots as the task progresses.
        """
        if task_id not in self.tasks:
            logger.warning(f"Stream requested for non-existent task {task_id}")
            return

        last_update = None

        while True:
            task = self.get_task(task_id)
            if not task:
                logger.debug(f"Task {task_id} no longer exists, ending stream")
                break

            # Yield if there's an update
            if last_update is None or task.updated_at > last_update:
                last_update = task.updated_at
                yield task

            # Exit if task is completed
            if task.task_status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                logger.debug(f"Task {task_id} finished, ending stream")
                break

            # Wait before next check
            await asyncio.sleep(0.5)
