# Plan: Endpoint para controlar ciclo de vida del deployment

Crear un nuevo endpoint REST que gestione el deployment completo mediante un modelo de estado deseado. La arquitectura utiliza `PUT /deployment` para cambiar el estado del deployment (running, stopped, restarting) respetando el patrón arquitectónico actual y best practices RESTful.

## Steps
1. Crear nueva clase `DeploymentRoutes` en nuevo archivo que siga el patrón de [ContainerRoutes](container_routes.py) e implemente transiciones de estado del deployment.
2. Agregar métodos en [ConfigService](config_service.py) para operaciones de compose (`docker_compose_up`, `docker_compose_down`, `docker_compose_restart`, `get_deployment_status`).
3. Registrar el nuevo router en [main.py](main.py) bajo prefijo `/deployment`.
4. Definir Pydantic models: `DeploymentStateRequest` (desired_state: "running"|"stopped"|"restarting"), `DeploymentStateResponse` (current_state, services_status, timestamp).
5. Implementar máquina de estados con validaciones: verificar variables antes de arrancar, respetar orden de dependencias, manejo de errores con logging.
6. Agregar `GET /deployment` para consultar estado actual del deployment (sin cambios).

## Implementation Details

### Transiciones de estado
`restarting` es una acción directa que internamente ejecuta stop + start en secuencia, garantizando limpieza antes de reinicio.

### Respuestas y Health checks
Los endpoints retornan inmediatamente sin bloquear (evita timeouts en requests de 30+ segundos). Las respuestas incluyen campo `transitioning: true` cuando hay cambios en progreso. El cliente usa `GET /deployment` para polling y verificar readiness de servicios.

### Eliminación de recursos
`DELETE /deployment` elimina la stack completa incluyendo volúmenes. `PUT /deployment` solo maneja transiciones de estado (running/stopped/restarting).

## API Endpoints

```
GET    /deployment              # Obtiene información sobre el deplyment y su estado actual
PUT    /deployment              # Cambia estado deseado (running|stopped|restarting)
DELETE /deployment              # Elimina deployment completo + volúmenes
```

## Request/Response Examples

### GET /deployment
**Response:**
```json
{
  "metadata": {
    "id": "4g-core",
    "name": "4G Core Network",
    "description": "Docker Compose configuration for a 4G Core Network using Open5GS components.",
    "version": "1.0",
    "author": "TKNIKA - www.tknika.eus",
    "changelog": "First release.",
    "documentation_url": ""
  },
  "current_state": "running",
  "desired_state": "running",
  "last_state_change": "2026-01-12T10:30:00Z"
}
```
*Nota: Para información detallada de contenedores, consultar `GET /containers`*

### PUT /deployment
**Request:**
```json
{
  "desired_state": "stopped"
}
```

**Response:**
```json
{
  "success": true,
  "desired_state": "stopped",
  "current_state": "running",
  "transitioning": true,
  "message": "Deployment stop initiated, services are shutting down"
}
```

### DELETE /deployment
**Response:**
```json
{
  "success": true,
  "message": "Deployment removed successfully",
  "removed_containers": ["mongo", "webui", "hss", "mme", "smf", "upf"],
  "removed_volumes": ["open5gs_db_data", "open5gs_logs"]
}
```
