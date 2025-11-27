# Contributing to AS400 MCP Server

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

### Development Setup

```bash
# Clone the repository
git clone https://github.com/your-repo/as400-mcp.git
cd as400-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

### Running Locally

```bash
# Set connection string
export AS400_CONNECTION_STRING="DRIVER={IBM i Access ODBC Driver};SYSTEM=your-system;UID=user;PWD=pass"

# Run the server
python -m as400_mcp.server
```

## Code Style

We use [ruff](https://github.com/astral-sh/ruff) for linting and formatting.

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

### Guidelines

- Use type hints for function parameters and return values
- Write docstrings for public functions (Google style)
- Keep functions focused and small
- Use meaningful variable names

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_server.py -v

# Run with coverage
pytest tests/ --cov=as400_mcp --cov-report=html
```

### Writing Tests

- Use pytest fixtures for common setup
- Mock ODBC connections (don't require actual AS400 for unit tests)
- Mark integration tests with `@pytest.mark.requires_odbc`
- Include both positive and negative test cases

## Pull Request Process

1. **Fork** the repository and create your branch from `main`
2. **Add tests** for any new functionality
3. **Update documentation** if needed
4. **Run tests** and ensure they pass
5. **Run linter** and fix any issues
6. **Submit** a pull request

### PR Checklist

- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated
- [ ] Commit messages are clear and descriptive

### Commit Messages

Use clear, descriptive commit messages:

```
feat: Add support for SYSTABLESTAT view
fix: Handle null COLUMN_TEXT gracefully  
docs: Update Japanese README with troubleshooting
test: Add tests for get_columns edge cases
```

## Feature Requests and Bug Reports

- Use GitHub Issues
- Check existing issues before creating new ones
- Provide detailed reproduction steps for bugs
- Include AS400/IBM i version information when relevant

## AS400-Specific Considerations

When contributing features:

- Use QSYS2 catalog views (not legacy QADBXREF etc.)
- Handle CCSID/encoding properly for Japanese text
- Consider both physical files and SQL tables
- Test with common source file types (QCLSRC, QRPGSRC, QRPGLESRC, QCBLSRC)

## Questions?

Feel free to open an issue for any questions about contributing.
