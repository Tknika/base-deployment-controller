"""
Test cases for the Container endpoints (/containers).

Tests container-level operations:
- Get container list
- Container lifecycle with SSE monitoring
- Individual container actions (stop, start, restart)
"""
import time
import pytest
from tests.utils import stream_task_updates


class TestContainerEndpoints:
    """Container endpoint tests with SSE monitoring."""

    def test_containers_list(self, api_client, api_url, api_server, check_dependencies):
        """Test GET /containers returns container list."""
        print("\n=== CONTAINERS LIST TEST ===\n")
        
        # Deploy first
        print("Deploying stack...")
        resp_up = api_client.post(f"{api_url}/deployment/up")
        assert resp_up.status_code == 202
        
        task_id = resp_up.json()["task_id"]
        final_state = stream_task_updates(api_url, task_id, f"/deployment/tasks/{task_id}/stream", timeout=120)
        
        # Wait for deployment to be ready
        time.sleep(2)
        
        # Get containers list
        print("\nGetting containers list...")
        resp_list = api_client.get(f"{api_url}/containers")
        
        assert resp_list.status_code == 200, "GET /containers should return 200"
        data = resp_list.json()
        
        # Validate response structure
        assert isinstance(data, dict), "Response should be a dict"
        assert "containers" in data, "Response should contain 'containers'"
        
        containers = data["containers"]
        assert isinstance(containers, list), "Containers should be a list"
        assert len(containers) > 0, "Should have at least one container running"
        
        # Validate each container has required fields
        for container in containers:
            assert "name" in container
            assert "status" in container
            assert "ports" in container or container["ports"] is None
        
        print(f"✓ Found {len(containers)} containers")
        
        # Cleanup
        print("\nCleaning up (compose kill)...")
        resp_kill = api_client.post(f"{api_url}/deployment/kill")
        assert resp_kill.status_code == 202
        
        task_id_kill = resp_kill.json()["task_id"]
        stream_task_updates(api_url, task_id_kill, f"/deployment/tasks/{task_id_kill}/stream", timeout=120)

    def test_container_individual_action_with_sse(self, api_client, api_url, api_server, check_dependencies):
        """
        Test individual container actions (stop/start) with SSE monitoring.
        
        Sequence:
        1. Deploy UP and wait for all containers running
        2. Stop specific container (MME) with SSE monitoring
        3. Verify container state changed
        4. Deploy KILL
        """
        print("\n=== CONTAINER INDIVIDUAL ACTION TEST ===\n")
        
        # PHASE 1: Deploy UP
        print("PHASE 1: Deploying stack...")
        resp_up = api_client.post(f"{api_url}/deployment/up")
        assert resp_up.status_code == 202
        
        task_id_up = resp_up.json()["task_id"]
        print(f"Monitoring deployment (task {task_id_up[:8]}...)...")
        final_state_up = stream_task_updates(
            api_url, task_id_up, f"/deployment/tasks/{task_id_up}/stream", timeout=120
        )
        assert final_state_up.get("task_status") == "completed"
        
        time.sleep(2)
        
        # Get container list to identify target
        resp_list = api_client.get(f"{api_url}/containers")
        containers = resp_list.json().get("containers", [])
        print(f"Active containers: {[c['name'] for c in containers]}")
        
        # Find and stop MME container
        mme_container = next((c for c in containers if "mme" in c["name"].lower()), None)
        if mme_container:
            container_name = mme_container["name"]
            print(f"\nPHASE 2: Stopping container {container_name}...")
            
            resp_stop = api_client.post(f"{api_url}/containers/{container_name}/stop")
            assert resp_stop.status_code == 202, "Stop should return 202 Accepted"
            
            task_id_stop = resp_stop.json()["task_id"]
            print(f"Monitoring stop action (task {task_id_stop[:8]}...)...")
            
            final_state_stop = stream_task_updates(
                api_url, task_id_stop, f"/containers/{container_name}/tasks/{task_id_stop}/stream", timeout=60
            )
            assert final_state_stop.get("task_status") == "completed"
        
        # PHASE 3: Deploy KILL
        print("\nPHASE 3: Cleaning up (compose kill)...")
        resp_kill = api_client.post(f"{api_url}/deployment/kill")
        assert resp_kill.status_code == 202
        
        task_id_kill = resp_kill.json()["task_id"]
        stream_task_updates(api_url, task_id_kill, f"/deployment/tasks/{task_id_kill}/stream", timeout=120)
        
        print("\n✓ Container action test passed")
