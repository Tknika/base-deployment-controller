# Tests

Integration tests for the Base Deployment Controller API.

## Setup

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Or using uv:

```bash
uv pip install -e ".[dev]"
```

## Running Tests

### Run all tests

```bash
pytest tests/
```

### Run with verbose output

```bash
pytest tests/ -v
```

### Run specific test file

```bash
pytest tests/test_api_integration.py
```

### Run specific test class

```bash
pytest tests/test_api_integration.py::TestDeploymentEndpoints
```

### Run specific test

```bash
pytest tests/test_api_integration.py::TestContainerEndpoints::test_container_restart_with_verification
```

## Test Structure

- `conftest.py` - Pytest configuration and shared fixtures
- `test_api_integration.py` - Integration tests for all API endpoints

## Fixtures

Main fixtures defined in `conftest.py`:

- `api_url` - Base URL for the API (default: http://localhost:8000)
- `api_server` - Automatically starts/stops FastAPI server for tests
- `api_client` - HTTP session for making requests
- `check_dependencies` - Validates Python, Docker, and data files

## Requirements

- Python 3.8+
- Docker daemon running
- `data/compose.yaml` file present
- All dependencies in `pyproject.toml`

## Notes

- Tests automatically start and stop the FastAPI server
- Docker containers are brought up/down during tests
- Environment variables may be modified during tests (restored after)
- WebSocket tests require async support (pytest-asyncio)
