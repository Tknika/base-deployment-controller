"""
StatusEventManager: on-demand Docker events monitor with SSE subscribers.
"""
import threading
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional
from queue import Queue, Empty

import asyncio

from ..models.events import ContainerStatusEvent, ServiceState
from ..services.config import ConfigService

logger = logging.getLogger(__name__)


class StatusEventManager:
    """
    Manages a single Docker events monitor and broadcasts container status events
    to subscribed SSE clients. Starts when the first subscriber connects and stops
    when there are no subscribers.
    """

    def __init__(self, config: ConfigService) -> None:
        self.config = config
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._subscribers: List[Queue] = []
        self._lock = threading.Lock()
        self._last_state: Dict[str, ServiceState] = {}

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            # Reset stop event
            self._stop_event.clear()
            # Start monitor thread
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            logger.info("StatusEventManager: monitor started")

    def _maybe_stop(self) -> None:
        with self._lock:
            if self._subscribers:
                return
            if self._thread and self._thread.is_alive():
                self._stop_event.set()
                self._thread.join(timeout=5)
                self._thread = None
                logger.info("StatusEventManager: monitor stopped")

    def subscribe(self) -> Queue:
        """Add a new subscriber and ensure the monitor is running."""
        q: Queue = Queue()
        with self._lock:
            self._subscribers.append(q)
        self._ensure_started()
        return q

    def unsubscribe(self, q: Queue) -> None:
        """Remove subscriber and stop monitor if none left."""
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)
        self._maybe_stop()

    async def get_event(self, q: Queue) -> ContainerStatusEvent:
        """
        Async helper to get next event from a subscriber queue.
        
        Polls the queue with short timeout to allow cancellation checks.
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                # Use run_in_executor to avoid blocking
                event = await loop.run_in_executor(None, q.get, True, 0.1)
                return event
            except Empty:
                # Queue empty, yield control and retry
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.debug(f"Error getting event from queue: {e}")
                await asyncio.sleep(0.05)

    def _broadcast(self, event: ContainerStatusEvent) -> None:
        # Snapshot subscribers to avoid holding lock while putting
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put(event, timeout=0.1)
            except Exception:
                pass

    def _monitor_loop(self) -> None:
        """Background thread: listen to Docker events and broadcast mapped state events."""
        try:
            logger.debug("StatusEventManager: starting Docker event monitor")
            docker = self.config.get_docker_client()
            action_to_state = {
                "kill": ServiceState.STOPPING,
                "stop": ServiceState.STOPPED,
                "die": ServiceState.STOPPED,
                "create": ServiceState.CREATING,
                "start": ServiceState.STARTING,
                "health_status: healthy": ServiceState.STARTED,
                "destroy": ServiceState.REMOVED,
                "pull": ServiceState.PULLING,
                "build": ServiceState.CREATING,
            }
            
            logger.debug("StatusEventManager: listening to docker.system.events()")
            for event in docker.system.events(filters={"type": "container"}):
                if self._stop_event.is_set():
                    logger.debug("StatusEventManager: stop event received, breaking")
                    break
                try:
                    action = getattr(event, "action", "").lower()
                    actor = getattr(event, "actor", None)
                    attributes = getattr(actor, "attributes", {}) if actor else {}
                    name = attributes.get("name")
                    
                    if not name:
                        logger.debug(f"StatusEventManager: skipping event with no name, action={action}")
                        continue
                    
                    new_state = action_to_state.get(action)
                    if not new_state:
                        logger.debug(f"StatusEventManager: unmapped action '{action}' for {name}")
                        continue
                    
                    prev_state = self._last_state.get(name)
                    self._last_state[name] = new_state
                    
                    logger.debug(f"StatusEventManager: {name} state={new_state} (action={action})")
                    
                    ev = ContainerStatusEvent(
                        container_name=name,
                        state=new_state,
                        prev_state=prev_state,
                        action=action,
                        timestamp=datetime.now(timezone.utc),
                    )
                    self._broadcast(ev)
                except Exception as e:
                    logger.error(f"StatusEventManager: error processing event: {e}", exc_info=True)
                # Yield to avoid tight loop
                time.sleep(0.01)
        except Exception as e:
            logger.error(f"StatusEventManager: monitor loop error: {e}", exc_info=True)
        finally:
            logger.info("StatusEventManager: monitor loop exiting")
