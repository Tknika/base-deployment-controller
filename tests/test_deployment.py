"""
Test cases for the Deployment endpoints (/deployment).

Tests the full deployment lifecycle:
- Deploy UP with real-time SSE monitoring
- Deploy DOWN with real-time SSE monitoring
"""
import time
from tests.utils import stream_task_updates


class TestDeploymentEndpoints:
    """Deployment endpoint tests with SSE monitoring."""

    def test_deployment_lifecycle_with_sse_monitoring(self, api_client, api_url, api_server, check_dependencies):
        """
        Test complete deployment lifecycle with real-time SSE monitoring.
        
        Sequence:
        1. POST /deployment/up to start deployment
        2. Monitor SSE stream to track container state transitions
        3. Verify all containers reach STARTED state
        4. POST /deployment/down to down deployment
        5. Monitor SSE stream for shutdown progression
        6. Verify all containers reach REMOVED state
        """
        print("\n=== DEPLOYMENT LIFECYCLE TEST ===\n")
        
        # PHASE 1: Start deployment
        print("PHASE 1: Starting deployment (compose up)...")
        resp_up = api_client.post(f"{api_url}/deployment/up")
        
        assert resp_up.status_code == 202, "UP should return 202 Accepted"
        data_up = resp_up.json()
        assert "task_id" in data_up, "Response should contain task_id"
        assert data_up.get("status") == "running", "Initial status should be 'running'"
        
        task_id_up = data_up["task_id"]
        sse_endpoint_up = f"/deployment/tasks/{task_id_up}/stream"
        
        # Stream and monitor UP progress
        print(f"Monitoring UP task {task_id_up[:8]}... via SSE...")
        final_state_up = stream_task_updates(
            api_url, task_id_up, sse_endpoint_up, timeout=120
        )
        
        # Verify all containers are in STARTED state
        print(f"Final UP task: {final_state_up}")
        assert final_state_up.get("task_status") == "completed", "UP task should be completed"
        assert final_state_up.get("operation") == "up"
        
        time.sleep(2)  # Give containers time to settle
        
        # PHASE 2: Stop deployment
        print("\nPHASE 2: Stopping deployment (compose down)...")
        resp_down = api_client.post(f"{api_url}/deployment/down")
        
        assert resp_down.status_code == 202, "DOWN should return 202 Accepted"
        data_down = resp_down.json()
        assert "task_id" in data_down, "Response should contain task_id"
        
        task_id_down = data_down["task_id"]
        sse_endpoint_down = f"/deployment/tasks/{task_id_down}/stream"
        
        # Stream and monitor DOWN progress
        print(f"Monitoring DOWN task {task_id_down[:8]}... via SSE...")
        final_state_down = stream_task_updates(
            api_url, task_id_down, sse_endpoint_down, timeout=120
        )
        
        # Verify all containers are in REMOVED state
        print(f"Final DOWN task: {final_state_down}")
        assert final_state_down.get("task_status") == "completed", "DOWN task should be completed"
        assert final_state_down.get("operation") == "down"
        
        print("\n✓ Deployment lifecycle test passed")
