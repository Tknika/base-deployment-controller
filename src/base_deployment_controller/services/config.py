"""
Configuration service module.
Manages reading/writing .env and compose.yaml, validation and Docker client.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import re
import logging
import time

import yaml
from dotenv import dotenv_values, set_key
from python_on_whales import DockerClient

from ..models.deployment import DeploymentStatus, DeploymentMetadata
from ..models.compose import ComposeActionResponse

logger = logging.getLogger(__name__)


class ConfigService:
    """
    Configuration and Docker access service.

    Centralizes reading/writing of `.env` and `compose.yaml`, validation
    of variables according to `x-env-vars`, and Docker client access.

    Args:
        compose_file: Path to Docker Compose file (default "compose.yaml").
        env_file: Path to environment variables file (default ".env").

    Attributes:
        compose_path: Path to compose.yaml file as `Path`.
        env_path: Path to .env file as `Path`.
        compose_schema: Parsed compose.yaml content as dictionary.
        compose_services: Services section from compose.yaml.
        env_to_services_map: Mapping of environment variables to services that use them.
    """

    def __init__(self, compose_file: str = "compose.yaml", env_file: str = ".env") -> None:
        """
        Initialize the configuration service.

        Args:
            compose_file: Path to Docker Compose file.
            env_file: Path to environment variables file.

        Raises:
            FileNotFoundError: If compose file doesn't exist.
        """
        self.compose_path = Path(compose_file)
        self.env_path = Path(env_file)
        self.compose_schema: Dict[str, Any] = self._load_compose_schema()
        self.compose_services: Dict[str, Any] = self._load_compose_services()
        self.env_to_services_map: Dict[str, List[str]] = self._build_env_to_services_map()

    def _load_compose_schema(self) -> Dict[str, Any]:
        """
        Load and parse the compose.yaml file.

        Returns:
            Dict containing the parsed compose.yaml content.

        Raises:
            FileNotFoundError: If compose.yaml doesn't exist.
            yaml.YAMLError: If YAML parsing fails.
        """
        if not self.compose_path.exists():
            raise FileNotFoundError(f"Compose file not found: {self.compose_path}")
        with open(self.compose_path, "r") as f:
            return yaml.safe_load(f)

    def _load_compose_services(self) -> Dict[str, Any]:
        """
        Load services section from compose.yaml.

        Returns:
            Dictionary containing service definitions from compose.yaml.
        """
        try:
            compose = self.compose_schema
            return compose.get("services", {})
        except Exception as e:
            logger.warning(f"Failed to load services from compose.yaml: {e}")
            return {}

    # File Operations
    def _build_env_to_services_map(self) -> Dict[str, List[str]]:
        """
        Build a mapping of environment variables to services that use them.

        Parses the compose.yaml to identify which services reference each environment
        variable in their environment section or network configuration.

        Returns:
            Dict mapping environment variable names to list of service names that use them.
        """
        env_to_services: Dict[str, List[str]] = {}

        try:
            services = self.compose_services

            # Pattern to match ${VAR_NAME} in strings
            env_var_pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

            for service_name, service_config in services.items():
                # Check environment variables section
                environment = service_config.get("environment", [])
                if isinstance(environment, dict):
                    # Dict format: key: value
                    for key, value in environment.items():
                        if isinstance(value, str):
                            matches = env_var_pattern.findall(value)
                            for var_name in matches:
                                if var_name not in env_to_services:
                                    env_to_services[var_name] = []
                                if service_name not in env_to_services[var_name]:
                                    env_to_services[var_name].append(service_name)
                elif isinstance(environment, list):
                    # List format: ["KEY=value", ...]
                    for entry in environment:
                        if isinstance(entry, str):
                            matches = env_var_pattern.findall(entry)
                            for var_name in matches:
                                if var_name not in env_to_services:
                                    env_to_services[var_name] = []
                                if service_name not in env_to_services[var_name]:
                                    env_to_services[var_name].append(service_name)

                # Check network configuration (IPv4 addresses often use env vars)
                networks = service_config.get("networks", {})
                if isinstance(networks, dict):
                    for network_name, network_config in networks.items():
                        if isinstance(network_config, dict):
                            ipv4_addr = network_config.get("ipv4_address", "")
                            if isinstance(ipv4_addr, str):
                                matches = env_var_pattern.findall(ipv4_addr)
                                for var_name in matches:
                                    if var_name not in env_to_services:
                                        env_to_services[var_name] = []
                                    if service_name not in env_to_services[var_name]:
                                        env_to_services[var_name].append(service_name)

                # Check ports configuration
                ports = service_config.get("ports", [])
                for port_mapping in ports:
                    if isinstance(port_mapping, str):
                        matches = env_var_pattern.findall(port_mapping)
                        for var_name in matches:
                            if var_name not in env_to_services:
                                env_to_services[var_name] = []
                            if service_name not in env_to_services[var_name]:
                                env_to_services[var_name].append(service_name)

        except Exception as e:
            # If we can't build the map, log the error but don't fail initialization
            logger.warning(f"Failed to build env-to-services map: {e}")
            return {}

        return env_to_services

    def get_env_vars_schema(self) -> Dict[str, Dict[str, Any]]:
        """
        Extract the x-env-vars schema from compose.yaml.

        Returns:
            Dict mapping variable names to their metadata.
        """
        compose = self.compose_schema
        return compose.get("x-env-vars", {})

    def load_env_values(self) -> Dict[str, Optional[str]]:
        """
        Load current values from .env file.

        Returns:
            Dict mapping variable names to their current values.
        """
        if not self.env_path.exists():
            return {}
        return dict(dotenv_values(self.env_path))

    def update_env_file(self, updates: Dict[str, str]) -> None:
        """
        Update variables in .env file atomically.
        Only modifies specified variables, preserves others and comments.

        Args:
            updates: Dict mapping variable names to new values.

        Raises:
            IOError: If file operations fail.
        """
        if not self.env_path.exists():
            self.env_path.touch()
        for key, value in updates.items():
            set_key(self.env_path, key, value)

    # Validation
    def parse_type_constraint(self, type_str: str) -> Dict[str, Any]:
        """
        Parse the type constraint string from x-env-vars.

        Format examples:
            - "string:0;^\\d{3}$" -> string with regex pattern (0 = show in UI, 1 = do not show)
            - "integer:0;2048" -> integer with min/max bounds
            - "enum:tun,tap" -> enum with allowed values

        Args:
            type_str: Type constraint string.

        Returns:
            Dict with parsed constraint information.
        """
        parts = type_str.split(":", 1)
        type_name = parts[0]
        result: Dict[str, Any] = {"type": type_name}
        if len(parts) > 1:
            constraint = parts[1]
            if type_name == "string":
                cp = constraint.split(";", 1)
                if len(cp) == 2:
                    result["hide"] = bool(int(cp[0]))
                    result["pattern"] = cp[1]
            elif type_name == "integer":
                cp = constraint.split(";")
                if len(cp) == 2:
                    result["min"] = int(cp[0])
                    result["max"] = int(cp[1])
            elif type_name == "enum":
                result["values"] = constraint.split(",")
        return result

    def validate_variable_value(self, name: str, value: str, type_str: str) -> None:
        """
        Validate a variable value against its type constraint.

        Args:
            name: Variable name.
            value: Value to validate.
            type_str: Type constraint string from x-env-vars.

        Raises:
            ValueError: If validation fails.
        """
        constraint = self.parse_type_constraint(type_str)
        if constraint["type"] == "string":
            pattern = constraint.get("pattern")
            if pattern and not re.match(pattern, value):
                raise ValueError(
                    f"Variable '{name}' value '{value}' doesn't match pattern {pattern}"
                )
        elif constraint["type"] == "integer":
            try:
                int_value = int(value)
            except ValueError:
                raise ValueError(f"Variable '{name}' must be an integer, got '{value}'")
            if "min" in constraint and int_value < constraint["min"]:
                raise ValueError(
                    f"Variable '{name}' value {int_value} is below minimum {constraint['min']}"
                )
            if "max" in constraint and int_value > constraint["max"]:
                raise ValueError(
                    f"Variable '{name}' value {int_value} exceeds maximum {constraint['max']}"
                )
        elif constraint["type"] == "enum":
            values = constraint.get("values", [])
            if values and value not in values:
                raise ValueError(
                    f"Variable '{name}' value '{value}' not in allowed values: {values}"
                )

    def get_service_dependencies(self, service_name: str) -> List[str]:
        """
        Extract service dependencies from compose.yaml.

        Args:
            service_name: Name of the service.

        Returns:
            List of service names this service depends on.
        """
        service = self.compose_services.get(service_name, {})
        depends_on = service.get("depends_on", [])
        if isinstance(depends_on, dict):
            return list(depends_on.keys())
        return depends_on

    def get_container_name_by_service(self, service_name: str) -> str:
        """
        Get the container name for a given service from compose.yaml.

        Args:
            service_name: Name of the service.

        Returns:
            Container name if specified, else service name.
        """
        service = self.compose_services.get(service_name, {})
        return service.get("container_name", "")

    # Docker
    def get_docker_client(self) -> DockerClient:
        """
        Get Docker client instance.

        Returns:
            Docker client connected to local daemon.
        """
        docker = DockerClient(compose_files=[str(self.compose_path)])
        return docker

    def get_affected_services(self, changed_vars: List[str]) -> List[str]:
        """
        Get list of services affected by changes to specific environment variables.

        Args:
            changed_vars: List of environment variable names that changed.

        Returns:
            List of unique service names that use any of the changed variables.
        """
        affected_services = set()
        for var_name in changed_vars:
            services = self.env_to_services_map.get(var_name, [])
            affected_services.update(services)
        return list(affected_services)

    def recreate_services(self, service_names: List[str]) -> Dict[str, bool]:
        """
        Recreate specified Docker services/containers.

        Args:
            service_names: List of service names from compose.yaml to recreate.

        Returns:
            Dict mapping service names to recreate success status (True/False).
        """
        results: Dict[str, bool] = {}

        if not service_names:
            return results

        try:
            client = self.get_docker_client()

            for service_name in service_names:
                # Get container name from service
                container_name = self.get_container_name_by_service(service_name)
                if not container_name:
                    results[service_name] = False
                    continue

                try:
                    if client.container.exists(container_name):
                        # Only recreate if container exists
                        container_inspect = client.container.inspect(container_name)
                        if container_inspect.state.status == "running":
                            # Recreate service container to apply environment changes.
                            # Equivalent intent to: docker compose rm -f -s <service> && docker compose up -d <service>
                            client.compose.rm(services=[service_name], stop=True)
                            client.compose.up(detach=True, services=[service_name])
                            results[service_name] = True
                        else:
                            # Container exists but not running, don't recreate
                            results[service_name] = False
                    else:
                        # Container doesn't exist, can't recreate
                        results[service_name] = False
                except Exception as e:
                    logger.error(f"Error recreating service {service_name}: {e}")
                    results[service_name] = False

        except Exception as e:
            logger.error(f"Error in recreate_services: {e}")

        return results

    # Docker Compose Operations
    def get_deployment_metadata(self) -> DeploymentMetadata:
        """
        Extract metadata from x-metadata section in compose.yaml.

        Returns:
            Dict with deployment metadata (id, name, description, version, author, changelog, documentation_url).
        """
        compose = self.compose_schema
        metadata = compose.get("x-metadata", {})
        return DeploymentMetadata(
            id=metadata.get("id", "unknown"),
            name=metadata.get("name", "Unknown"),
            description=metadata.get("description", ""),
            version=metadata.get("version", "1.0"),
            author=metadata.get("author", ""),
            changelog=metadata.get("changelog", ""),
            documentation_url=metadata.get("documentation_url", ""),
        )

    def get_deployment_status(self) -> DeploymentStatus:
        """
        Get current deployment status by checking if services are running.

        Analyzes Docker containers and determines overall deployment state:
        - "running": All or most critical services are running
        - "partially_running": Some services are running but others are stopped
        - "stopped": All services are stopped
        - "unknown": Unable to determine overall state

        Returns:
            Dict with current_state, desired_state, transitioning, and last_state_change.
        """
        services = self.compose_services
        if not services:
            return DeploymentStatus.UNKNOWN

        client = self.get_docker_client()
        running = 0
        total = 0

        for service_name, service_config in services.items():
            container_name = service_config.get("container_name", service_name)
            total += 1
            if client.container.exists(container_name):
                container_inspect = client.container.inspect(container_name)
                if container_inspect.state.status == "running":
                    running += 1

        if running == 0:
            return DeploymentStatus.STOPPED
        elif running == total:
            return DeploymentStatus.RUNNING
        else:
            return DeploymentStatus.PARTIALLY_RUNNING

    def docker_compose_up(self) -> ComposeActionResponse:
        """
        Execute docker compose up and return the result.

        Returns:
            ComposeActionResponse with success status and message.
        """
        try:
            client = self.get_docker_client()
            client.compose.up(detach=True)
            return ComposeActionResponse(
                success=True,
                message="Deployment started successfully",
            )
        except Exception as e:
            logger.error(f"Failed to start deployment: {e}")
            return ComposeActionResponse(
                success=False,
                message=str(e),
            )

    def docker_compose_stop(self) -> ComposeActionResponse:
        """
        Execute docker compose stop and return the result.

        Returns:
            ComposeActionResponse with success status and message.
        """
        try:
            client = self.get_docker_client()
            client.compose.stop()
            return ComposeActionResponse(
                success=True,
                message="Deployment stopped successfully",
            )
        except Exception as e:
            logger.error(f"Failed to stop deployment: {e}")
            return ComposeActionResponse(
                success=False,
                message=str(e),
            )

    def docker_compose_down(self) -> ComposeActionResponse:
        """
        Execute docker compose down and return the result.

        Returns:
            ComposeActionResponse with success status and message
        """
        try:
            client = self.get_docker_client()
            client.compose.down(volumes=True)
            return ComposeActionResponse(
                success=True,
                message="Deployment downed successfully"
            )
        except Exception as e:
            logger.error(f"Failed to down deployment: {e}")
            return ComposeActionResponse(
                success=False,
                message=str(e)
            )
        
    def docker_compose_kill(self) -> ComposeActionResponse:
        """
        Execute docker compose kill and return the result.

        Returns:
            ComposeActionResponse with success status and message.
        """
        try:
            client = self.get_docker_client()
            client.compose.kill()
            return ComposeActionResponse(
                success=True,
                message="Deployment killed successfully",
            )
        except Exception as e:
            logger.error(f"Failed to kill deployment: {e}")
            return ComposeActionResponse(
                success=False,
                message=str(e),
            )

    def docker_compose_restart(self) -> ComposeActionResponse:
        """
        Execute docker compose stop then up and return the result.

        Returns:
            ComposeActionResponse with success status and message.
        """
        try:
            down_result = self.docker_compose_stop()
            if not down_result.success:
                return ComposeActionResponse(
                    success=False,
                    message=down_result.message,
                )
            up_result = self.docker_compose_up()
            return ComposeActionResponse(
                success=up_result.success,
                message=up_result.message,
            )
        except Exception as e:
            logger.error(f"Failed to restart deployment: {e}")
            return ComposeActionResponse(
                success=False,
                message=str(e),
            )

    def wait_for_containers(self, service_names: List[str], timeout: int = 60) -> Dict[str, bool]:
        """
        Wait for specified containers to become running.

        Args:
            service_names: List of service names to wait for.
            timeout: Timeout in seconds.

        Returns:
            Dict mapping service names to True if running, False otherwise.
        """
        start_time = time.time()
        results: Dict[str, bool] = {}

        while time.time() - start_time < timeout:
            all_running = True
            for service_name in service_names:
                container_name = self.get_container_name_by_service(service_name)
                if not container_name:
                    results[service_name] = False
                    all_running = False
                    continue
                client = self.get_docker_client()
                if not client.container.exists(container_name):
                    results[service_name] = False
                    all_running = False
                    continue
                container_inspect = client.container.inspect(container_name)
                if container_inspect.state.status != "running":
                    results[service_name] = False
                    all_running = False
                    continue
                results[service_name] = True

            if all_running:
                return results

            time.sleep(2)

        return results
