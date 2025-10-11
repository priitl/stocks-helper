"""Import CLI commands for CSV transaction imports and metadata enrichment."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from src.lib.db import db_session
from src.models import Security, Stock
from src.services.import_service import ImportService

console = Console()


def validate_file_path(file_path: Path) -> None:
    """Validate file path for security risks.

    Args:
        file_path: Path to validate

    Raises:
        click.BadParameter: If path is unsafe (symlink, outside allowed dirs, etc.)
    """
    # Check if file exists
    if not file_path.exists():
        raise click.BadParameter(f"File not found: {file_path}")

    # Resolve to absolute path to check for traversal
    try:
        resolved_path = file_path.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise click.BadParameter(f"Invalid file path: {e}")

    # Check if it's a symlink (security risk)
    if file_path.is_symlink():
        raise click.BadParameter(f"Symlinks are not allowed for security reasons: {file_path}")

    # Check if it's a regular file (not directory, device, etc.)
    if not resolved_path.is_file():
        raise click.BadParameter(f"Path must be a regular file: {file_path}")

    # Check file extension (only allow CSV files)
    if resolved_path.suffix.lower() not in [".csv"]:
        raise click.BadParameter(f"Only CSV files are allowed, got: {resolved_path.suffix}")

    # Get allowed base directories (user's home, current directory, /tmp)
    allowed_dirs = [
        Path.home(),
        Path.cwd(),
        Path("/tmp"),
        Path("/var/tmp"),
    ]

    # Check if file is within one of the allowed directories
    is_allowed = any(
        str(resolved_path).startswith(str(allowed_dir.resolve())) for allowed_dir in allowed_dirs
    )

    if not is_allowed:
        raise click.BadParameter(
            f"File must be in user home, current directory, or /tmp. Got: {resolved_path}"
        )

    # Check for sensitive system paths (additional safety check)
    sensitive_paths = ["/etc/", "/sys/", "/proc/", "/dev/", "/boot/"]
    for sensitive in sensitive_paths:
        if str(resolved_path).startswith(sensitive):
            raise click.BadParameter(
                f"Access to system directories is not allowed: {resolved_path}"
            )


@click.group(name="import")
def import_group() -> None:
    """Import transactions and manage metadata enrichment."""
    pass


@import_group.command(name="csv")
@click.option(
    "--file",
    "-f",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to CSV file",
)
@click.option(
    "--broker",
    "-b",
    required=True,
    type=click.Choice(["swedbank", "lightyear"], case_sensitive=False),
    help="Broker type (swedbank or lightyear)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate without importing to database",
)
def import_csv(file: Path, broker: str, dry_run: bool) -> None:
    """Import transactions from CSV file.

    Examples:
        stocks-helper import csv -f transactions.csv -b swedbank
        stocks-helper import csv -f data.csv -b lightyear --dry-run
    """
    # Validate file path for security (check symlinks, path traversal, etc.)
    validate_file_path(file)

    service = ImportService()

    console.print(f"\n[bold]Importing {file.name}[/bold] (broker: {broker})")

    if dry_run:
        console.print("[yellow]DRY RUN MODE - No data will be saved[/yellow]\n")

    try:
        result = service.import_csv(filepath=file, broker_type=broker.lower(), dry_run=dry_run)

        # Display summary
        table = Table(title="Import Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="green")

        table.add_row("Total Rows", str(result.total_rows))
        table.add_row("Successful", str(result.successful_count))
        table.add_row("Duplicates", str(result.duplicate_count))
        table.add_row("Errors", str(result.error_count))
        table.add_row("Unknown Tickers", str(result.unknown_ticker_count))
        table.add_row("Duration", f"{result.processing_duration:.2f}s", style="dim")

        console.print(table)

        # Show unknown tickers if any
        if result.unknown_ticker_count > 0:
            console.print(
                f"\n[yellow]⚠️  {result.unknown_ticker_count} unknown ticker(s) detected![/yellow]"
            )
            console.print(
                f"[dim]Review with:[/dim] stocks-helper import review-tickers {result.batch_id}"
            )

        # Show enrichment suggestion
        if result.successful_count > 0 and not dry_run:
            console.print(
                "\n[dim]Check metadata enrichment:[/dim] stocks-helper import review-metadata\n"
            )

    except Exception as e:
        console.print(f"[red]✗ Import failed: {e}[/red]")
        raise click.Abort()


@import_group.command(name="review-metadata")
def review_metadata() -> None:
    """Review securities needing metadata enrichment.

    Shows securities where metadata was not fetched from Yahoo Finance
    during import (usually regional/European stocks).
    """
    service = ImportService()
    securities = service.get_securities_needing_enrichment()

    if not securities:
        console.print("\n[green]✓ All securities have complete metadata![/green]\n")
        return

    table = Table(title=f"Securities Needing Enrichment ({len(securities)})")
    table.add_column("Security ID", style="dim")
    table.add_column("Ticker", style="cyan")
    table.add_column("Current Name", style="yellow")
    table.add_column("Exchange", style="magenta")

    for sec in securities:
        table.add_row(
            sec["security_id"][:8] + "...",
            sec["ticker"],
            sec["current_name"],
            sec["current_exchange"],
        )

    console.print()
    console.print(table)

    console.print("\n[bold]Next Steps:[/bold]")
    console.print("1. Determine correct Yahoo Finance ticker (e.g., IWDA-NA → IWDA.AS)")
    console.print(
        "2. Update: [cyan]stocks-helper import update-metadata <ticker> <yahoo-ticker>[/cyan]"
    )
    console.print(
        "\n[dim]Common exchange suffixes: "
        ".TL (Tallinn), .HE (Helsinki), .AS (Amsterdam), .OL (Oslo)[/dim]\n"
    )


@import_group.command(name="update-metadata")
@click.argument("ticker")
@click.argument("yahoo_ticker", required=False)
def update_metadata(ticker: str, yahoo_ticker: str | None) -> None:
    """Update security metadata from Yahoo Finance.

    TICKER: Stock ticker to update (as stored in database)
    YAHOO_TICKER: Corrected Yahoo Finance ticker (optional, if different)

    Examples:
        stocks-helper import update-metadata IWDA-NA IWDA.AS
        stocks-helper import update-metadata BRK.B BRK-B
        stocks-helper import update-metadata AAPL  (retry with current ticker)
    """
    service = ImportService()

    # Find security by ticker
    with db_session() as session:
        stmt = select(Security).where(Security.ticker == ticker)
        security = session.execute(stmt).scalar_one_or_none()

        if not security:
            console.print(f"[red]✗ Security not found: {ticker}[/red]")
            raise click.Abort()

        security_id = security.id
        current_name = security.name

    console.print(f"\n[bold]Updating metadata for {ticker}[/bold]")
    console.print(f"Current name: [yellow]{current_name}[/yellow]")

    if yahoo_ticker:
        console.print(f"Using Yahoo ticker: [cyan]{yahoo_ticker}[/cyan]")

    try:
        success = service.update_security_metadata(security_id, yahoo_ticker)

        if success:
            # Link dividends to holdings for this security
            linked_count = service.link_dividends_to_holdings(security_id=security_id)
            if linked_count > 0:
                console.print(f"[green]✓ Linked {linked_count} dividend(s) to holdings[/green]")

            # Auto-sync stock splits
            with db_session() as session:
                stmt_check = select(Security).where(Security.id == security_id)
                security_check = session.execute(stmt_check).scalar_one_or_none()

                if security_check and security_check.ticker:
                    try:
                        from src.models import SecurityType
                        from src.services.splits_service import SplitsService

                        # Only sync splits for stocks
                        if security_check.security_type == SecurityType.STOCK:
                            splits_service = SplitsService()
                            splits_added = splits_service.sync_splits_from_yfinance(
                                session, security_id, security_check.ticker
                            )
                            if splits_added > 0:
                                console.print(
                                    f"[green]✓ Synced {splits_added} stock split(s)[/green]"
                                )
                                session.commit()
                    except Exception as e:
                        # Don't fail the whole update if split sync fails
                        console.print(f"[yellow]⚠ Split sync failed: {e}[/yellow]")

            # Read updated data
            with db_session() as session:
                stmt2 = (
                    select(Security, Stock)
                    .outerjoin(Stock, Security.id == Stock.security_id)
                    .where(Security.id == security_id)
                )
                result2 = session.execute(stmt2).one()
                updated_security, updated_stock = result2

                console.print("\n[green]✓ Successfully enriched![/green]")
                console.print(f"  Name: [bold]{updated_security.name}[/bold]")

                if updated_stock:
                    console.print(f"  Exchange: [bold]{updated_stock.exchange}[/bold]")
                    if updated_stock.sector:
                        console.print(f"  Sector: [cyan]{updated_stock.sector}[/cyan]")
                    if updated_stock.industry:
                        console.print(f"  Industry: [cyan]{updated_stock.industry}[/cyan]")
                    if updated_stock.country:
                        console.print(f"  Country: [yellow]{updated_stock.country}[/yellow]")
                    if updated_stock.region:
                        console.print(f"  Region: [yellow]{updated_stock.region}[/yellow]")
                console.print()
        else:
            console.print("\n[red]✗ Failed to fetch metadata from Yahoo Finance[/red]")
            console.print(
                "[dim]Verify the Yahoo ticker is correct and "
                "the stock exists on Yahoo Finance[/dim]\n"
            )

    except Exception as e:
        console.print(f"[red]✗ Update failed: {e}[/red]")
        raise click.Abort()


@import_group.command(name="history")
@click.option(
    "--limit",
    "-n",
    default=10,
    type=int,
    help="Number of recent imports to show",
)
def import_history(limit: int) -> None:
    """Show recent import history.

    Example:
        stocks-helper import history
        stocks-helper import history -n 20
    """
    service = ImportService()
    batches = service.get_import_history(limit=limit)

    if not batches:
        console.print("\n[yellow]No import history found[/yellow]\n")
        return

    table = Table(title=f"Import History (last {limit})")
    table.add_column("Batch ID", style="dim")
    table.add_column("File", style="cyan")
    table.add_column("Broker", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Rows", justify="right")
    table.add_column("Success", justify="right", style="green")
    table.add_column("Errors", justify="right", style="red")
    table.add_column("Date", style="dim")

    for batch in batches:
        status_color = "green" if batch.status == "COMPLETED" else "yellow"
        table.add_row(
            str(batch.batch_id),
            batch.filename,
            batch.broker_type,
            f"[{status_color}]{batch.status}[/{status_color}]",
            str(batch.total_rows),
            str(batch.successful_count),
            str(batch.error_count),
            batch.upload_timestamp.strftime("%Y-%m-%d %H:%M") if batch.upload_timestamp else "N/A",
        )

    console.print()
    console.print(table)
    console.print()


@import_group.command(name="review-tickers")
@click.argument("batch_id", type=int)
def review_unknown_tickers(batch_id: int) -> None:
    """Review unknown tickers from an import batch.

    BATCH_ID: Import batch ID (from import history)

    Example:
        stocks-helper import review-tickers 123
    """
    service = ImportService()

    try:
        unknowns = service.get_unknown_tickers(batch_id)

        if not unknowns:
            console.print(f"\n[green]✓ No unknown tickers in batch {batch_id}[/green]\n")
            return

        table = Table(title=f"Unknown Tickers in Batch {batch_id}")
        table.add_column("Row", justify="right", style="dim")
        table.add_column("Ticker", style="cyan")
        table.add_column("Suggestions", style="yellow")
        table.add_column("Preview", style="dim")

        for unknown in unknowns:
            suggestions = ", ".join(unknown.suggestions[:3]) if unknown.suggestions else "None"
            preview = unknown.transaction_preview[:50] if unknown.transaction_preview else ""
            table.add_row(
                str(unknown.row_number),
                unknown.ticker,
                suggestions,
                preview,
            )

        console.print()
        console.print(table)

        console.print("\n[bold]Next Steps:[/bold]")
        console.print("Use one of these commands to resolve unknown tickers:\n")
        console.print(
            f"  [cyan]stocks-helper import correct-ticker {batch_id} <row> <correct-ticker>[/cyan]"
        )
        console.print(
            f"  [cyan]stocks-helper import ignore-tickers {batch_id} <row1> <row2> ...[/cyan]\n"
        )

    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise click.Abort()


@import_group.command(name="correct-ticker")
@click.argument("batch_id", type=int)
@click.argument("row_number", type=int)
@click.argument("corrected_ticker")
def correct_ticker(batch_id: int, row_number: int, corrected_ticker: str) -> None:
    """Correct an unknown ticker and retry import.

    BATCH_ID: Import batch ID
    ROW_NUMBER: Row number with unknown ticker
    CORRECTED_TICKER: Correct ticker symbol

    Example:
        stocks-helper import correct-ticker 123 45 AAPL
    """
    service = ImportService()

    try:
        imported_count = service.correct_ticker(
            batch_id=batch_id,
            row_numbers=[row_number],
            corrected_ticker=corrected_ticker,
        )

        console.print(
            f"\n[green]✓ Successfully imported {imported_count} transaction(s)![/green]\n"
        )

    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise click.Abort()


@import_group.command(name="ignore-tickers")
@click.argument("batch_id", type=int)
@click.argument("row_numbers", nargs=-1, type=int, required=True)
def ignore_tickers(batch_id: int, row_numbers: tuple[int, ...]) -> None:
    """Ignore unknown tickers (don't import these rows).

    BATCH_ID: Import batch ID
    ROW_NUMBERS: One or more row numbers to ignore

    Example:
        stocks-helper import ignore-tickers 123 45 46 47
    """
    service = ImportService()

    try:
        deleted_count = service.delete_error_rows(batch_id, list(row_numbers))

        console.print(f"\n[green]✓ Ignored {deleted_count} row(s)[/green]\n")

    except ValueError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise click.Abort()
