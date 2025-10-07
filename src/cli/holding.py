"""Holding subcommands for managing stock positions."""

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import joinedload

from src.lib.db import db_session
from src.lib.validators import (
    validate_currency,
    validate_date,
    validate_price,
    validate_quantity,
    validate_ticker,
)
from src.models import Holding, Portfolio, SecurityType, Stock, Transaction, TransactionType
from src.services.currency_converter import CurrencyConverter
from src.services.market_data_fetcher import MarketDataFetcher

console = Console()


@click.group()
def holding() -> None:
    """Manage stock holdings."""
    pass


@holding.command()
@click.argument("portfolio_id")
@click.option("--ticker", required=True, help="Stock ticker symbol")
@click.option("--quantity", required=True, type=float, help="Number of shares")
@click.option("--price", required=True, type=float, help="Purchase price per share")
@click.option("--date", required=True, help="Purchase date (YYYY-MM-DD)")
@click.option("--currency", default="USD", help="Transaction currency")
@click.option("--fees", default=0.0, type=float, help="Transaction fees")
@click.option("--notes", default=None, help="Optional transaction notes")
def add(
    portfolio_id: str,
    ticker: str,
    quantity: float,
    price: float,
    date: str,
    currency: str,
    fees: float,
    notes: str | None,
) -> None:
    """Add a stock purchase to portfolio."""
    try:
        # Validate and parse inputs first (before DB session)
        try:
            # Parse date string and validate range
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
            purchase_date = validate_date(parsed_date)
        except ValueError as e:
            console.print(f"[red]Error: Invalid date format '{date}'. Use YYYY-MM-DD. {e}[/red]")
            return
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        try:
            ticker = validate_ticker(ticker)
            currency = validate_currency(currency)
            quantity_decimal = validate_quantity(Decimal(str(quantity)))
            price_decimal = validate_price(Decimal(str(price)))

            if fees < 0:
                console.print("[red]Error: Fees cannot be negative.[/red]")
                return
            fees_decimal = Decimal(str(fees))
        except (ValueError, Exception) as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        with db_session() as session:
            # Verify portfolio exists
            portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
            if not portfolio:
                console.print(f"[red]Error: Portfolio '{portfolio_id}' not found[/red]")
                console.print(
                    "[yellow]Run 'stocks-helper portfolio list' to see "
                    "available portfolios.[/yellow]"
                )
                return

            # Create stock if doesn't exist
            stock = session.query(Stock).filter_by(ticker=ticker).first()
            if not stock:
                stock = Stock(
                    ticker=ticker,
                    exchange="NASDAQ",  # Default, should ideally fetch from API
                    name=ticker,  # Placeholder - will be enriched by market data service
                    currency=currency,
                    last_updated=datetime.now(timezone.utc),
                )
                session.add(stock)
                session.flush()

            # Get or create holding with row lock to prevent concurrent updates
            holding = (
                session.query(Holding)
                .filter_by(portfolio_id=portfolio_id, ticker=ticker)
                .with_for_update()
                .first()
            )

            if holding:
                # Update existing holding - calculate weighted average price
                old_qty = holding.quantity
                old_avg = holding.avg_purchase_price
                new_qty = old_qty + quantity_decimal
                # Weighted average: (old_qty * old_avg + new_qty * new_price) / total_qty
                new_avg = (old_qty * old_avg + quantity_decimal * price_decimal) / new_qty
                holding.avg_purchase_price = new_avg
                holding.quantity = new_qty
                holding.updated_at = datetime.now(timezone.utc)
            else:
                # Create new holding
                holding = Holding(
                    id=str(uuid.uuid4()),
                    portfolio_id=portfolio_id,
                    ticker=ticker,
                    quantity=quantity_decimal,
                    avg_purchase_price=price_decimal,
                    original_currency=currency,
                    first_purchase_date=purchase_date,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(holding)
                session.flush()

            # Fetch exchange rate from transaction currency to portfolio base currency
            exchange_rate = Decimal("1.0")  # Default for same currency
            if portfolio.base_currency and currency != portfolio.base_currency:
                converter = CurrencyConverter()
                rate = asyncio.run(
                    converter.get_rate(currency, portfolio.base_currency, purchase_date)
                )
                if not rate:
                    console.print(
                        f"[red]Error: Cannot fetch exchange rate "
                        f"{currency}/{portfolio.base_currency}[/red]"
                    )
                    console.print("[red]Transaction aborted to prevent incorrect valuation.[/red]")
                    return
                exchange_rate = Decimal(str(rate))

            # Create transaction record
            transaction = Transaction(
                id=str(uuid.uuid4()),
                holding_id=holding.id,
                type=TransactionType.BUY,
                date=purchase_date,
                quantity=quantity_decimal,
                price=price_decimal,
                currency=currency,
                exchange_rate=exchange_rate,
                fees=fees_decimal,
                notes=notes,
                created_at=datetime.now(timezone.utc),
            )
            session.add(transaction)

            # Display success message
            total_cost = quantity_decimal * price_decimal + fees_decimal
            console.print("[green]Stock purchase recorded![/green]")
            console.print(f"Ticker: {ticker}")
            console.print(f"Quantity: {quantity} shares")
            console.print(f"Price: {currency} {price} per share")
            if fees > 0:
                console.print(
                    f"Total Cost: {currency} {quantity_decimal * price_decimal} + {fees} fees "
                    f"= {currency} {total_cost}"
                )
            else:
                console.print(f"Total Cost: {currency} {total_cost}")

            console.print("\nHolding updated:")
            console.print(f"├─ Total Quantity: {holding.quantity} shares")
            console.print(f"├─ Average Price: {currency} {holding.avg_purchase_price:.2f}")
            console.print("└─ Current Value: N/A (market data service not yet implemented)")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@holding.command()
@click.argument("portfolio_id")
@click.option("--ticker", required=True, help="Stock ticker symbol")
@click.option("--quantity", required=True, type=float, help="Number of shares to sell")
@click.option("--price", required=True, type=float, help="Sale price per share")
@click.option("--date", required=True, help="Sale date (YYYY-MM-DD)")
@click.option("--currency", default="USD", help="Transaction currency")
@click.option("--fees", default=0.0, type=float, help="Transaction fees")
@click.option("--notes", default=None, help="Optional transaction notes")
def sell(
    portfolio_id: str,
    ticker: str,
    quantity: float,
    price: float,
    date: str,
    currency: str,
    fees: float,
    notes: str | None,
) -> None:
    """Record a stock sale from portfolio."""
    try:
        # Validate and parse inputs first (before DB session)
        try:
            # Parse date string and validate range
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
            sale_date = validate_date(parsed_date)
        except ValueError as e:
            console.print(f"[red]Error: Invalid date format '{date}'. Use YYYY-MM-DD. {e}[/red]")
            return
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        try:
            ticker = validate_ticker(ticker)
            currency = validate_currency(currency)
            quantity_decimal = validate_quantity(Decimal(str(quantity)))
            price_decimal = validate_price(Decimal(str(price)))

            if fees < 0:
                console.print("[red]Error: Fees cannot be negative.[/red]")
                return
            fees_decimal = Decimal(str(fees))
        except (ValueError, Exception) as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        with db_session() as session:
            # Verify portfolio exists
            portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
            if not portfolio:
                console.print(f"[red]Error: Portfolio '{portfolio_id}' not found[/red]")
                return

            # Find holding with row lock to prevent concurrent updates
            holding = (
                session.query(Holding)
                .filter_by(portfolio_id=portfolio_id, ticker=ticker)
                .with_for_update()
                .first()
            )

            if not holding:
                console.print(f"[red]Error: Stock '{ticker}' not found in portfolio.[/red]")
                console.print(
                    f"[yellow]Run 'stocks-helper holding list {portfolio_id}' to see "
                    "holdings.[/yellow]"
                )
                return

            # Validate sufficient quantity
            if holding.quantity < quantity_decimal:
                console.print(
                    f"[red]Error: Cannot sell {quantity} shares. "
                    f"Only {holding.quantity} shares available.[/red]"
                )
                return

            # Calculate gain/loss for this sale
            cost_basis = holding.avg_purchase_price * quantity_decimal
            proceeds = price_decimal * quantity_decimal - fees_decimal
            gain_loss = proceeds - cost_basis
            gain_loss_pct = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0

            # Update holding quantity
            new_quantity = holding.quantity - quantity_decimal
            if new_quantity == 0:
                # Delete holding if fully sold
                session.delete(holding)
                holding_deleted = True
            else:
                holding.quantity = new_quantity
                holding.updated_at = datetime.now(timezone.utc)
                holding_deleted = False

            # Fetch exchange rate from transaction currency to portfolio base currency
            exchange_rate = Decimal("1.0")  # Default for same currency
            if portfolio.base_currency and currency != portfolio.base_currency:
                try:
                    converter = CurrencyConverter()
                    rate = asyncio.run(
                        converter.get_rate(currency, portfolio.base_currency, sale_date)
                    )
                    if rate:
                        exchange_rate = Decimal(str(rate))
                    else:
                        console.print(
                            f"[yellow]Warning: Could not fetch exchange rate "
                            f"{currency}/{portfolio.base_currency}. Using 1.0[/yellow]"
                        )
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Exchange rate fetch failed: {e}. Using 1.0[/yellow]"
                    )

            # Create transaction record
            transaction = Transaction(
                id=str(uuid.uuid4()),
                holding_id=holding.id,
                type=TransactionType.SELL,
                date=sale_date,
                quantity=quantity_decimal,
                price=price_decimal,
                currency=currency,
                exchange_rate=exchange_rate,
                fees=fees_decimal,
                notes=notes,
                created_at=datetime.now(timezone.utc),
            )
            session.add(transaction)

            # Display success message
            console.print("[green]Stock sale recorded![/green]")
            console.print(f"Ticker: {ticker}")
            console.print(f"Quantity: {quantity} shares sold")
            console.print(f"Sale Price: {currency} {price} per share")
            if fees > 0:
                console.print(
                    f"Total Proceeds: {currency} {quantity_decimal * price_decimal} - {fees} fees "
                    f"= {currency} {proceeds}"
                )
            else:
                console.print(f"Total Proceeds: {currency} {proceeds}")

            # Show gain/loss
            gain_color = "green" if gain_loss >= 0 else "red"
            gain_sign = "+" if gain_loss >= 0 else ""
            console.print(
                f"\nGain/Loss on this sale: [{gain_color}]{gain_sign}{currency} {gain_loss:.2f} "
                f"({gain_sign}{gain_loss_pct:.2f}%)[/{gain_color}]"
            )

            # Show remaining holding
            if holding_deleted:
                console.print("\n[yellow]Position fully closed.[/yellow]")
            else:
                console.print("\nRemaining holding:")
                console.print(f"├─ Quantity: {holding.quantity} shares")
                console.print(f"├─ Average Price: {currency} {holding.avg_purchase_price:.2f}")
                console.print("└─ Current Value: N/A (market data service not yet implemented)")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@holding.command("list")
@click.argument("portfolio_id")
@click.option(
    "--sort-by",
    default="ticker",
    type=click.Choice(["ticker", "quantity", "value"], case_sensitive=False),
    help="Sort by field",
)
@click.option(
    "--order",
    default="ASC",
    type=click.Choice(["ASC", "DESC"], case_sensitive=False),
    help="Sort order",
)
def list_holdings(portfolio_id: str, sort_by: str, order: str) -> None:
    """List all holdings in a portfolio."""
    try:
        with db_session() as session:
            # Verify portfolio exists
            portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
            if not portfolio:
                console.print(f"[red]Error: Portfolio '{portfolio_id}' not found[/red]")
                return

            # Get all holdings with eager loading to avoid N+1 queries
            query = (
                session.query(Holding)
                .options(joinedload(Holding.security))  # Eager load security relationship
                .filter(Holding.portfolio_id == portfolio_id)
            )

            # Apply sorting
            if sort_by.lower() == "ticker":
                query = query.order_by(
                    Holding.ticker.asc() if order.upper() == "ASC" else Holding.ticker.desc()
                )
            elif sort_by.lower() == "quantity":
                query = query.order_by(
                    Holding.quantity.asc() if order.upper() == "ASC" else Holding.quantity.desc()
                )
            # Note: 'value' sorting requires market data, using ticker as fallback
            else:
                query = query.order_by(Holding.ticker.asc())

            holdings = query.all()

            if not holdings:
                console.print(
                    f"[yellow]No holdings found in portfolio '{portfolio.name}'.[/yellow]"
                )
                console.print("[yellow]Add holdings with 'stocks-helper holding add'.[/yellow]")
                return

            # Create table
            table = Table(title=f"Holdings in {portfolio.name} ({len(holdings)} securities)")
            table.add_column("Ticker", style="cyan", no_wrap=True)
            table.add_column("Type", style="dim", no_wrap=True)
            table.add_column("Name", style="white")
            table.add_column("Quantity", justify="right", style="yellow")
            table.add_column("Avg Price", justify="right", style="blue")
            table.add_column("Currency", style="magenta")
            table.add_column("Current", justify="right", style="white")
            table.add_column("Value", justify="right", style="white")
            table.add_column("Gain/Loss", justify="right", style="white")

            # Initialize market data fetcher and bulk fetch all prices
            market_data_fetcher = MarketDataFetcher()
            all_tickers = [h.ticker for h in holdings]
            current_prices = market_data_fetcher.get_current_prices(all_tickers)

            # Initialize currency converter for converting to base currency
            currency_converter = CurrencyConverter()

            total_cost = Decimal("0")
            total_value = Decimal("0")
            for holding in holdings:
                security = holding.security
                cost_local = holding.quantity * holding.avg_purchase_price

                # Get exchange rate once and reuse for both cost and value
                exchange_rate = None
                if security.currency != portfolio.base_currency:
                    exchange_rate = asyncio.run(
                        currency_converter.get_rate(
                            security.currency, portfolio.base_currency, datetime.now().date()
                        )
                    )

                # Convert cost to portfolio base currency
                if exchange_rate:
                    cost = cost_local * Decimal(str(exchange_rate))
                else:
                    cost = cost_local

                total_cost += cost

                # Get current price from bulk fetch result
                current_price = current_prices.get(holding.ticker)

                if current_price is not None:
                    # Current value in the security's currency
                    current_value_local = holding.quantity * Decimal(str(current_price))

                    # Convert to portfolio base currency using same exchange rate
                    if exchange_rate:
                        current_value = current_value_local * Decimal(str(exchange_rate))
                    else:
                        current_value = current_value_local

                    total_value += current_value
                    gain_loss = current_value - cost
                    gain_loss_pct = (gain_loss / cost * 100) if cost > 0 else Decimal("0")

                    # Format gain/loss with color
                    if gain_loss >= 0:
                        gain_loss_str = f"[green]+{gain_loss:.2f} (+{gain_loss_pct:.1f}%)[/green]"
                    else:
                        gain_loss_str = f"[red]{gain_loss:.2f} ({gain_loss_pct:.1f}%)[/red]"

                    # Security type badge
                    type_badge = security.security_type.value
                    if security.archived:
                        type_badge += " [dim](archived)[/dim]"

                    table.add_row(
                        holding.ticker,
                        type_badge,
                        security.name,
                        f"{holding.quantity:.2f}",
                        f"{holding.avg_purchase_price:.2f}",
                        holding.original_currency,
                        f"{current_price:.2f}",
                        f"{current_value:.2f}",
                        gain_loss_str,
                    )
                else:
                    # No market data available
                    # Security type badge
                    type_badge = security.security_type.value
                    if security.archived:
                        type_badge += " [dim](archived)[/dim]"
                        # Archived securities: show 0 for current price/value/gain
                        total_value += Decimal("0")  # Worth nothing
                        table.add_row(
                            holding.ticker,
                            type_badge,
                            security.name,
                            f"{holding.quantity:.2f}",
                            f"{holding.avg_purchase_price:.2f}",
                            holding.original_currency,
                            "0.00",
                            "0.00",
                            "0.00 (0.0%)",
                        )
                    elif security.security_type in (SecurityType.BOND, SecurityType.FUND):
                        # Bonds and funds: show avg price as current, cost as value, 0 gain/loss
                        total_value += cost  # Use cost basis as value
                        table.add_row(
                            holding.ticker,
                            type_badge,
                            security.name,
                            f"{holding.quantity:.2f}",
                            f"{holding.avg_purchase_price:.2f}",
                            holding.original_currency,
                            f"{holding.avg_purchase_price:.2f}",
                            f"{cost:.2f}",
                            "0.00 (0.0%)",
                        )
                    else:
                        # Stocks with no price data: show N/A
                        total_value += cost  # Use cost as fallback
                        table.add_row(
                            holding.ticker,
                            type_badge,
                            security.name,
                            f"{holding.quantity:.2f}",
                            f"{holding.avg_purchase_price:.2f}",
                            holding.original_currency,
                            "N/A",
                            "N/A",
                            "N/A",
                        )

            console.print(table)

            # Calculate total gain/loss
            total_gain_loss = total_value - total_cost
            total_gain_loss_pct = (
                (total_gain_loss / total_cost * 100) if total_cost > 0 else Decimal("0")
            )

            if total_gain_loss >= 0:
                gain_color = "green"
                gain_sign = "+"
            else:
                gain_color = "red"
                gain_sign = ""

            console.print(
                f"\n[bold]Total Cost:[/bold] {portfolio.base_currency} {total_cost:.2f} | "
                f"[bold]Total Value:[/bold] {portfolio.base_currency} {total_value:.2f} | "
                f"[bold]Gain/Loss:[/bold] [{gain_color}]{gain_sign}"
                f"{portfolio.base_currency} {total_gain_loss:.2f} "
                f"({gain_sign}{total_gain_loss_pct:.1f}%)[/{gain_color}]"
            )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@holding.command()
@click.argument("portfolio_id")
@click.option("--ticker", required=True, help="Stock ticker symbol")
def show(portfolio_id: str, ticker: str) -> None:
    """Show detailed holding information."""
    try:
        # Validate ticker first
        try:
            ticker = validate_ticker(ticker)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        with db_session() as session:
            # Verify portfolio exists
            portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
            if not portfolio:
                console.print(f"[red]Error: Portfolio '{portfolio_id}' not found[/red]")
                return

            # Find holding
            holding = (
                session.query(Holding).filter_by(portfolio_id=portfolio_id, ticker=ticker).first()
            )

            if not holding:
                console.print(f"[red]Error: Stock '{ticker}' not found in portfolio.[/red]")
                return

            stock = holding.stock

            # Display holding details
            console.print(
                f"\n[bold cyan]Holding Details: {ticker}[/bold cyan] [white]({stock.name})[/white]"
            )
            console.print(f"Portfolio: {portfolio.name}\n")

            # Fetch current market price
            market_data_fetcher = MarketDataFetcher()
            current_price = market_data_fetcher.get_current_price(ticker)

            console.print("[bold]Current Position:[/bold]")
            console.print(f"├─ Quantity: {holding.quantity} shares")
            console.print(
                f"├─ Average Price: {holding.original_currency} {holding.avg_purchase_price:.2f}"
            )

            total_cost = holding.quantity * holding.avg_purchase_price

            if current_price is not None:
                console.print(f"├─ Current Price: {holding.original_currency} {current_price:.2f}")
                current_value = holding.quantity * Decimal(str(current_price))
                gain_loss = current_value - total_cost
                gain_loss_pct = (gain_loss / total_cost * 100) if total_cost > 0 else Decimal("0")

                console.print(f"├─ Total Cost: {holding.original_currency} {total_cost:.2f}")
                console.print(f"├─ Current Value: {holding.original_currency} {current_value:.2f}")

                # Format gain/loss with color
                if gain_loss >= 0:
                    console.print(
                        f"└─ Gain/Loss: [green]+{holding.original_currency} {gain_loss:.2f} "
                        f"(+{gain_loss_pct:.1f}%)[/green]\n"
                    )
                else:
                    console.print(
                        f"└─ Gain/Loss: [red]{holding.original_currency} {gain_loss:.2f} "
                        f"({gain_loss_pct:.1f}%)[/red]\n"
                    )
            else:
                console.print("├─ Current Price: N/A (no market data available)")
                console.print(f"├─ Total Cost: {holding.original_currency} {total_cost:.2f}")
                console.print("├─ Current Value: N/A (no market data available)")
                console.print("└─ Gain/Loss: N/A (no market data available)\n")

            # Get transaction history
            transactions = (
                session.query(Transaction)
                .filter_by(holding_id=holding.id)
                .order_by(Transaction.date.desc())
                .all()
            )

            if transactions:
                console.print("[bold]Transaction History:[/bold]")
                table = Table()
                table.add_column("Date", style="cyan")
                table.add_column("Type", style="yellow")
                table.add_column("Quantity", justify="right", style="white")
                table.add_column("Price", justify="right", style="blue")
                table.add_column("Currency", style="magenta")
                table.add_column("Fees", justify="right", style="red")
                table.add_column("Total Cost", justify="right", style="green")

                for txn in transactions:
                    # Calculate total (handle None for FEE transactions)
                    if txn.quantity is not None and txn.price is not None:
                        total = txn.quantity * txn.price
                        if txn.type == TransactionType.BUY:
                            total += txn.fees
                        else:
                            total -= txn.fees
                    else:
                        # For FEE transactions without quantity/price, show fees as total
                        total = txn.fees

                    table.add_row(
                        str(txn.date),
                        txn.type.value,
                        f"{txn.quantity:.2f}" if txn.quantity is not None else "N/A",
                        f"{txn.price:.2f}" if txn.price is not None else "N/A",
                        txn.currency,
                        f"{txn.fees:.2f}",
                        f"{total:.2f}",
                    )

                console.print(table)
            else:
                console.print("[yellow]No transaction history available.[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
