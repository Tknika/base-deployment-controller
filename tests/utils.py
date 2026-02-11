"""
Test helper utilities.
"""
from typing import Dict, Any, Optional
import time
import threading
import json
import requests


def monitor_deployment_status(api_url: str, stop_event: threading.Event, timeout: int = 120):
    """
    Background worker to monitor /deployment/status SSE and print changes.
    """
    session = requests.Session()
    last_status = None
    endpoint = f"{api_url}/deployment/status"

    try:
        response = session.get(endpoint, stream=True, timeout=timeout)
        response.raise_for_status()

        print(f"\n[MONITOR] Subscribed to {endpoint}")
        
        for line in response.iter_lines():
            if stop_event.is_set():
                break

            if not line or line.startswith(b':'): # Skip empty lines and keep-alives
                continue

            if line.startswith(b'data:'):
                json_str = line[5:].strip()
                try:
                    data = json.loads(json_str)
                    status = data.get("status")
                    if status != last_status:
                        print(f"\n>>> [MONITOR] Deployment Status Change: {last_status} -> {status}")
                        last_status = status
                except json.JSONDecodeError:
                    pass
                    
    except Exception as e:
        if not stop_event.is_set():
            print(f"\n[MONITOR] Error: {e}")
    finally:
        session.close()
        print("\n[MONITOR] Unsubscribed from /deployment/status")


def stream_task_updates(
    api_url: str,
    task_id: str,
    endpoint: str,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Stream SSE task updates and return final task state.

    Args:
        api_url: Base API URL
        task_id: Task ID to monitor
        endpoint: Endpoint to stream from (e.g., "/deployment/tasks/{task_id}/stream")
        timeout: Maximum wait time in seconds

    Returns:
        Final task state dictionary
    """
    session = requests.Session()
    start_time = time.time()
    last_state = None

    try:
        response = session.get(f"{api_url}{endpoint}", stream=True, timeout=timeout)
        response.raise_for_status()

        for line in response.iter_lines():
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task monitoring exceeded {timeout}s timeout")

            if not line or line.startswith(b':'):
                continue

            # Parse SSE format: "data: {json}"
            if line.startswith(b'data:'):
                json_str = line[5:].strip()
                try:
                    last_state = json.loads(json_str)
                    # Print real-time updates
                    if "task_status" in last_state:
                        print(f"  Task {task_id[:8]}... - Status: {last_state['task_status']}")

                except json.JSONDecodeError:
                    pass

            # Check for completion
            if line.startswith(b'event: done'):
                break

    except Exception as e:
        print(f"Error streaming task updates: {e}")
        raise
    finally:
        session.close()

    return last_state or {}
