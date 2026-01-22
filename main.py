"""
Base Deployment Controller - Demo application entry point.

Creates a FastAPI app using the library factory and starts uvicorn.
"""
import logging
import os

import uvicorn

from base_deployment_controller import create_app

# Configure logging
COMPOSE_FILE = os.getenv("COMPOSE_FILE", "data/compose.yaml")
ENV_FILE = os.getenv("ENV_FILE", "data/.env")
API_PORT = int(os.getenv("API_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# FastAPI Application
app = create_app(
    compose_file=COMPOSE_FILE,
    env_file=ENV_FILE,
)

if __name__ == "__main__":
    logger.info(f"Starting Base Deployment Controller on http://0.0.0.0:{API_PORT}")
    logger.info(f"Log level set to: {LOG_LEVEL}")
    uvicorn.run("main:app", host="0.0.0.0", port=API_PORT, reload=True)
