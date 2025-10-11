"""
Database connection and initialization module.

Manages SQLite database creation, connection pooling, and schema initialization.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Base class for all models
Base = declarative_base()

# Default database path (can be overridden by environment variable)
DEFAULT_DB_PATH = Path.home() / ".stocks-helper" / "data.db"

# Global engine and session factory
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def _enable_foreign_keys(dbapi_conn: Any, connection_record: Any) -> None:
    """Enable foreign key constraints for SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(db_path: Optional[Path] = None) -> Engine:
    """
    Get or create the SQLAlchemy engine.

    Args:
        db_path: Optional custom database path. Defaults to ~/.stocks-helper/data.db
                 Can also be set via STOCKS_HELPER_DB_PATH environment variable.

    Returns:
        SQLAlchemy Engine instance
    """
    global _engine

    if _engine is None:
        if db_path is None:
            # Check environment variable for test database path
            env_db_path = os.environ.get("STOCKS_HELPER_DB_PATH")
            if env_db_path:
                db_path = Path(env_db_path)
            else:
                db_path = DEFAULT_DB_PATH

        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create engine with SQLite-specific settings
        db_url = f"sqlite:///{db_path}"
        _engine = create_engine(
            db_url,
            echo=False,  # Set to True for SQL debugging
            connect_args={"check_same_thread": False},  # Allow multi-threading
        )

        # Enable foreign keys for all connections
        event.listen(_engine, "connect", _enable_foreign_keys)

    return _engine


def reset_engine() -> None:
    """Reset the global engine and session factory.

    This is used for testing to ensure a fresh database connection.
    **WARNING: Only use this in tests!**
    """
    global _engine, _SessionLocal

    if _engine is not None:
        _engine.dispose()
        _engine = None

    _SessionLocal = None


def get_session() -> Session:
    """
    Get a new database session.

    Returns:
        SQLAlchemy Session instance
    """
    global _SessionLocal

    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return _SessionLocal()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic commit/rollback.

    Provides transactional safety by automatically:
    - Committing on successful completion
    - Rolling back on exceptions
    - Closing the session in all cases

    Usage:
        with db_session() as session:
            # ... database operations ...
            # Automatic commit on success, rollback on exception

    Yields:
        SQLAlchemy Session instance

    Example:
        with db_session() as session:
            stock = Stock(ticker="AAPL", name="Apple Inc.")
            session.add(stock)
            # Commits automatically when context exits successfully
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Initialize the database by creating all tables.

    Args:
        db_path: Optional custom database path. Defaults to ~/.stocks-helper/data.db
    """
    engine = get_engine(db_path)

    # Import all models to ensure they're registered with Base
    from src.models import (  # noqa: F401
        Account,
        Bond,
        Cashflow,
        ChartAccount,
        ExchangeRate,
        FundamentalData,
        Holding,
        ImportBatch,
        ImportError,
        Insight,
        JournalEntry,
        JournalLine,
        MarketData,
        Portfolio,
        Reconciliation,
        Security,
        Stock,
        StockRecommendation,
        StockSuggestion,
        Transaction,
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create cache directory
    cache_dir = DEFAULT_DB_PATH.parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)


def reset_db(db_path: Optional[Path] = None) -> None:
    """
    Drop all tables and recreate them. **WARNING: This deletes all data!**

    Args:
        db_path: Optional custom database path
    """
    engine = get_engine(db_path)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def db_exists(db_path: Optional[Path] = None) -> bool:
    """
    Check if the database file exists.

    Args:
        db_path: Optional custom database path

    Returns:
        True if database file exists
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    return db_path.exists()
