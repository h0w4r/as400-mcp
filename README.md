# Servidor MCP AS400

Este servidor MCP es compatible con el desarrollo de AS400/IBM i para Claude Code.
Recupera metadatos y código fuente de AS400 mediante ODBC, lo que facilita el desarrollo de programas CL/RPG/COBOL.

## Características

- **Compatibilidad con etiquetas japonesas**: Obtiene y utiliza descripciones de texto en japonés para columnas y tablas.
- **Referencia de código fuente**: Obtiene código fuente de QCLSRC/QRPGSRC, etc.
- **Inspección de dependencias del programa**: Obtiene archivos referenciados y relaciones de llamadas.
- **Obtención de información del sistema**: Comprueba la versión del sistema operativo, el nivel de PTF, etc.
- **Solo lectura**: Por razones de seguridad, todas las operaciones son de solo lectura.

## Herramientas disponibles

| Herramienta | Descripción |
|--------|------|
| `list_libraries` | Lista de bibliotecas (con etiquetas) |
| `list_tables` | Lista de tablas/archivos |
| `get_columns` | Lista de columnas (etiquetas japonesas, tipos, información clave) |
| `list_source_files` | Lista de archivos fuente (QCLSRC, QRPGSRC, etc.) |
| `list_sources` | Lista de miembros fuente |
| `get_source` | Obtener código fuente |
| `get_data` | Obtener datos de la tabla |
| `get_table_info` | Detalles de la tabla |
| `get_system_info` | Información del sistema (versión del sistema operativo, PTF, etc.) |
| `list_programs` | Lista de programas (RPG/CL/COBOL, etc.) |
| `get_program_references` | Archivos de referencia de programa y relaciones de llamada |
| `list_data_areas` | Lista de áreas de datos (variables compartidas) |
| `execute_sql` | Ejecutar SELECT arbitrario (solo lectura) |

## Instalación

### Requisitos previos

- Python 3.10 o posterior
- Controlador ODBC de IBM i Access
- AS400/IBM i 7.3 o posterior (se recomienda 7.4 o posterior)
- 7.3: Las funciones básicas funcionan
- 7.4+: Funciones adicionales como `get_program_references` están disponibles
- Información de conexión de AS400/IBM i

### Procedimiento de instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/omni-s/as400-mcp.git
cd as400-mcp

# 2. Crear y activar un entorno virtual
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

# 3. Instalar el paquete
pip install -e .
```

## Configuración de Claude Code

Cree un archivo `.mcp.json` en la raíz del proyecto donde ejecutará Claude Code.

Si el archivo contiene información de conexión (como una contraseña), recomendamos agregar `.mcp.json` a `.gitignore`.

### Windows (.mcp.json)

```json
{
"mcpServers": {
"as400": {
"command": "C:/ruta/a/as400-mcp/.venv/Scripts/python.exe",
"args": ["-m", "as400_mcp.server"],
"env": {
"AS400_CONNECTION_STRING": "DRIVER={Controlador ODBC de IBM i Access};SYSTEM=SU_SISTEMA;UID=USUARIO;PWD=CONTRASEÑA;CCSID=1208;EXTCOLINFO=1"
}
}
}
}
````

### Linux/macOS (.mcp.json)

```json
{
"mcpServers": {
"as400": {
"command": "/path/to/as400-mcp/.venv/bin/python",
"args": ["-m", "as400_mcp.server"],
"env": {
"AS400_CONNECTION_STRING": "DRIVER={Controlador ODBC de IBM i Access};SYSTEM=YOUR_SYSTEM;UID=USER;PWD=PASS;CCSID=1208;EXTCOLINFO=1"
}
}
}
}
```

Después de configurar esto, reinicie Claude Code y verifique que el servidor as400 se muestre con el comando `/mcp`.

### Opciones de la cadena de conexión

| Opción | Descripción |
|-----------|------|
| `SYSTEM` | Nombre de host o dirección IP del AS400 |
| `UID` | ID de usuario |
| `PWD` | Contraseña |
| `CCSID=1208` | Comunicación UTF-8 (soporte japonés) |
| `EXTCOLINFO=1` | Obtener información extendida de columnas (COLUMN_TEXT, etc.) |

## Uso

### Flujo de trabajo básico

```
Usuario: Crear una página web usando la tabla de pedidos MYLIB.

Código Claude:
1. Obtener información de la tabla con get_table_info("MYLIB", "ORDER")
2. Verificar la información de las columnas (con etiquetas en japonés)
3. Verificar datos de ejemplo con get_data
4. Generar una página web (React, etc.) y una API (FastAPI, etc.)
```

### Ejemplo de uso

#### Verificar la estructura de la tabla

```
> ¿Cuál es la estructura de la tabla ORDER en MYLIB? ```

#### Referencia al código fuente existente

```
> Muéstrame una lista de archivos fuente en MYLIB
> Muéstrame el código fuente de ORDMNT en MYLIB/QRPGSRC
```

#### Investigación del programa

```
> Muéstrame una lista de programas RPG en MYLIB
> Indica los archivos referenciados por el programa ORDER001
```

#### Generación de páginas web

```
> Crea una lista web y una pantalla de detalles usando la tabla CUSTOMER en MYLIB
- Usa etiquetas japonesas como nombres de campo de pantalla
- Con función de búsqueda
```

#### Confirmación de la información del sistema

```
> Indica la versión de AS400
```

## Configuración del controlador ODBC

Para obtener información sobre la instalación del controlador ODBC, consulte la documentación oficial a continuación.

[Instalación de ODBC en IBM i Access](https://ibmi-oss-docs.readthedocs.io/en/latest/odbc/installation.html)

## Desarrollo

### Pruebas sin Claude Code

Puede probar el servidor MCP sin Claude Code.

```bash
# Copiar .env.example y establecer la información de conexión
cp .env.example .env
# Editar .env e introducir la información de conexión

# Iniciar directamente (introducir JSON-RPC en la entrada estándar)
python -m as400_mcp.server

# Obtener una lista de herramientas
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m as400_mcp.server
```
> Lo anterior es para ejecutar as400-mcp de forma independiente, sin Claude Code.

#### Inspector MCP (Recomendado)

Puede probar herramientas desde una interfaz gráfica de usuario (GUI) utilizando la interfaz web de depuración proporcionada por Anthropic.

```bash
npx @modelcontextprotocol/inspector python -m as400_mcp.server
```
> Se asume que ya ha editado el archivo .env como se describe en "Pruebas sin Claude Code".

Se abrirá un navegador que le permitirá ver una lista de herramientas y ejecutar pruebas.

### Prueba unitaria

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

## Solución de problemas

### Error de conexión

```
[HY000] [IBM][Controlador ODBC de System i Access]Fallo de enlace de comunicación
```

→ Compruebe SYSTEM, UID y PWD. Compruebe que los puertos 446, 449, 8470, etc., estén abiertos en el firewall.

### Caracteres ilegibles

```
UnicodeDecodeError
```

→ Añada `CCSID=1208` a la cadena de conexión (comunicación UTF-8).

### No se pueden recuperar las etiquetas japonesas

```
COLUMN_TEXT está vacío
```

→ Añada `EXTCOLINFO=1` a la cadena de conexión.

### Error de autorización

```
[42501] Usuario no autorizado para objetar
```

→ Otorgar al usuario acceso a la vista del catálogo de QSYS2 en el lado AS400.

## Licencia

Licencia MIT - Copyright (c) 2025 kozokaAI Inc.

## Enlaces relacionados

- [FastMCP](https://github.com/jlowin/fastmcp)
- [Especificación MCP](https://modelcontextprotocol.io/specification/2025-11-25)
