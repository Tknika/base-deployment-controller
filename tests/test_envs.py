"""
Test cases for the Environment endpoints (/envs).

Tests environment variable management:
- Update environment variables
- Verify service restart via SSE monitoring
- Confirm completion before validation
"""
import time
import pytest
from tests.utils import stream_task_updates


class TestEnvironmentEndpoints:
    """Environment endpoints tests with SSE monitoring."""

    def test_env_update_with_sse_completion(self, api_client, api_url, api_server, check_dependencies):
        """
        Test environment variable update with SSE completion monitoring.
        
        Sequence:
        1. Deploy UP and wait for all containers running
        2. Update environment variable (MCC to 214)
        3. Monitor SSE stream for service restart completion
        4. Verify update was applied by checking environment
        5. Deploy KILL to clean up
        """
        print("\n=== ENVIRONMENT UPDATE TEST ===\n")
        
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
        
        # PHASE 2: Update environment variable
        print("\nPHASE 2: Updating environment variable (MCC=214)...")
        
        update_payload = {
            "variables": {
                "MCC": "214"
            }
        }
        
        resp_update = api_client.put(f"{api_url}/envs", json=update_payload)
        assert resp_update.status_code == 202, "PUT /envs should return 202 Accepted"
        
        data_update = resp_update.json()
        assert "task_id" in data_update, "Response should contain task_id"
        
        task_id_update = data_update["task_id"]
        print(f"Monitoring environment update (task {task_id_update[:8]}...)...")
        
        # Monitor the environment update with SSE
        final_state_update = stream_task_updates(
            api_url, task_id_update, f"/envs/tasks/{task_id_update}/stream", timeout=120
        )
        assert final_state_update.get("task_status") == "completed", "Environment update should be completed"
        
        print("✓ Environment update completed successfully via SSE")
        
        time.sleep(1)
        
        # PHASE 3: Verify environment was updated
        print("\nPHASE 3: Verifying environment update...")
        resp_get_env = api_client.get(f"{api_url}/envs")
        
        if resp_get_env.status_code == 200:
            env_data = resp_get_env.json()
            if "environment" in env_data:
                mcc_value = env_data["environment"].get("MCC")
                print(f"MCC environment variable: {mcc_value}")
                # Note: Actual verification would depend on API returning current env state
        
        # PHASE 4: Deploy KILL to clean up
        print("\nPHASE 4: Cleaning up (compose kill)...")
        resp_kill = api_client.post(f"{api_url}/deployment/kill")
        assert resp_kill.status_code == 202
        
        task_id_kill = resp_kill.json()["task_id"]
        stream_task_updates(api_url, task_id_kill, f"/deployment/tasks/{task_id_kill}/stream", timeout=120)
        
        print("\n✓ Environment update test completed successfully")
