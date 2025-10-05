"""Holding subcommands for managing stock positions."""

import uuid
from datetime import datetime
from decimal import Decimal

import click
from rich.console import Console
from rich.table import Table

from src.lib.db import get_session
from src.models import Holding, Portfolio, Stock, Transaction, TransactionType

console = Console()


@click.group()
def holding():
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
def add(portfolio_id, ticker, quantity, price, date, currency, fees, notes):
    """Add a stock purchase to portfolio."""
    session = get_session()
    try:
        # Verify portfolio exists
        portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
        if not portfolio:
            console.print(f"[red]Error: Portfolio '{portfolio_id}' not found[/red]")
            console.print(
                "[yellow]Run 'stocks-helper portfolio list' to see available portfolios.[/yellow]"
            )
            return

        # Validate and parse inputs
        try:
            purchase_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            console.print(
                f"[red]Error: Invalid date format '{date}'. Use YYYY-MM-DD.[/red]"
            )
            return

        if quantity <= 0:
            console.print("[red]Error: Quantity must be positive.[/red]")
            return

        if price <= 0:
            console.print("[red]Error: Price must be positive.[/red]")
            return

        if fees < 0:
            console.print("[red]Error: Fees cannot be negative.[/red]")
            return

        ticker = ticker.upper()
        currency = currency.upper()

        # Create stock if doesn't exist
        stock = session.query(Stock).filter_by(ticker=ticker).first()
        if not stock:
            stock = Stock(
                ticker=ticker,
                exchange="NASDAQ",  # Default, should ideally fetch from API
                name=ticker,  # Placeholder - will be enriched by market data service
                currency=currency,
                last_updated=datetime.utcnow(),
            )
            session.add(stock)
            session.flush()

        # Get or create holding
        holding = (
            session.query(Holding)
            .filter_by(portfolio_id=portfolio_id, ticker=ticker)
            .first()
        )

        qty_decimal = Decimal(str(quantity))
        price_decimal = Decimal(str(price))
        fees_decimal = Decimal(str(fees))

        if holding:
            # Update existing holding - calculate weighted average price
            old_qty = holding.quantity
            old_avg = holding.avg_purchase_price
            new_qty = old_qty + qty_decimal
            # Weighted average: (old_qty * old_avg + new_qty * new_price) / total_qty
            holding.avg_purchase_price = (
                old_qty * old_avg + qty_decimal * price_decimal
            ) / new_qty
            holding.quantity = new_qty
            holding.updated_at = datetime.utcnow()
        else:
            # Create new holding
            holding = Holding(
                id=str(uuid.uuid4()),
                portfolio_id=portfolio_id,
                ticker=ticker,
                quantity=qty_decimal,
                avg_purchase_price=price_decimal,
                original_currency=currency,
                first_purchase_date=purchase_date,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(holding)
            session.flush()

        # Create transaction record
        transaction = Transaction(
            id=str(uuid.uuid4()),
            holding_id=holding.id,
            type=TransactionType.BUY,
            date=purchase_date,
            quantity=qty_decimal,
            price=price_decimal,
            currency=currency,
            exchange_rate=Decimal("1.0"),  # TODO: Fetch real exchange rate
            fees=fees_decimal,
            notes=notes,
            created_at=datetime.utcnow(),
        )
        session.add(transaction)
        session.commit()

        # Display success message
        total_cost = qty_decimal * price_decimal + fees_decimal
        console.print("[green]Stock purchase recorded![/green]")
        console.print(f"Ticker: {ticker}")
        console.print(f"Quantity: {quantity} shares")
        console.print(f"Price: {currency} {price} per share")
        if fees > 0:
            console.print(
                f"Total Cost: {currency} {qty_decimal * price_decimal} + {fees} fees = {currency} {total_cost}"
            )
        else:
            console.print(f"Total Cost: {currency} {total_cost}")

        console.print("\nHolding updated:")
        console.print(f"├─ Total Quantity: {holding.quantity} shares")
        console.print(f"├─ Average Price: {currency} {holding.avg_purchase_price:.2f}")
        console.print(
            f"└─ Current Value: N/A (market data service not yet implemented)"
        )

    except Exception as e:
        session.rollback()
        console.print(f"[red]Error: {e}[/red]")
    finally:
        session.close()


@holding.command()
@click.argument("portfolio_id")
@click.option("--ticker", required=True, help="Stock ticker symbol")
@click.option("--quantity", required=True, type=float, help="Number of shares to sell")
@click.option("--price", required=True, type=float, help="Sale price per share")
@click.option("--date", required=True, help="Sale date (YYYY-MM-DD)")
@click.option("--currency", default="USD", help="Transaction currency")
@click.option("--fees", default=0.0, type=float, help="Transaction fees")
@click.option("--notes", default=None, help="Optional transaction notes")
def sell(portfolio_id, ticker, quantity, price, date, currency, fees, notes):
    """Record a stock sale from portfolio."""
    session = get_session()
    try:
        # Verify portfolio exists
        portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
        if not portfolio:
            console.print(f"[red]Error: Portfolio '{portfolio_id}' not found[/red]")
            return

        # Validate and parse inputs
        try:
            sale_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            console.print(
                f"[red]Error: Invalid date format '{date}'. Use YYYY-MM-DD.[/red]"
            )
            return

        if quantity <= 0:
            console.print("[red]Error: Quantity must be positive.[/red]")
            return

        if price <= 0:
            console.print("[red]Error: Price must be positive.[/red]")
            return

        if fees < 0:
            console.print("[red]Error: Fees cannot be negative.[/red]")
            return

        ticker = ticker.upper()
        currency = currency.upper()

        # Find holding
        holding = (
            session.query(Holding)
            .filter_by(portfolio_id=portfolio_id, ticker=ticker)
            .first()
        )

        if not holding:
            console.print(
                f"[red]Error: Stock '{ticker}' not found in portfolio.[/red]"
            )
            console.print(
                f"[yellow]Run 'stocks-helper holding list {portfolio_id}' to see holdings.[/yellow]"
            )
            return

        qty_decimal = Decimal(str(quantity))
        price_decimal = Decimal(str(price))
        fees_decimal = Decimal(str(fees))

        # Validate sufficient quantity
        if holding.quantity < qty_decimal:
            console.print(
                f"[red]Error: Cannot sell {quantity} shares. Only {holding.quantity} shares available.[/red]"
            )
            return

        # Calculate gain/loss for this sale
        cost_basis = holding.avg_purchase_price * qty_decimal
        proceeds = price_decimal * qty_decimal - fees_decimal
        gain_loss = proceeds - cost_basis
        gain_loss_pct = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0

        # Update holding quantity
        new_quantity = holding.quantity - qty_decimal
        if new_quantity == 0:
            # Delete holding if fully sold
            session.delete(holding)
            holding_deleted = True
        else:
            holding.quantity = new_quantity
            holding.updated_at = datetime.utcnow()
            holding_deleted = False

        # Create transaction record
        transaction = Transaction(
            id=str(uuid.uuid4()),
            holding_id=holding.id,
            type=TransactionType.SELL,
            date=sale_date,
            quantity=qty_decimal,
            price=price_decimal,
            currency=currency,
            exchange_rate=Decimal("1.0"),  # TODO: Fetch real exchange rate
            fees=fees_decimal,
            notes=notes,
            created_at=datetime.utcnow(),
        )
        session.add(transaction)
        session.commit()

        # Display success message
        console.print("[green]Stock sale recorded![/green]")
        console.print(f"Ticker: {ticker}")
        console.print(f"Quantity: {quantity} shares sold")
        console.print(f"Sale Price: {currency} {price} per share")
        if fees > 0:
            console.print(
                f"Total Proceeds: {currency} {qty_decimal * price_decimal} - {fees} fees = {currency} {proceeds}"
            )
        else:
            console.print(f"Total Proceeds: {currency} {proceeds}")

        # Show gain/loss
        gain_color = "green" if gain_loss >= 0 else "red"
        gain_sign = "+" if gain_loss >= 0 else ""
        console.print(
            f"\nGain/Loss on this sale: [{gain_color}]{gain_sign}{currency} {gain_loss:.2f} ({gain_sign}{gain_loss_pct:.2f}%)[/{gain_color}]"
        )

        # Show remaining holding
        if holding_deleted:
            console.print("\n[yellow]Position fully closed.[/yellow]")
        else:
            console.print("\nRemaining holding:")
            console.print(f"├─ Quantity: {holding.quantity} shares")
            console.print(
                f"├─ Average Price: {currency} {holding.avg_purchase_price:.2f}"
            )
            console.print(
                f"└─ Current Value: N/A (market data service not yet implemented)"
            )

    except Exception as e:
        session.rollback()
        console.print(f"[red]Error: {e}[/red]")
    finally:
        session.close()


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
def list_holdings(portfolio_id, sort_by, order):
    """List all holdings in a portfolio."""
    session = get_session()
    try:
        # Verify portfolio exists
        portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
        if not portfolio:
            console.print(f"[red]Error: Portfolio '{portfolio_id}' not found[/red]")
            return

        # Get all holdings
        query = (
            session.query(Holding)
            .join(Stock, Holding.ticker == Stock.ticker)
            .filter(Holding.portfolio_id == portfolio_id)
        )

        # Apply sorting
        if sort_by.lower() == "ticker":
            query = query.order_by(
                Holding.ticker.asc() if order.upper() == "ASC" else Holding.ticker.desc()
            )
        elif sort_by.lower() == "quantity":
            query = query.order_by(
                Holding.quantity.asc()
                if order.upper() == "ASC"
                else Holding.quantity.desc()
            )
        # Note: 'value' sorting requires market data, using ticker as fallback
        else:
            query = query.order_by(Holding.ticker.asc())

        holdings = query.all()

        if not holdings:
            console.print(
                f"[yellow]No holdings found in portfolio '{portfolio.name}'.[/yellow]"
            )
            console.print(
                "[yellow]Add holdings with 'stocks-helper holding add'.[/yellow]"
            )
            return

        # Create table
        table = Table(title=f"Holdings in {portfolio.name} ({len(holdings)} stocks)")
        table.add_column("Ticker", style="cyan", no_wrap=True)
        table.add_column("Name", style="white")
        table.add_column("Quantity", justify="right", style="yellow")
        table.add_column("Avg Price", justify="right", style="blue")
        table.add_column("Currency", style="magenta")
        table.add_column("Current", justify="right", style="white")
        table.add_column("Value", justify="right", style="white")
        table.add_column("Gain/Loss", justify="right", style="white")

        total_cost = Decimal("0")
        for holding in holdings:
            stock = holding.stock
            cost = holding.quantity * holding.avg_purchase_price
            total_cost += cost

            table.add_row(
                holding.ticker,
                stock.name,
                f"{holding.quantity:.2f}",
                f"{holding.avg_purchase_price:.2f}",
                holding.original_currency,
                "N/A",  # Current price - requires market data service
                "N/A",  # Current value - requires market data service
                "N/A",  # Gain/Loss - requires market data service
            )

        console.print(table)
        console.print(
            f"\nTotal Cost: {portfolio.base_currency} {total_cost:.2f} | "
            f"Total Value: N/A | Gain/Loss: N/A"
        )
        console.print(
            "[dim]Market data service not yet implemented - showing N/A for current values[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    finally:
        session.close()


@holding.command()
@click.argument("portfolio_id")
@click.option("--ticker", required=True, help="Stock ticker symbol")
def show(portfolio_id, ticker):
    """Show detailed holding information."""
    session = get_session()
    try:
        # Verify portfolio exists
        portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
        if not portfolio:
            console.print(f"[red]Error: Portfolio '{portfolio_id}' not found[/red]")
            return

        ticker = ticker.upper()

        # Find holding
        holding = (
            session.query(Holding)
            .filter_by(portfolio_id=portfolio_id, ticker=ticker)
            .first()
        )

        if not holding:
            console.print(
                f"[red]Error: Stock '{ticker}' not found in portfolio.[/red]"
            )
            return

        stock = holding.stock

        # Display holding details
        console.print(
            f"\n[bold cyan]Holding Details: {ticker}[/bold cyan] [white]({stock.name})[/white]"
        )
        console.print(f"Portfolio: {portfolio.name}\n")

        console.print("[bold]Current Position:[/bold]")
        console.print(f"├─ Quantity: {holding.quantity} shares")
        console.print(
            f"├─ Average Price: {holding.original_currency} {holding.avg_purchase_price:.2f}"
        )
        console.print(f"├─ Current Price: N/A (market data not available)")
        total_cost = holding.quantity * holding.avg_purchase_price
        console.print(f"├─ Total Cost: {holding.original_currency} {total_cost:.2f}")
        console.print(f"├─ Current Value: N/A (market data not available)")
        console.print(f"└─ Gain/Loss: N/A (market data not available)\n")

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
                total = txn.quantity * txn.price
                if txn.type == TransactionType.BUY:
                    total += txn.fees
                else:
                    total -= txn.fees

                table.add_row(
                    str(txn.date),
                    txn.type.value,
                    f"{txn.quantity:.2f}",
                    f"{txn.price:.2f}",
                    txn.currency,
                    f"{txn.fees:.2f}",
                    f"{total:.2f}",
                )

            console.print(table)
        else:
            console.print("[yellow]No transaction history available.[/yellow]")

        console.print(
            "\n[dim]Market data and recommendations not yet implemented[/dim]"
        )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    finally:
        session.close()
