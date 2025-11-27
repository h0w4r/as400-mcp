# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules
- 結果は日本語で返してください

## Project Overview

AS400 MCP Server for Claude Code - An MCP (Model Context Protocol) server that enables Claude to interact with AS400/IBM i systems for CL/RPG/COBOL program development. This server provides tools, resources, and prompts for accessing AS400 metadata, source code, and data via ODBC.

## Development Commands

### Setup and Installation
```bash
# Install in editable mode
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

### Running the Server
```bash
# Set connection string (required)
# CCSID=1208: UTF-8通信（日本語対応）
# EXTCOLINFO=1: 拡張カラム情報（COLUMN_TEXT等）を取得
export AS400_CONNECTION_STRING="DRIVER={IBM i Access ODBC Driver};SYSTEM=YOUR_SYSTEM;UID=USER;PWD=PASS;CCSID=1208;EXTCOLINFO=1"

# Run server directly
python -m as400_mcp.server

# Or use the installed command
as400-mcp
```

### Testing
```bash
# Run all tests
pytest

# Run with verbose output
pytest tests/ -v

# Run specific test file
pytest tests/test_server.py -v

# Run with coverage
pytest tests/ --cov=as400_mcp --cov-report=html
```

### Code Quality
```bash
# Check code with ruff
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

## Architecture

### Core Technologies
- **FastMCP**: Framework for building MCP servers (handles protocol implementation)
- **pyodbc**: ODBC driver interface for AS400 connectivity
- **IBM i Access ODBC Driver**: Required external dependency for AS400 connections

### Main Components

**src/as400_mcp/server.py** - Single-file MCP server implementation containing:

1. **Tools** (12 functions): Action execution for querying AS400
   - `list_libraries()` - Get library list with labels
   - `list_tables()` - Get tables/files in a library
   - `get_columns()` - Get column metadata with Japanese labels
   - `list_sources()` - Get source members (CL/RPG/COBOL files)
   - `get_source()` - Retrieve source code content
   - `get_data()` - Query table data with column labels
   - `get_table_info()` - Get comprehensive table metadata (for DDL generation)
   - `get_system_info()` - Get AS400 system information (OS version, PTF level, system status)
   - `list_programs()` - Get program list in a library (RPG/CL/COBOL etc.)
   - `get_program_references()` - Get files and programs referenced by a program
   - `list_data_areas()` - Get data area list with values (shared variables for CL)
   - `execute_sql()` - Execute SELECT statements (read-only for security)

2. **Resources** (3 URIs): Structured data access via URI patterns
   - `as400://library/{library}/tables` - Library table listing
   - `as400://library/{library}/table/{table}/schema` - Table schema
   - `as400://library/{library}/source/{source_file}/{member}` - Source code

3. **Prompts** (3 templates): Pre-configured prompt templates for common tasks
   - `create_crud_program()` - Generate CRUD screen programs (RPG/CL)
   - `analyze_source()` - Analyze existing source code
   - `generate_cl_for_batch()` - Create batch processing CL programs

### Key Design Patterns

- **Connection Management**: `get_connection()` creates new ODBC connections per request; connections are closed in `finally` blocks
- **Case Handling**: Library/table/column names are normalized to uppercase (AS400 convention)
- **Japanese Text**: COLUMN_TEXT and TABLE_TEXT fields preserve Japanese labels via CCSID handling
- **Security**: `execute_sql()` only allows SELECT statements to prevent data modification
- **Metadata Queries**: Uses QSYS2 catalog views (modern approach: SYSTABLES, SYSCOLUMNS, SYSKEYCST, etc.)

### Configuration

Connection string is set via:
1. `AS400_CONNECTION_STRING` environment variable (preferred)
2. Falls back to placeholder in `main()` function

The server expects Claude Code's `claude_code_config.json` to be configured with the MCP server entry.

## AS400-Specific Conventions

### Naming Conventions
- **Libraries**: Similar to schemas in SQL databases (e.g., MYLIB)
- **Source Files**: Container for source members (QCLSRC, QRPGSRC, QRPGLESRC, QCBLSRC)
- **Members**: Individual source code files within source files
- **Physical Files (P)**: Tables with actual data storage
- **Logical Files (L)**: Views/indexes over physical files

### Common Source File Types
- QCLSRC - CL (Control Language) programs
- QRPGSRC - RPG programs
- QRPGLESRC - RPG ILE programs
- QCBLSRC - COBOL programs
- QDDSSRC - DDS (Data Description Specifications)

### Typical Development Workflow
1. Use `list_libraries()` to find target library
2. Use `list_tables()` to discover files/tables
3. Use `get_columns()` to understand table structure (includes Japanese labels)
4. Use `list_sources()` and `get_source()` if referencing existing code
5. Generate new CL/RPG programs based on gathered metadata

## Testing Approach

- **Unit Tests**: Mock ODBC connections (see `tests/conftest.py` fixtures)
- **Fixtures**: `mock_odbc`, `sample_columns`, `sample_tables`, `sample_source_members`
- **Integration Tests**: Marked with `@pytest.mark.requires_odbc` (require actual AS400)
- All tests should work without actual AS400 connection via mocking

## Important Implementation Notes

- Always handle null COLUMN_TEXT/TABLE_TEXT with `COALESCE()`
- String values from AS400 are right-padded; use `.rstrip()` when processing
- CCSID (Coded Character Set ID) is important for Japanese text encoding
- Source files have special columns: SRCSEQ (sequence), SRCDAT (date), SRCDTA (source text)
- The system uses SYSTEM_TABLE_MEMBER to identify members within source files
- Key information comes from QSYS2.SYSKEYCST view, not from constraints

## Claude Code MCP Instructions

The server includes built-in instructions (see `server.py` lines 13-44) that guide Claude on:
- When to use each tool in the workflow
- How to utilize Japanese labels in generated programs
- AS400-specific terminology and conventions
- Best practices for CRUD screen generation

These instructions are automatically provided to Claude when the MCP server is active.
