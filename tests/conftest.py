"""
Pytest configuration and shared fixtures for integration tests.
"""
import os
import subprocess
import time
from pathlib import Path

import pytest
import requests


@pytest.fixture(scope="session")
def api_url():
    """Base URL for the API."""
    return "http://localhost:8000"


@pytest.fixture(scope="session")
def compose_data_dir():
    """Path to the compose data directory."""
    return Path("data")


@pytest.fixture(scope="session")
def api_server(api_url):
    """
    Start the FastAPI server for the test session.
    
    This fixture starts the server once at the beginning of the test session
    and stops it at the end. The server is started from the project root directory
    to ensure proper resolution of relative paths like 'data/compose.yaml'.
    """
    import sys
    
    # Change to project root to ensure correct working directory for relative paths
    project_root = Path(__file__).parent.parent
    original_cwd = os.getcwd()
    
    # Start server from project root
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", 
         "main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(project_root)  # Execute from project root
    )
    
    # Wait for server to be ready
    session = requests.Session()
    start_time = time.time()
    timeout = 60
    
    while time.time() - start_time < timeout:
        try:
            response = session.get(f"{api_url}/ping", timeout=2)
            if response.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.5)
    else:
        process.terminate()
        process.wait()
        pytest.fail(f"Server did not start within {timeout} seconds")
    
    yield process
    
    # Teardown: stop server
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture(scope="function")
def api_client(api_url, api_server):
    """HTTP client session for API requests."""
    session = requests.Session()
    yield session
    session.close()


@pytest.fixture(scope="session")
def check_dependencies(compose_data_dir):
    """Verify system dependencies before running tests."""
    import sys
    
    # Check Python version
    if sys.version_info < (3, 8):
        pytest.fail("Python 3.8+ required")
    
    # Check Docker
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            pytest.fail("Docker not found")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.fail("Docker not available")
    
    # Check Docker daemon
    try:
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            pytest.fail("Docker daemon not running")
    except subprocess.TimeoutExpired:
        pytest.fail("Docker daemon timeout")
    
    # Check data folder structure
    if not compose_data_dir.exists():
        pytest.fail(f"Data directory '{compose_data_dir}' not found")
    
    compose_file = compose_data_dir / "compose.yaml"
    if not compose_file.exists():
        pytest.fail(f"Compose file not found: {compose_file}")
    
    return True
