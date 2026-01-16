# Base Deployment Controller

REST API para la gestión básica de un deployment.

## Características

- **Gestión del deployment**: Inicia, detiene y borrar el deploy (`compose.yaml`)
- **Gestión de variables de entorno**: Lee configuración de `x-env-vars` en `compose.yaml` y permite actualizar valores en `.env`
- **Control de contenedores**: Inicia, detiene y reinicia contenedores del deploy
- **Logs en tiempo real**: WebSocket para streaming de logs de contenedores
- **Validación de tipos**: Valida automáticamente valores según schemas (regex, rangos, enums)

## Requisitos

- Python 3.8+
- Docker y Docker Compose

## Instalación

```bash
# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar como librería
pip install base-deployment-controller
```

## Uso

### Iniciar el servidor (demo)

```bash
# Ejecutar la app demo desde la raíz del repo
python3 main.py
```

El servidor estará disponible en `http://localhost:8000`

### Uso como librería

#### Uso básico (factory)

```python
from base_deployment_controller import create_app

app = create_app(
  compose_file="compose.yaml",
  env_file=".env",
)
```

#### Uso avanzado (builder + routers personalizados)

```python
from fastapi import APIRouter
from base_deployment_controller import AppBuilder

custom_router = APIRouter(prefix="/custom")

builder = AppBuilder("compose.yaml", ".env")
app = builder.register_router(custom_router).build()
```

### API Endpoints

#### GET /
Obtiene información sobre el deploy:

```bash
curl http://localhost:8000/
```

#### POST /up|down|stop
Controla el deploy:

```bash
# Levanta todos los servicio del deploy
curl -X POST http://localhost:8000/up
```

#### GET /envs
Obtiene todas las variables de entorno con sus valores actuales:

```bash
curl http://localhost:8000/envs
```

#### PUT /envs
Actualiza variables de entorno. Usa `restart_services` (por defecto `true`) para controlar si se reinician los servicios afectados.

```bash
# Actualización múltiple
curl -X PUT http://localhost:8000/envs \
  -H "Content-Type: application/json" \
  -d '{"variables": {"MCC": "214", "MNC": "07"}, "restart_services": false}'
```

#### GET /containers
Lista el estado de todos los contenedores:

```bash
curl http://localhost:8000/containers
```

#### POST /containers/{name}/start|stop|restart
Controla un contenedor específico:

```bash
# Reiniciar el MME
curl -X POST http://localhost:8000/containers/mme/restart
```

#### WebSocket /containers/{container_name}/logs
Logs en tiempo real via WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:8000/containers/mme/logs');
ws.onmessage = (event) => {
  console.log(event.data);
};
```

#### GET /ping
Health check del servicio:

```bash
curl http://localhost:8000/ping
```

## Documentación Interactiva

FastAPI genera automáticamente documentación interactiva:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Arquitectura

### Configuración de Tres Niveles

1. **compose.yaml**: Define servicios y dependencias
2. **x-env-vars**: Schema maestro con validaciones
3. **.env**: Valores en tiempo de ejecución

## Validación de Tipos

Las variables se validan según el schema de `x-env-vars`:

- **String con regex**: `"string:0;^\d{3}$"` - MCC debe ser 3 dígitos
- **Integer con rango**: `"integer:0;2048"` - MAX_NUM_UE entre 0-2048
- **Enum**: `"enum:tun,tap"` - UPF_TUNTAP_MODE solo acepta tun o tap

## Seguridad

- Solo permite actualizar variables existentes en el schema
- No permite agregar nuevas variables
- No permite eliminar variables
- Valida todos los valores antes de escribir en `.env`

## Licencia

Este proyecto es parte del controlador de despliegue 5G de Tknika.
