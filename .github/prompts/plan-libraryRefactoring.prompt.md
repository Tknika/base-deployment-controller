# Plan: Convertir base-deployment-controller a Librería Reutilizable (src layout)

## Objetivo
Convertir el código actual en paquete Python distribible (`uv pip install base-deployment-controller`) que otros deployment-controllers puedan importar y extender, agregando nuevos endpoints FastAPI sin modificar el código base.

## Decisiones Confirmadas

### Estructura & Layout
- ✅ **Mantener src layout**: `src/base_deployment_controller/` (best practice para librerías)
- ✅ **main.py separado**: Permanece en raíz como aplicación demo ejecutable que importa la librería
- ✅ **data/ excluido**: compose.yaml y .env de prueba no se empaquetan

### Dependencias
- ✅ FastAPI, uvicorn, python-dotenv, pyyaml, websockets, python-on-whales: **required**
- ✅ Todos los deployment-controllers usarán FastAPI + uvicorn

### Exposición Pública
- ✅ Exportar routers base públicamente: `EnvRoutes`, `ContainerRoutes`, `DeploymentRoutes`
- ✅ Crear función factory `create_app()`
- ✅ Crear clase `AppBuilder` para composición avanzada
- ✅ Función `create_app()` instancia `ConfigService`, registra 3 routers base, retorna app lista

### Metadata
- ✅ `name = "base-deployment-controller"`
- ✅ `version = "0.1.0"`
- ✅ `author = "Tknika"`
- ✅ Re-exportar clases clave en `__init__.py` para backward compatibility

## Steps de Implementación

### 1. Crear `pyproject.toml`
**Archivo**: `pyproject.toml` en raíz
**Contenido**:
- Configuración de src layout: `packages = [{include = "base_deployment_controller", from = "src"}]`
- Dependencias required: fastapi, uvicorn, python-dotenv, pyyaml, websockets, python-on-whales
- Metadatos: nombre, versión, author, description, license
- Exclusiones: `data/`, `main.py`, tests, ejemplos (no se empaquetan)

### 2. Refactorizar estructura interna
**Archivos a revisar/ajustar**:
- `src/base_deployment_controller/__init__.py`: Actualmente vacío o imports simples
- `src/base_deployment_controller/routers/` y `models/` y `services/`: Ya bien estructurados
- **Acción**: Verificar imports internos, asegurar que no hay referencias circulares

### 3. Crear función factory `create_app()`
**Archivo**: `src/base_deployment_controller/__init__.py`
**Firma**:
```python
def create_app(
    compose_file: str = "compose.yaml",
    env_file: str = ".env",
    include_routers: bool = True
) -> FastAPI:
    """
    Factory function to create a preconfigured FastAPI application.
    
    Args:
        compose_file: Path to compose.yaml file
        env_file: Path to .env file
        include_routers: If True, registers base routers (envs, containers, deployment)
    
    Returns:
        FastAPI app ready to use or extend
    """
```
**Lógica interna**:
- Instancia `ConfigService(compose_file, env_file)`
- Crea `EnvRoutes(config)`, `ContainerRoutes(config)`, `DeploymentRoutes(config)`
- Incluye routers si `include_routers=True`
- Retorna `app`

### 4. Crear clase `AppBuilder`
**Archivo**: `src/base_deployment_controller/builder.py`
**Clase**: `AppBuilder`
**Métodos**:
- `__init__(compose_file: str, env_file: str)`: Constructor. Initializes ConfigService and creates base routers
- `register_router(router: APIRouter, prefix: str = "") → AppBuilder`: Registers a custom router, returns self (fluent pattern)
- `build() → FastAPI`: Compiles and returns app with all registered routers
- Internally: instantiates `ConfigService`, creates base routers, allows adding custom routers

**Ejemplo de uso** (para documentación):
```python
from base_deployment_controller import AppBuilder
from fastapi import APIRouter

app_builder = AppBuilder("compose.yaml", ".env")
my_custom_router = APIRouter(prefix="/custom")

app = (
    app_builder
    .register_router(my_custom_router)
    .build()
)
```

### 5. Refactorizar `main.py` (en raíz)
**Archivo**: `main.py` en raíz (NO se empaqueta)
**Acción**: Reescribir para usar `AppBuilder` o `create_app()` como demo pública
**Estructura**:
- Imports: `from base_deployment_controller import create_app` (o `AppBuilder`)
- Lee variables de entorno: `COMPOSE_FILE`, `ENV_FILE`, `API_PORT`, `LOG_LEVEL`
- Instancia app: `app = create_app(COMPOSE_FILE, ENV_FILE)`
- Bloque if `__name__ == "__main__"`: inicia uvicorn
- **Importante**: Este archivo demuestra cómo se usa la librería desde afuera

### 6. Actualizar `README.md`
**Secciones**:
1. **Descripción**: Qué es, para qué sirve
2. **Instalación**: `pip install base-deployment-controller` o `uv pip install base-deployment-controller`
3. **Uso Básico**: Función `create_app()`
   ```python
   from base_deployment_controller import create_app
   app = create_app()
   ```
4. **Uso Avanzado**: Clase `AppBuilder`
   ```python
   from base_deployment_controller import AppBuilder
   builder = AppBuilder("my-compose.yaml", "my-.env")
   app = builder.register_router(my_router).build()
   ```
5. **Extensión**: Cómo crear routers personalizados que se registran con la librería
6. **Estructura de Paquete**: Diagrama de src layout
7. **API Endpoints**: Documentación de GET /envs, POST /containers/{name}/control, etc.

### 7. Configurar exclusiones en empaquetamiento
**Archivo**: `pyproject.toml`
**Acción**: Usar campo `exclude` o `include` para excluir `data/`, `main.py`, `test_*.py`

**Ejemplo**:
```toml
[tool.setuptools]
packages = [{include = "base_deployment_controller", from = "src"}]

[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"
```

### 8. Re-exportar clases públicas en `__init__.py`
**Archivo**: `src/base_deployment_controller/__init__.py`
**Exports**:
```python
from .services.config import ConfigService
from .routers.environment import EnvRoutes
from .routers.container import ContainerRoutes
from .routers.deployment import DeploymentRoutes
from .builder import AppBuilder
from .factory import create_app  # o definir inline

__all__ = [
    "ConfigService",
    "EnvRoutes",
    "ContainerRoutes",
    "DeploymentRoutes",
    "AppBuilder",
    "create_app",
]
```

**Objetivo**: Usuarios pueden importar directamente:
```python
from base_deployment_controller import create_app, AppBuilder, ConfigService, EnvRoutes
```

## Validación Final

- [ ] `pyproject.toml` crea valid Python package
- [ ] `uv pip install -e .` instala librería en modo editable localmente
- [ ] `main.py` ejecutable usa librería: `python main.py` inicia servidor
- [ ] Imports públicos funcionan: `from base_deployment_controller import create_app`
- [ ] No hay archivos de prueba (`data/`, `test_*.py`) en distribución final
- [ ] `README.md` tiene ejemplos claros de instalación y extensión

## Additional Notes

- **All code docstrings must be in English** (classes, methods, attributes, functions)
- ConfigService remains agnostic (no changes required, only re-export)
- Routers remain the same, only re-exported publicly
- `main.py` is the living proof that the library is usable from outside
- Users can import `from base_deployment_controller import AppBuilder` and build their own app without touching base code
