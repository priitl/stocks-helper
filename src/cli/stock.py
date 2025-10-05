"""CLI commands for managing stock metadata."""

import asyncio

import click
from rich.console import Console
from rich.table import Table

from src.lib.db import get_session
from src.models.stock import Stock
from src.services.fundamental_analyzer import FundamentalAnalyzer

console = Console()


@click.group()
def stock():
    """Manage stock metadata."""
    pass


@stock.command("add")
@click.option("--ticker", required=True, help="Stock ticker symbol")
@click.option("--name", help="Company name")
@click.option("--exchange", default="NASDAQ", help="Stock exchange")
@click.option("--sector", help="Sector (e.g., Technology)")
@click.option("--country", default="US", help="Country code")
def add_stock(ticker, name, exchange, sector, country):
    """Add a stock to the database."""

    async def fetch_and_add():
        session = get_session()
        try:
            # Check if already exists
            existing = session.query(Stock).filter(Stock.ticker == ticker.upper()).first()
            if existing:
                console.print(f"[yellow]Stock {ticker} already exists[/yellow]")
                return

            # Try to fetch fundamental data to get company info
            analyzer = FundamentalAnalyzer()
            fundamental_data = await analyzer.fetch_fundamental_data(ticker.upper())

            if fundamental_data:
                # Extract company info from Alpha Vantage
                console.print(f"[cyan]Fetching company info for {ticker}...[/cyan]")

            # Create stock entry
            stock_entry = Stock(
                ticker=ticker.upper(),
                exchange=exchange,
                name=name or ticker.upper(),
                sector=sector or "Unknown",
                country=country,
            )

            session.add(stock_entry)
            session.commit()

            console.print(f"[green]✓ Added {ticker.upper()}[/green]")
            console.print(f"  Exchange: {exchange}")
            console.print(f"  Sector: {sector or 'Unknown'}")
            console.print(f"  Country: {country}")

        except Exception as e:
            session.rollback()
            console.print(f"[red]✗ Failed to add {ticker}: {e}[/red]")
        finally:
            session.close()

    asyncio.run(fetch_and_add())


@stock.command("add-batch")
@click.option("--tickers", required=True, help="Comma-separated list of tickers")
@click.option("--exchange", default="NASDAQ", help="Stock exchange")
@click.option("--country", default="US", help="Country code")
def add_batch(tickers, exchange, country):
    """Add multiple stocks at once with metadata lookup."""

    # Common tech stocks metadata
    tech_stocks = {
        "NVDA": {"name": "NVIDIA Corp", "sector": "Technology", "market_cap": 3000000000000},
        "AMD": {
            "name": "Advanced Micro Devices",
            "sector": "Technology",
            "market_cap": 250000000000,
        },
        "INTC": {"name": "Intel Corporation", "sector": "Technology", "market_cap": 200000000000},
        "META": {"name": "Meta Platforms", "sector": "Technology", "market_cap": 900000000000},
        "GOOGL": {"name": "Alphabet Inc", "sector": "Technology", "market_cap": 1800000000000},
        "TSLA": {"name": "Tesla Inc", "sector": "Automotive", "market_cap": 800000000000},
        "TSM": {"name": "Taiwan Semiconductor", "sector": "Technology", "market_cap": 600000000000},
        "NFLX": {"name": "Netflix Inc", "sector": "Entertainment", "market_cap": 300000000000},
        "DIS": {"name": "Walt Disney Co", "sector": "Entertainment", "market_cap": 200000000000},
        "JPM": {"name": "JPMorgan Chase", "sector": "Financial", "market_cap": 500000000000},
        "JNJ": {"name": "Johnson & Johnson", "sector": "Healthcare", "market_cap": 400000000000},
        "XOM": {"name": "Exxon Mobil", "sector": "Energy", "market_cap": 450000000000},
    }

    ticker_list = [t.strip().upper() for t in tickers.split(",")]

    session = get_session()
    try:
        added = 0
        skipped = 0

        for ticker in ticker_list:
            # Check if already exists
            existing = session.query(Stock).filter(Stock.ticker == ticker).first()
            if existing:
                console.print(f"[yellow]⏭️  {ticker}: Already exists[/yellow]")
                skipped += 1
                continue

            # Get metadata if available
            metadata = tech_stocks.get(ticker, {})

            stock_entry = Stock(
                ticker=ticker,
                exchange=exchange,
                name=metadata.get("name", ticker),
                currency="USD",  # Default currency
                sector=metadata.get("sector", "Unknown"),
                country=country,
                market_cap=metadata.get("market_cap"),
            )

            session.add(stock_entry)
            console.print(
                f"[green]✓ {ticker}: {metadata.get('name', ticker)} ({metadata.get('sector', 'Unknown')})[/green]"
            )
            added += 1

        session.commit()

        console.print("\n[bold]Summary:[/bold]")
        console.print(f"  Added: {added}")
        console.print(f"  Skipped: {skipped}")

    except Exception as e:
        session.rollback()
        console.print(f"[red]Error: {e}[/red]")
    finally:
        session.close()


@stock.command("list")
def list_stocks():
    """List all stocks in database."""
    session = get_session()
    try:
        stocks = session.query(Stock).order_by(Stock.ticker).all()

        if not stocks:
            console.print("[yellow]No stocks found[/yellow]")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Ticker")
        table.add_column("Name")
        table.add_column("Exchange")
        table.add_column("Sector")
        table.add_column("Country")

        for stock in stocks:
            table.add_row(
                stock.ticker,
                stock.name or "",
                stock.exchange or "",
                stock.sector or "",
                stock.country or "",
            )

        console.print(table)
        console.print(f"\nTotal: {len(stocks)} stocks")

    finally:
        session.close()


@stock.command("remove")
@click.option("--ticker", required=True, help="Stock ticker to remove")
def remove_stock(ticker):
    """Remove a stock from database."""
    session = get_session()
    try:
        stock = session.query(Stock).filter(Stock.ticker == ticker.upper()).first()

        if not stock:
            console.print(f"[yellow]Stock {ticker} not found[/yellow]")
            return

        session.delete(stock)
        session.commit()

        console.print(f"[green]✓ Removed {ticker.upper()}[/green]")

    except Exception as e:
        session.rollback()
        console.print(f"[red]Error: {e}[/red]")
    finally:
        session.close()


if __name__ == "__main__":
    stock()
