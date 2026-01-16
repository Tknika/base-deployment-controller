"""
Integration tests for base-deployment-controller API.

Covers:
- Deployment lifecycle (up/down)
- Container management and restart with started_at validation
- Environment variables CRUD
- WebSocket logs
"""
import time
from datetime import datetime, timezone
import asyncio
import pytest
import websockets


class TestDeploymentEndpoints:
    """Deployment endpoints."""

    def test_ping(self, api_client, api_url, check_dependencies):
        resp = api_client.get(f"{api_url}/ping")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert "message" in data

    def test_deployment_info(self, api_client, api_url):
        resp = api_client.get(f"{api_url}/")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "metadata" in data
        assert "env_vars" in data

    def test_deployment_up(self, api_client, api_url):
        resp = api_client.post(f"{api_url}/up")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        # Small delay for startup
        time.sleep(2)


class TestContainerEndpoints:
    """Container management endpoints."""

    def test_containers_list(self, api_client, api_url):
        resp = api_client.get(f"{api_url}/containers")
        assert resp.status_code == 200
        data = resp.json()
        assert "containers" in data
        assert len(data.get("containers", [])) > 0

    def test_container_restart_with_verification(self, api_client, api_url):
        container_name = "mongo"
        # Pre-condition: must be running
        pre = api_client.get(f"{api_url}/containers")
        assert pre.status_code == 200
        pre_data = pre.json()
        containers = pre_data.get("containers", [])
        mongo = next((c for c in containers if c.get("name") == container_name), None)
        assert mongo is not None, "Container 'mongo' not found"
        assert mongo.get("status") == "running"

        # Perform restart
        resp = api_client.post(
            f"{api_url}/containers/{container_name}/restart",
            json={"action": "restart"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True

        # Post-condition: wait for running status with recent started_at
        max_wait = 20
        start = time.time()
        new_mongo = None
        while time.time() - start < max_wait:
            post = api_client.get(f"{api_url}/containers")
            if post.status_code == 200:
                post_data = post.json()
                post_containers = post_data.get("containers", [])
                new_mongo = next((c for c in post_containers if c.get("name") == container_name), None)
                if new_mongo and new_mongo.get("status") == "running" and new_mongo.get("started_at"):
                    break
            time.sleep(0.5)

        assert new_mongo is not None, "mongo container not available after restart"
        assert new_mongo.get("status") == "running"
        started_at_str = new_mongo.get("started_at")
        assert started_at_str, "started_at missing"
        if started_at_str.endswith("Z"):
            started_at_str = started_at_str[:-1] + "+00:00"
        started_at = datetime.fromisoformat(started_at_str)
        delta = (datetime.now(timezone.utc) - started_at).total_seconds()
        assert delta >= 0
        assert delta <= 15, f"started_at too old ({delta:.2f}s)"


class TestEnvironmentVariables:
    """Environment variables endpoints."""

    def test_environment_variable_crud_cycle(self, api_client, api_url):
        """
        Complete GET/PUT cycle test for environment variables:
        - Initial GET to retrieve MCC value
        - PUT with opposite value
        - GET to verify change
        - PUT to restore original value
        - Final GET to verify restoration
        """
        # PHASE 1: Initial GET - retrieve current MCC value
        resp_initial = api_client.get(f"{api_url}/envs")
        assert resp_initial.status_code == 200
        data_initial = resp_initial.json()
        vars_initial = data_initial.get("variables", [])
        mcc_initial = next((v for v in vars_initial if v.get("name") == "MCC"), None)
        assert mcc_initial is not None
        original_value = mcc_initial.get("value")
        assert original_value in ["001", "214"], f"MCC must be 001 or 214, got: {original_value}"
        
        # PHASE 2: PUT with opposite value
        new_value = "214" if original_value == "001" else "001"
        payload_update = {"variables": {"MCC": new_value}, "restart_services": False}
        resp_update = api_client.put(f"{api_url}/envs", json=payload_update)
        assert resp_update.status_code == 200
        data_update = resp_update.json()
        assert data_update.get("success") is True
        assert "MCC" in data_update.get("updated", [])
        assert data_update.get("restarted_services") == {}
        
        # PHASE 3: GET to verify the change
        resp_after_change = api_client.get(f"{api_url}/envs")
        assert resp_after_change.status_code == 200
        data_after_change = resp_after_change.json()
        vars_after_change = data_after_change.get("variables", [])
        mcc_after_change = next((v for v in vars_after_change if v.get("name") == "MCC"), None)
        assert mcc_after_change is not None
        assert mcc_after_change.get("value") == new_value, \
            f"MCC must be {new_value}, got: {mcc_after_change.get('value')}"
        
        # PHASE 4: PUT to restore original value
        payload_restore = {"variables": {"MCC": original_value}}
        resp_restore = api_client.put(f"{api_url}/envs", json=payload_restore)
        assert resp_restore.status_code == 200
        data_restore = resp_restore.json()
        assert data_restore.get("success") is True
        assert "MCC" in data_restore.get("updated", [])
        assert data_restore.get("restarted_services") is not None
        time.sleep(2)  # Wait for service restart when restart_services defaults to true
        
        # PHASE 5: Final GET to verify restoration
        resp_final = api_client.get(f"{api_url}/envs")
        assert resp_final.status_code == 200
        data_final = resp_final.json()
        vars_final = data_final.get("variables", [])
        mcc_final = next((v for v in vars_final if v.get("name") == "MCC"), None)
        assert mcc_final is not None
        assert mcc_final.get("value") == original_value, \
            f"MCC must be restored to {original_value}, got: {mcc_final.get('value')}"


class TestWebSocket:
    """WebSocket log streaming."""

    async def test_websocket_logs(self, api_url):
        ws_url = api_url.replace("http", "ws") + "/containers/mongo/logs"
        async with websockets.connect(ws_url) as websocket:
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                assert len(msg) > 0
            except asyncio.TimeoutError:
                # No recent logs is also valid
                pass


class TestDeploymentLifecycle:
    """Complete shutdown/ping lifecycle."""

    def test_deployment_down(self, api_client, api_url):
        resp = api_client.post(f"{api_url}/down")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        time.sleep(2)

    def test_ping_after_shutdown(self, api_client, api_url):
        resp = api_client.get(f"{api_url}/ping")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
