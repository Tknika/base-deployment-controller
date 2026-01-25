"""
Test cases for the API root endpoint (GET /).
"""
import pytest


class TestAPIEndpoint:
    """API root endpoint tests."""

    def test_api_root_operational(self, api_client, api_url, api_server, check_dependencies):
        """
        Verify that the API root endpoint returns operational status.
        
        Tests:
        - GET / returns status 200
        - Response contains "status": "operational"
        - Response contains valid API information
        """
        resp = api_client.get(f"{api_url}/")
        
        assert resp.status_code == 200, "Root endpoint should return 200"
        
        data = resp.json()
        assert data.get("status") == "operational", "API status should be 'operational'"
        assert "name" in data, "Response should contain API name"
        assert "message" in data, "Response should contain status message"
        assert data.get("name") == "Base Deployment Controller", "API name should be 'Base Deployment Controller'"
