"""
Database initialization CLI command.

Provides commands for initializing and resetting the stocks-helper database.
"""

import click
from pathlib import Path

from src.lib.db import init_db, db_exists, reset_db, DEFAULT_DB_PATH


@click.command()
@click.option('--reset', is_flag=True, help='Reset database (WARNING: deletes all data)')
def init(reset: bool) -> None:
    """Initialize the stocks-helper database."""

    if db_exists() and not reset:
        click.echo(f"Database already exists at {DEFAULT_DB_PATH}")
        click.echo("Use --reset to recreate (WARNING: this will delete all data)")
        return

    if reset:
        if not click.confirm("This will DELETE ALL DATA. Continue?"):
            click.echo("Aborted.")
            return

        reset_db()
        click.echo("Database reset successfully.")
    else:
        init_db()
        click.echo(f"Database initialized at {DEFAULT_DB_PATH}")
        click.echo(f"Cache directory: {DEFAULT_DB_PATH.parent / 'cache'}")
