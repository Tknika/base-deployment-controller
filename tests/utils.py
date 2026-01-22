"""
Test helper utilities.
"""
from typing import Dict, Any, Optional
import time
import json
import requests


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
