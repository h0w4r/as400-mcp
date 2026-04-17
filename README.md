# Servidor MCP para AS400

Este es un servidor MCP de apoyo al desarrollo sobre AS400/IBM i para Claude Code.
Obtiene metadatos y codigo fuente de AS400 a traves de ODBC y ayuda en el desarrollo de programas CL/RPG/COBOL.

## Caracteristicas

- **Compatibilidad con etiquetas en japones**: obtiene y aprovecha las descripciones en japones (TEXT) de columnas y tablas.
- **Consulta de codigo fuente**: permite obtener fuentes desde QCLSRC, QRPGSRC y archivos similares.
- **Analisis de dependencias de programas**: obtiene archivos referenciados y relaciones de invocacion.
- **Obtencion de informacion del sistema**: permite revisar version de OS, nivel de PTF y otros datos.
- **Solo lectura**: por seguridad, todas las operaciones son exclusivamente de lectura.

## Cambios incluidos en este repo

Comparado contra el repositorio fuente del fork [`kozokaAI/as400-mcp`](https://github.com/kozokaAI/as400-mcp), esta version incluye los siguientes ajustes propios:

- **Instrumentacion y logging seguro para MCP** en `src/as400_mcp/server.py`:
  - se agrego logging a archivo para no contaminar `stdin/stdout` del protocolo MCP;
  - se incorporaron variables de entorno para controlar ruta, nivel y detalle del log (`AS400_MCP_LOG`, `AS400_MCP_LOG_LEVEL`, `AS400_MCP_LOG_STDERR`, `AS400_MCP_LOG_SQL`);
  - se agregaron trazas de inicio/fin/error por tool con identificador de llamada y medicion de tiempo.
- **Diagnostico mejorado de ODBC/DB2** en `src/as400_mcp/server.py`:
  - se agregaron wrappers `odbc_execute`, `odbc_fetchall` y `odbc_fetchone` para registrar tiempos de conexion, ejecucion y lectura;
  - se soportan timeouts configurables con `AS400_MCP_SQL_TIMEOUT` y `AS400_MCP_CONNECT_TIMEOUT`;
  - la cadena de conexion se resume y se enmascara al registrar credenciales sensibles.
- **Manejo robusto de errores en `execute_sql`**:
  - se reforzo la validacion para permitir solo un `SELECT`;
  - se detectan errores frecuentes de DB2 for i y se devuelven respuestas estructuradas con `ok`, `error`, `debug_id` y `hint`;
  - se evita que errores SQL u ODBC dejen colgado al cliente MCP;
  - se agregaron advertencias heuristicas para casos comunes como lectura de CLOB desde `QSYS2.IFS_READ*`.
- **Mejoras en lectura de fuentes IBM i con `get_source`**:
  - se ajusto la conversion de `SRCDTA` a UTF-8 mediante `CAST ... CCSID` para reducir problemas de encoding;
  - se mejoro el tratamiento de `memoryview` y `bytes`;
  - se preserva mejor la indentacion al evitar eliminar espacios a la izquierda del codigo fuente.
- **Decoracion de tools con trazabilidad**:
  - varias tools ahora estan envueltas con `@log_tool` para registrar argumentos, duracion y resultado resumido.
- **Documentacion en espanol**:
  - este `README.md` fue traducido al espanol para facilitar mantenimiento y adopcion local.
- **Ajuste de `.gitignore`**:
  - se agrego `src/as400_mcp/server - copia.py` para evitar versionar un respaldo local que no forma parte del codigo activo.

## Herramientas disponibles

| Herramienta | Descripcion |
|--------|------|
| `list_libraries` | Lista de librerias (con etiqueta) |
| `list_tables` | Lista de tablas/archivos |
| `get_columns` | Lista de columnas (etiquetas en japones, tipo, informacion de claves) |
| `list_source_files` | Lista de archivos fuente (QCLSRC, QRPGSRC, etc.) |
| `list_sources` | Lista de miembros fuente |
| `get_source` | Obtiene el codigo fuente |
| `get_data` | Obtiene datos de tabla |
| `get_table_info` | Informacion detallada de la tabla |
| `get_system_info` | Informacion del sistema (version del OS, PTF, etc.) |
| `list_programs` | Lista de programas (RPG/CL/COBOL, etc.) |
| `get_program_references` | Archivos referenciados y relaciones de invocacion de un programa |
| `list_data_areas` | Lista de areas de datos (variables compartidas) |
| `execute_sql` | Ejecuta un SELECT arbitrario (solo lectura) |

## Instalacion

### Requisitos previos

- Python 3.10 o superior
- IBM i Access ODBC Driver
- AS400/IBM i 7.3 o superior (recomendado: 7.4 o superior)
  - 7.3: las funciones basicas estan disponibles
  - 7.4+: se pueden usar funciones adicionales como `get_program_references`
- Informacion de conexion al AS400/IBM i

### Pasos de instalacion

```bash
# 1. Clonar el repositorio
git clone https://github.com/omni-s/as400-mcp.git
cd as400-mcp

# 2. Crear y activar el entorno virtual
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

# 3. Instalar el paquete
pip install -e .
```

## Configuracion de Claude Code

Crea el archivo `.mcp.json` en la raiz del proyecto donde realmente vas a ejecutar Claude Code.

Si el archivo incluye informacion sensible de conexion (como contrasenas), se recomienda agregar `.mcp.json` a `.gitignore`.

### Windows (`.mcp.json`)

```json
{
  "mcpServers": {
    "as400": {
      "command": "C:/path/to/as400-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "as400_mcp.server"],
      "env": {
        "AS400_CONNECTION_STRING": "DRIVER={IBM i Access ODBC Driver};SYSTEM=YOUR_SYSTEM;UID=USER;PWD=PASS;CCSID=1208;EXTCOLINFO=1"
      }
    }
  }
}
```

### Linux/macOS (`.mcp.json`)

```json
{
  "mcpServers": {
    "as400": {
      "command": "/path/to/as400-mcp/.venv/bin/python",
      "args": ["-m", "as400_mcp.server"],
      "env": {
        "AS400_CONNECTION_STRING": "DRIVER={IBM i Access ODBC Driver};SYSTEM=YOUR_SYSTEM;UID=USER;PWD=PASS;CCSID=1208;EXTCOLINFO=1"
      }
    }
  }
}
```

Despues de configurar esto, reinicia Claude Code y verifica con el comando `/mcp` que el servidor `as400` aparezca correctamente.

### Opciones de la cadena de conexion

| Opcion | Descripcion |
|-----------|------|
| `SYSTEM` | Nombre de host o direccion IP del AS400 |
| `UID` | ID de usuario |
| `PWD` | Contrasena |
| `CCSID=1208` | Comunicacion en UTF-8 (compatible con japones) |
| `EXTCOLINFO=1` | Obtiene informacion extendida de columnas (como `COLUMN_TEXT`) |

## Uso

### Flujo de trabajo basico

```
Usuario: Crea una pantalla web usando la tabla de pedidos de MYLIB

Claude Code:
1. Obtiene la informacion de la tabla con get_table_info("MYLIB", "ORDER")
2. Revisa la informacion de columnas (incluyendo etiquetas en japones)
3. Verifica datos de ejemplo con get_data
4. Genera la pantalla web (React, por ejemplo) y la API (FastAPI, por ejemplo)
```

### Ejemplos de uso

#### Revisar estructura de tabla

```
> Muestrame la estructura de la tabla ORDER de MYLIB
```

#### Consultar codigo fuente existente

```
> Muestrame la lista de archivos fuente de MYLIB
> Muestrame el fuente ORDMNT dentro de MYLIB/QRPGSRC
```

#### Investigar programas

```
> Muestrame la lista de programas RPG que existen en MYLIB
> Dime que archivos referencia el programa ORDER001
```

#### Generar pantallas web

```
> Crea una pantalla web de lista y detalle usando la tabla CUSTOMER de MYLIB
  - Usa las etiquetas en japones como nombres de campos en pantalla
  - Incluye funcionalidad de busqueda
```

#### Revisar informacion del sistema

```
> Dime la version del AS400
```

## Configuracion del driver ODBC

Para instalar el driver ODBC, consulta la documentacion oficial siguiente:

[IBM i Access ODBC Installation](https://ibmi-oss-docs.readthedocs.io/en/latest/odbc/installation.html)

## Desarrollo

### Probar sin Claude Code

Puedes verificar el funcionamiento del servidor MCP incluso sin Claude Code.

```bash
# Copiar .env.example y configurar la informacion de conexion
cp .env.example .env
# Editar .env e ingresar los datos de conexion

# Iniciar directamente (enviando JSON-RPC por stdin)
python -m as400_mcp.server

# Obtener la lista de herramientas
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m as400_mcp.server
```
> Lo anterior aplica si quieres ejecutar `as400-mcp` de forma independiente y no a traves de Claude Code.

#### MCP Inspector (recomendado)

Puedes probar las herramientas desde una GUI usando la Web UI de depuracion proporcionada por Anthropic.

```bash
npx @modelcontextprotocol/inspector python -m as400_mcp.server
```
> Se asume que ya editaste el archivo `.env` segun lo indicado en la seccion "Probar sin Claude Code".

Se abrira el navegador y podras revisar la lista de herramientas y ejecutar pruebas manuales.

### Pruebas unitarias

```bash
# Instalar dependencias de desarrollo
pip install -e ".[dev]"

# Ejecutar pruebas
pytest tests/ -v
```

### Lint

```bash
ruff check .
ruff format .
```

## Solucion de problemas

### Error de conexion

```
[HY000] [IBM][System i Access ODBC Driver]Communication link failure
```

-> Verifica `SYSTEM`, `UID` y `PWD`. Revisa tambien que el firewall permita puertos como 446, 449 y 8470.

### Texto corrupto / problemas de encoding

```
UnicodeDecodeError
```

-> Agrega `CCSID=1208` a la cadena de conexion (comunicacion UTF-8).

### No se pueden obtener las etiquetas en japones

```
COLUMN_TEXT is empty
```

-> Agrega `EXTCOLINFO=1` a la cadena de conexion.

### Error de permisos

```
[42501] User not authorized to object
```

-> En AS400, otorga al usuario permisos de acceso sobre las vistas de catalogo QSYS2.

## Licencia

MIT License - Copyright (c) 2025 kozokaAI Inc.

## Enlaces relacionados

- [FastMCP](https://github.com/jlowin/fastmcp)
- [MCP Specification](https://modelcontextprotocol.io/specification/2025-11-25)
