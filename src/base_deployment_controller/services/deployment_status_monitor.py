"""
DeploymentStatusMonitor: on-demand deployment status monitor with SSE subscribers.

Monitors deployment status changes by polling get_deployment_status at regular intervals
and broadcasts changes to subscribed SSE clients. Starts when the first subscriber connects
and stops when there are no subscribers.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from ..models.deployment import DeploymentStatus
from ..models.events import DeploymentStatusEvent, ServiceState
from ..services.config import ConfigService
from ..services.status_event_manager import StatusEventManager

logger = logging.getLogger(__name__)


class DeploymentStatusMonitor:
    """
    Manages deployment status monitoring and broadcasts status change events
    to subscribed SSE clients. Starts when the first subscriber connects and stops
    when there are no subscribers.
    
    Uses asyncio to process container events without blocking the event loop.
    """

    def __init__(
        self,
        config: ConfigService,
        status_events: StatusEventManager,
        error_backoff_seconds: float = 0.25,
    ) -> None:
        """
        Initialize the deployment status monitor.
        
        Args:
            config: ConfigService instance for accessing deployment status.
            status_events: Shared StatusEventManager (single Docker events subscription).
            error_backoff_seconds: Sleep time after errors in the event loop.
        """
        self.config = config
        self.status_events = status_events
        self._task: Optional[asyncio.Task] = None
        self._subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self._last_status: Optional[DeploymentStatus] = None
        self._error_backoff_seconds = error_backoff_seconds
        self._container_states: Dict[str, ServiceState] = {}
        self._relevant_containers: Set[str] = set()
        self._docker_subscriber_q = None

        services = self.config.compose_services or {}
        for service_name, service_config in services.items():
            container_name = service_config.get("container_name", service_name)
            self._relevant_containers.add(container_name)

        logger.info(
            f"DeploymentStatusMonitor: initialized for {len(self._relevant_containers)} containers"
        )

    async def _ensure_started(self) -> None:
        """Ensure the monitor task is running."""
        async with self._lock:
            if self._task and not self._task.done():
                return
            # Start monitor task
            self._task = asyncio.create_task(self._monitor_loop())
            logger.debug("DeploymentStatusMonitor: monitor started")

    async def _maybe_stop(self) -> None:
        """Stop the monitor if there are no subscribers."""
        async with self._lock:
            if self._subscribers:
                return
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None
                logger.info("DeploymentStatusMonitor: monitor stopped")

    async def subscribe(self) -> tuple[asyncio.Queue, Optional[DeploymentStatus]]:
        """
        Add a new subscriber and ensure the monitor is running.
        
        Returns:
            Tuple of (queue for receiving events, current deployment status).
            The current status is returned immediately so the client has the initial state.
        """
        q: asyncio.Queue = asyncio.Queue()

        # Ensure we have a snapshot for immediate, correct initial state.
        if self._last_status is None:
            await self._refresh_snapshot()

        async with self._lock:
            self._subscribers.append(q)
            current_status = self._last_status

        await self._ensure_started()
        return q, current_status

    async def _refresh_snapshot(self) -> None:
        """Build an initial container state snapshot via Docker inspection."""

        def _snapshot_sync() -> Dict[str, ServiceState]:
            services = self.config.compose_services or {}
            if not services:
                return {}

            client = self.config.get_docker_client()
            snapshot: Dict[str, ServiceState] = {}
            for service_name, service_config in services.items():
                container_name = service_config.get("container_name", service_name)
                try:
                    if not client.container.exists(container_name):
                        snapshot[container_name] = ServiceState.REMOVED
                        continue
                    inspect = client.container.inspect(container_name)
                    if getattr(inspect.state, "status", None) == "running":
                        snapshot[container_name] = ServiceState.STARTED
                    else:
                        snapshot[container_name] = ServiceState.STOPPED
                except Exception:
                    snapshot[container_name] = ServiceState.ERROR
            return snapshot

        async with self._lock:
            # Avoid doing expensive snapshots repeatedly.
            if self._last_status is not None:
                return

        snapshot = await asyncio.to_thread(_snapshot_sync)
        new_status = self._compute_deployment_status(snapshot)

        async with self._lock:
            self._container_states = snapshot
            self._last_status = new_status
            logger.info(f"DeploymentStatusMonitor: initial snapshot status={new_status}")

    def _compute_deployment_status(self, states: Dict[str, ServiceState]) -> DeploymentStatus:
        """Compute deployment status from relevant container states."""
        if not self._relevant_containers:
            return DeploymentStatus.UNKNOWN

        started = 0
        stopped = 0
        transitional = 0
        unknown = 0
        total = len(self._relevant_containers)

        for name in self._relevant_containers:
            state = states.get(name)
            if state in (ServiceState.STARTED, ServiceState.STARTING):
                started += 1
            elif state in (ServiceState.STOPPED, ServiceState.REMOVED, ServiceState.NOT_STARTED):
                stopped += 1
            elif state in (ServiceState.CREATING, ServiceState.STOPPING, ServiceState.PULLING, ServiceState.PULLED, ServiceState.REMOVED):
                transitional += 1
            elif state is None:
                unknown += 1
            else:
                # Error/other states
                logger.warning(f"DeploymentStatusMonitor: container '{name}' in state '{state}' treated as unknown")
                unknown += 1

        if started == total:
            return DeploymentStatus.RUNNING
        if stopped == total:
            return DeploymentStatus.STOPPED
        if started == 0 and stopped == 0 and unknown == total:
            return DeploymentStatus.UNKNOWN
        return DeploymentStatus.PARTIALLY_RUNNING

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        """
        Remove subscriber and stop monitor if none left.
        
        Args:
            q: The queue to unsubscribe.
        """
        async with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)
        await self._maybe_stop()

    async def _broadcast(self, event: DeploymentStatusEvent) -> None:
        """
        Broadcast an event to all subscribers.
        
        Args:
            event: The deployment status event to broadcast.
        """
        # Snapshot subscribers to avoid holding lock while putting
        async with self._lock:
            subscribers = list(self._subscribers)
        
        for q in subscribers:
            try:
                await asyncio.wait_for(q.put(event), timeout=0.1)
            except asyncio.TimeoutError:
                logger.warning("DeploymentStatusMonitor: timeout broadcasting to subscriber")
            except Exception as e:
                logger.error(f"DeploymentStatusMonitor: error broadcasting to subscriber: {e}")

    async def _monitor_loop(self) -> None:
        """
        Background task: process container events and broadcast deployment status changes.
        
        Runs continuously while there are subscribers.
        Only broadcasts when the computed deployment status changes.
        """
        try:
            logger.debug("DeploymentStatusMonitor: starting monitor loop (docker events)")

            # Internal subscription to the shared Docker events manager.
            self._docker_subscriber_q = self.status_events.subscribe()

            while True:
                try:
                    container_event = await self.status_events.get_event(self._docker_subscriber_q)
                    name = container_event.container_name

                    if name not in self._relevant_containers:
                        await asyncio.sleep(0)
                        continue

                    async with self._lock:
                        self._container_states[name] = container_event.state
                        current_status = self._compute_deployment_status(self._container_states)
                        prev_status = self._last_status

                        if current_status == prev_status:
                            continue

                        self._last_status = current_status

                    logger.info(
                        f"DeploymentStatusMonitor: status changed from {prev_status} to {current_status}"
                    )

                    event = DeploymentStatusEvent(
                        status=current_status,
                        previous_status=prev_status,
                        timestamp=datetime.now(timezone.utc),
                    )
                    await self._broadcast(event)

                except asyncio.CancelledError:
                    logger.debug("DeploymentStatusMonitor: monitor loop cancelled")
                    raise
                except Exception as e:
                    logger.error(
                        f"DeploymentStatusMonitor: error processing docker events: {e}",
                        exc_info=True,
                    )
                    await asyncio.sleep(self._error_backoff_seconds)
                    
        except asyncio.CancelledError:
            logger.debug("DeploymentStatusMonitor: monitor loop exiting")
        except Exception as e:
            logger.error(
                f"DeploymentStatusMonitor: fatal error in monitor loop: {e}",
                exc_info=True
            )
        finally:
            # Ensure we unsubscribe from Docker events.
            try:
                if self._docker_subscriber_q is not None:
                    self.status_events.unsubscribe(self._docker_subscriber_q)
            except Exception:
                pass
            logger.debug("DeploymentStatusMonitor: monitor loop stopped")
