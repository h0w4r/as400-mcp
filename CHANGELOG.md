# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release

## [0.1.0] - 2024-XX-XX

### Added
- Core tools for AS400/IBM i interaction
  - `list_libraries`: List libraries with labels
  - `list_tables`: List tables/files with metadata
  - `get_columns`: Get column information with Japanese labels
  - `list_sources`: List source members
  - `get_source`: Retrieve source code
  - `get_data`: Fetch table data with column labels
  - `get_table_info`: Get detailed table information
  - `execute_sql`: Execute SELECT queries safely

- MCP Resources
  - `as400://library/{lib}/tables`: Table listing resource
  - `as400://library/{lib}/table/{tbl}/schema`: Schema resource
  - `as400://library/{lib}/source/{srcf}/{mbr}`: Source code resource

- MCP Prompts
  - `create_crud_program`: Generate CRUD screen program prompt
  - `analyze_source`: Source code analysis prompt
  - `generate_cl_for_batch`: Batch CL generation prompt

- Documentation
  - README in English and Japanese
  - Setup guide
  - Usage examples

### Security
- SELECT-only restriction for `execute_sql` tool
- Connection string via environment variable (not hardcoded)

[Unreleased]: https://github.com/your-repo/as400-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-repo/as400-mcp/releases/tag/v0.1.0
