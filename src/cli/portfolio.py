"""Portfolio subcommands."""

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import SQLAlchemyError

from src.lib.db import db_session
from src.models import Portfolio
from src.services.currency_converter import CurrencyConverter
from src.services.market_data_fetcher import MarketDataFetcher

console = Console()


@click.group()  # type: ignore[misc]
def portfolio() -> None:
    """Manage investment portfolios."""
    pass


@portfolio.command()  # type: ignore[misc]
@click.option("--name", required=True, help="Portfolio name")  # type: ignore[misc]
@click.option("--currency", required=True, help="Base currency (USD, EUR, etc.)")  # type: ignore[misc]
def create(name: str, currency: str) -> None:
    """Create a new portfolio."""
    # Validate currency (3 chars uppercase)
    currency = currency.upper()
    if len(currency) != 3:
        console.print(
            f"[red]Error: Invalid currency '{currency}'. "
            f"Must be 3-letter ISO code (e.g., USD, EUR)[/red]"
        )
        return

    try:
        with db_session() as session:
            portfolio_obj = Portfolio(id=str(uuid.uuid4()), name=name, base_currency=currency)
            session.add(portfolio_obj)

            console.print("[green]Portfolio created successfully![/green]")
            console.print(f"ID: {portfolio_obj.id}")
            console.print(f"Name: {portfolio_obj.name}")
            console.print(f"Base Currency: {portfolio_obj.base_currency}")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


@portfolio.command()  # type: ignore[misc]
def list() -> None:
    """List all portfolios with total values."""
    try:
        with db_session() as session:
            portfolios = session.query(Portfolio).all()

            if not portfolios:
                console.print(
                    "[yellow]No portfolios found. Create one with 'portfolio create'.[/yellow]"
                )
                return

            table = Table(title="Portfolios")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Currency", style="yellow")
            table.add_column("Total Value", style="magenta")

            for p in portfolios:
                # Calculate total value from holdings
                total_value = _calculate_total_value(p)
                currency_symbol = _get_currency_symbol(p.base_currency)

                # Format the total value
                if total_value is not None:
                    value_str = f"{currency_symbol}{total_value:,.2f}"
                else:
                    value_str = f"{currency_symbol}0.00"

                table.add_row(p.id, p.name, p.base_currency, value_str)

            console.print(table)
    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


@portfolio.command()  # type: ignore[misc]
@click.argument("portfolio_id", required=False)  # type: ignore[misc]
def show(portfolio_id: str | None) -> None:
    """Show portfolio details (default to first if no ID provided)."""
    try:
        with db_session() as session:
            if portfolio_id:
                portfolio_obj = session.query(Portfolio).filter_by(id=portfolio_id).first()
                if not portfolio_obj:
                    console.print(f"[red]Error: Portfolio '{portfolio_id}' not found.[/red]")
                    return
            else:
                # Default to first portfolio
                portfolio_obj = session.query(Portfolio).first()
                if not portfolio_obj:
                    console.print(
                        "[yellow]No portfolios found. Create one with 'portfolio create'.[/yellow]"
                    )
                    return

            # Display portfolio details
            console.print(f"\n[bold cyan]Portfolio: {portfolio_obj.name}[/bold cyan]")
            console.print(f"ID: {portfolio_obj.id}")
            console.print(f"Base Currency: {portfolio_obj.base_currency}")
            console.print(f"Created: {portfolio_obj.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

            # Calculate summary
            holdings_count = len(portfolio_obj.holdings)
            total_value = _calculate_total_value(portfolio_obj)
            currency_symbol = _get_currency_symbol(portfolio_obj.base_currency)

            console.print("\n[bold]Summary:[/bold]")
            if total_value is not None:
                console.print(f"├─ Total Value: {currency_symbol}{total_value:,.2f}")
            else:
                console.print(f"├─ Total Value: {currency_symbol}0.00")
            console.print(f"├─ Holdings: {holdings_count} stocks")
            console.print(
                f"└─ Last Updated: {portfolio_obj.updated_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # Show holdings if any
            if holdings_count > 0:
                console.print("\n[bold]Holdings:[/bold]")
                table = Table()
                table.add_column("Ticker", style="cyan")
                table.add_column("Quantity", style="yellow", justify="right")
                table.add_column("Avg Price", style="green", justify="right")
                table.add_column("Currency", style="magenta")

                for holding in portfolio_obj.holdings:
                    table.add_row(
                        holding.ticker,
                        f"{holding.quantity:.2f}",
                        f"{holding.avg_purchase_price:.2f}",
                        holding.original_currency,
                    )

                console.print(table)
            else:
                console.print("\n[yellow]No holdings yet. Add stocks with 'holding add'.[/yellow]")

    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


@portfolio.command("set-currency")  # type: ignore[misc]
@click.argument("portfolio_id")  # type: ignore[misc]
@click.option("--currency", required=True, help="New base currency (USD, EUR, etc.)")  # type: ignore[misc]
def set_currency(portfolio_id: str, currency: str) -> None:
    """Change portfolio base currency."""
    # Validate currency (3 chars uppercase)
    currency = currency.upper()
    if len(currency) != 3:
        console.print(
            f"[red]Error: Invalid currency '{currency}'. "
            f"Must be 3-letter ISO code (e.g., USD, EUR)[/red]"
        )
        return

    try:
        with db_session() as session:
            portfolio_obj = session.query(Portfolio).filter_by(id=portfolio_id).first()
            if not portfolio_obj:
                console.print(f"[red]Error: Portfolio '{portfolio_id}' not found.[/red]")
                return

            old_currency = portfolio_obj.base_currency
            portfolio_obj.base_currency = currency

            console.print(
                f"[green]Portfolio currency updated from {old_currency} to {currency}.[/green]"
            )
            console.print(
                "[yellow]Note: Historical values would be recalculated using exchange rates "
                "(exchange rate functionality to be implemented).[/yellow]"
            )

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


def _calculate_total_value(portfolio_obj: Portfolio) -> Decimal | None:
    """
    Calculate total portfolio value from holdings using current market prices.

    Args:
        portfolio_obj: Portfolio instance

    Returns:
        Total value in portfolio base currency
    """
    if not portfolio_obj.holdings:
        return Decimal("0.00")

    market_data_fetcher = MarketDataFetcher()
    currency_converter = CurrencyConverter()
    total = Decimal("0.00")

    for holding in portfolio_obj.holdings:
        # Get current market price
        current_price = market_data_fetcher.get_current_price(holding.ticker)

        # Fall back to avg purchase price if market data unavailable
        if current_price is None:
            current_price = float(holding.avg_purchase_price)

        # Calculate holding value in original currency
        holding_value = Decimal(str(holding.quantity)) * Decimal(str(current_price))

        # Convert to portfolio base currency if needed
        if (
            portfolio_obj.base_currency
            and holding.original_currency
            and holding.original_currency != portfolio_obj.base_currency
        ):
            try:
                rate = asyncio.run(
                    currency_converter.get_rate(
                        holding.original_currency, portfolio_obj.base_currency, date.today()
                    )
                )
                if rate:
                    holding_value = holding_value * Decimal(str(rate))
            except Exception:
                # If conversion fails, use value in original currency
                # (better than skipping the holding entirely)
                pass

        total += holding_value

    return total


def _get_currency_symbol(currency_code: str) -> str:
    """
    Get currency symbol for display.

    Args:
        currency_code: ISO 4217 currency code

    Returns:
        Currency symbol string
    """
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "CHF": "CHF ",
        "CAD": "C$",
        "AUD": "A$",
        "NZD": "NZ$",
        "CNY": "¥",
    }
    return symbols.get(currency_code, f"{currency_code} ")
