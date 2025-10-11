"""Pytest configuration and fixtures for all tests."""

import os
import tempfile
from pathlib import Path

import pytest

from src.lib.db import init_db, reset_db, reset_engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Initialize test database before any tests run.

    Creates a temporary database for testing that is automatically cleaned up.
    Uses session scope so database is created once per test session.
    """
    # Create temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        test_db_path = Path(tmp.name)

    # Set environment variable for test database BEFORE initializing
    os.environ["STOCKS_HELPER_DB_PATH"] = str(test_db_path)

    # Initialize database with all tables
    init_db(test_db_path)

    yield test_db_path

    # Cleanup: Remove temporary database file
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture(autouse=True)
def reset_database_between_tests(setup_test_database):
    """Reset database state between each test.

    This ensures test isolation by clearing all data between tests
    while keeping the schema intact.
    """
    # Reset engine to ensure fresh connection
    reset_engine()

    # Reset database tables
    reset_db(setup_test_database)

    yield
