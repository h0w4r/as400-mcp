"""Pytest configuration and fixtures"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_connection():
    """Mock ODBC connection for testing without actual AS400"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def mock_odbc(mock_connection):
    """Patch pyodbc.connect to return mock connection"""
    mock_conn, mock_cursor = mock_connection
    with patch("as400_mcp.server.get_connection", return_value=mock_conn):
        yield mock_conn, mock_cursor


# Sample test data
@pytest.fixture
def sample_columns():
    """Sample column data for testing"""
    return [
        ("ORDNO", "受注番号", "DECIMAL", 10, 0, "N", 1, "", 65535),
        ("CUSTCD", "顧客コード", "CHAR", 10, 0, "N", 2, "", 5035),
        ("ORDDAT", "受注日", "DATE", 10, 0, "Y", 3, "", 65535),
        ("ORDAMT", "受注金額", "DECIMAL", 15, 2, "Y", 4, "0", 65535),
    ]


@pytest.fixture
def sample_tables():
    """Sample table data for testing"""
    return [
        ("ORDER", "受注マスタ", "P", 1000),
        ("ORDERD", "受注明細", "P", 5000),
        ("CUSTOMER", "顧客マスタ", "P", 500),
    ]


@pytest.fixture
def sample_source_members():
    """Sample source member data for testing"""
    return [
        ("ORDMNT", "RPGLE", "受注メンテナンス", "2024-01-15 10:30:00", 500),
        ("ORDPRT", "RPGLE", "受注印刷", "2024-01-10 09:00:00", 300),
        ("ORDBAT", "CLP", "受注バッチ", "2024-02-01 14:00:00", 50),
    ]
