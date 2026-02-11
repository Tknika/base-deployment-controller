"""
Unit tests for StatusEventManager and ContainerStatusEvent.
"""
import pytest
from datetime import datetime, timezone
from queue import Queue

from src.base_deployment_controller.models.events import ContainerStatusEvent, ServiceState
from src.base_deployment_controller.services.status_event_manager import StatusEventManager
from src.base_deployment_controller.services.config import ConfigService


def test_container_status_event_creation():
    """Test that ContainerStatusEvent can be created and serialized."""
    event = ContainerStatusEvent(
        container_name="test-container",
        state=ServiceState.STARTED,
        prev_state=ServiceState.STARTING,
        action="start",
        timestamp=datetime.now(timezone.utc)
    )
    
    assert event.container_name == "test-container"
    assert event.state == ServiceState.STARTED
    assert event.prev_state == ServiceState.STARTING
    assert event.action == "start"
    assert event.timestamp is not None
    
    # Test JSON serialization
    json_str = event.model_dump_json()
    assert "test-container" in json_str
    assert "started" in json_str.lower()
    print(f"✓ Event JSON: {json_str}")


def test_container_status_event_json_format():
    """Test that JSON matches expected SSE format."""
    event = ContainerStatusEvent(
        container_name="web",
        state=ServiceState.STOPPED,
        prev_state=None,
        action="stop",
        timestamp=datetime(2026, 1, 20, 10, 30, 0, tzinfo=timezone.utc)
    )
    
    json_str = event.model_dump_json()
    
    # Should be valid JSON
    import json
    data = json.loads(json_str)
    
    assert data["container_name"] == "web"
    assert data["state"] == "stopped"
    assert data["action"] == "stop"
    assert data["prev_state"] is None
    
    print(f"✓ JSON structure is valid: {json_str}")


def test_status_event_manager_creation():
    """Test that StatusEventManager can be instantiated."""
    config = ConfigService("data/compose.yaml", "data/.env")
    manager = StatusEventManager(config)
    
    assert manager is not None
    assert manager._thread is None  # Not started yet
    assert len(manager._subscribers) == 0
    print("✓ StatusEventManager created successfully")


def test_status_event_manager_subscribe_unsubscribe():
    """Test subscribe/unsubscribe functionality."""
    config = ConfigService("data/compose.yaml", "data/.env")
    manager = StatusEventManager(config)
    
    # Subscribe
    q1 = manager.subscribe()
    assert isinstance(q1, Queue)
    assert len(manager._subscribers) == 1
    print("✓ First subscriber connected")
    
    # Subscribe again
    q2 = manager.subscribe()
    assert len(manager._subscribers) == 2
    print("✓ Second subscriber connected")
    
    # Unsubscribe first
    manager.unsubscribe(q1)
    assert len(manager._subscribers) == 1
    print("✓ First subscriber disconnected")
    
    # Unsubscribe second
    manager.unsubscribe(q2)
    assert len(manager._subscribers) == 0
    print("✓ Second subscriber disconnected")


def test_status_event_manager_broadcast():
    """Test that events are broadcast to all subscribers."""
    config = ConfigService("data/compose.yaml", "data/.env")
    manager = StatusEventManager(config)
    
    # Subscribe two clients
    q1 = manager.subscribe()
    q2 = manager.subscribe()
    
    # Broadcast an event
    event = ContainerStatusEvent(
        container_name="test",
        state=ServiceState.STARTED,
        prev_state=None,
        action="start",
        timestamp=datetime.now(timezone.utc)
    )
    manager._broadcast(event)
    
    # Both queues should receive the event
    received1 = q1.get(timeout=1)
    received2 = q2.get(timeout=1)
    
    assert received1.container_name == "test"
    assert received2.container_name == "test"
    print("✓ Events broadcast to all subscribers")
    
    manager.unsubscribe(q1)
    manager.unsubscribe(q2)


if __name__ == "__main__":
    print("Running StatusEventManager tests...\n")
    
    test_container_status_event_creation()
    test_container_status_event_json_format()
    test_status_event_manager_creation()
    test_status_event_manager_subscribe_unsubscribe()
    test_status_event_manager_broadcast()
    
    print("\n✓ All tests passed!")
