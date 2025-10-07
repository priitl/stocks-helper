"""CLI commands for managing stock metadata."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import click
from rich.console import Console
from rich.table import Table

from src.lib.db import db_session
from src.lib.validators import validate_ticker
from src.models import Bond, MarketData, Security, SecurityType, Stock
from src.services.fundamental_analyzer import FundamentalAnalyzer

console = Console()


@click.group()
def stock() -> None:
    """Manage stock metadata."""
    pass


@stock.command("add")
@click.option("--ticker", required=True, help="Stock ticker symbol")
@click.option("--name", help="Company name")
@click.option("--exchange", default="NASDAQ", help="Stock exchange")
@click.option("--sector", help="Sector (e.g., Technology)")
@click.option("--country", default="US", help="Country code")
def add_stock(
    ticker: str, name: str | None, exchange: str, sector: str | None, country: str
) -> None:
    """Add a stock to the database."""

    async def fetch_and_add() -> None:
        try:
            # Validate ticker
            try:
                validated_ticker = validate_ticker(ticker)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                return

            with db_session() as session:
                # Check if already exists
                existing = session.query(Stock).filter(Stock.ticker == validated_ticker).first()
                if existing:
                    console.print(f"[yellow]Stock {validated_ticker} already exists[/yellow]")
                    return

                # Try to fetch fundamental data to get company info
                analyzer = FundamentalAnalyzer()
                fundamental_data = await analyzer.fetch_fundamental_data(validated_ticker)

                if fundamental_data:
                    # Extract company info from Alpha Vantage
                    console.print(f"[cyan]Fetching company info for {validated_ticker}...[/cyan]")

                # Create stock entry
                stock_entry = Stock(
                    ticker=validated_ticker,
                    exchange=exchange,
                    name=name or validated_ticker,
                    sector=sector or "Unknown",
                    country=country,
                )

                session.add(stock_entry)

                console.print(f"[green]✓ Added {validated_ticker}[/green]")
                console.print(f"  Exchange: {exchange}")
                console.print(f"  Sector: {sector or 'Unknown'}")
                console.print(f"  Country: {country}")

        except Exception as e:
            console.print(f"[red]✗ Failed to add stock: {e}[/red]")

    asyncio.run(fetch_and_add())


@stock.command("add-batch")
@click.option("--tickers", required=True, help="Comma-separated list of tickers")
@click.option("--exchange", default="NASDAQ", help="Stock exchange")
@click.option("--country", default="US", help="Country code")
def add_batch(tickers: str, exchange: str, country: str) -> None:
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

    ticker_list = [t.strip() for t in tickers.split(",")]

    try:
        with db_session() as session:
            added = 0
            skipped = 0

            for ticker in ticker_list:
                # Validate ticker
                try:
                    validated_ticker = validate_ticker(ticker)
                except Exception as e:
                    console.print(f"[red]⏭️  {ticker}: {e}[/red]")
                    skipped += 1
                    continue

                # Check if already exists
                existing = session.query(Stock).filter(Stock.ticker == validated_ticker).first()
                if existing:
                    console.print(f"[yellow]⏭️  {validated_ticker}: Already exists[/yellow]")
                    skipped += 1
                    continue

                # Get metadata if available
                metadata = tech_stocks.get(validated_ticker, {})

                stock_entry = Stock(
                    ticker=validated_ticker,
                    exchange=exchange,
                    name=metadata.get("name", validated_ticker),
                    currency="USD",  # Default currency
                    sector=metadata.get("sector", "Unknown"),
                    country=country,
                    market_cap=metadata.get("market_cap"),
                )

                session.add(stock_entry)
                console.print(
                    f"[green]✓ {validated_ticker}: {metadata.get('name', validated_ticker)} "
                    f"({metadata.get('sector', 'Unknown')})[/green]"
                )
                added += 1

            console.print("\n[bold]Summary:[/bold]")
            console.print(f"  Added: {added}")
            console.print(f"  Skipped: {skipped}")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@stock.command("list")
def list_stocks() -> None:
    """List all stocks in database."""
    try:
        with db_session() as session:
            # Query Securities of type STOCK and left join with Stock details
            securities = (
                session.query(Security)
                .outerjoin(Stock, Security.id == Stock.security_id)
                .filter(Security.security_type == SecurityType.STOCK)
                .order_by(Security.ticker)
                .all()
            )

            if not securities:
                console.print("[yellow]No stocks found[/yellow]")
                return

            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Ticker")
            table.add_column("Name")
            table.add_column("Exchange")
            table.add_column("Sector")
            table.add_column("Industry")
            table.add_column("Country")
            table.add_column("Region")

            for security in securities:
                # Access stock details if available
                stock_details = security.stock
                table.add_row(
                    security.ticker or security.isin or "",
                    security.name or "",
                    stock_details.exchange if stock_details else "",
                    stock_details.sector if stock_details else "",
                    stock_details.industry if stock_details else "",
                    stock_details.country if stock_details else "",
                    stock_details.region if stock_details else "",
                )

            console.print(table)
            console.print(f"\nTotal: {len(securities)} stocks")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@stock.command("remove")
@click.option("--ticker", required=True, help="Stock ticker to remove")
def remove_stock(ticker: str) -> None:
    """Remove a stock from database."""
    try:
        # Validate ticker
        try:
            validated_ticker = validate_ticker(ticker)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return

        with db_session() as session:
            stock = session.query(Stock).filter(Stock.ticker == validated_ticker).first()

            if not stock:
                console.print(f"[yellow]Stock {validated_ticker} not found[/yellow]")
                return

            session.delete(stock)

            console.print(f"[green]✓ Removed {validated_ticker}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@stock.command("update")
@click.option("--ticker", required=True, help="Current security ticker to update")
@click.option("--new-ticker", help="New ticker symbol (to rename the ticker)")
@click.option("--isin", help="ISIN code (e.g., US0378331005)")
@click.option("--name", help="Security name")
@click.option("--currency", help="Trading currency (ISO 4217 code, e.g., EUR, USD)")
@click.option("--price", type=float, help="Current price (creates manual market data entry)")
# Stock-specific options
@click.option("--exchange", help="Exchange (for stocks only, e.g., NASDAQ, NYSE)")
@click.option("--sector", help="Business sector (for stocks only, e.g., Technology)")
@click.option("--industry", help="Industry (for stocks only, e.g., Consumer Electronics)")
@click.option("--country", help="Country (for stocks only, e.g., US, Estonia)")
@click.option("--region", help="Region (for stocks only, e.g., North America, Europe)")
@click.option("--market-cap", type=float, help="Market cap in billions (for stocks only)")
# Bond-specific options
@click.option("--issuer", help="Bond issuer (for bonds only, e.g., BIGBANK)")
@click.option("--coupon-rate", type=float, help="Annual coupon rate % (for bonds only, e.g., 11.0)")
@click.option("--maturity-date", help="Maturity date (for bonds only, format: YYYY-MM-DD)")
@click.option("--face-value", type=float, help="Face value (for bonds only, e.g., 1000)")
@click.option(
    "--payment-frequency", help="Coupon payment frequency (for bonds only, e.g., quarterly)"
)
def update_security(
    ticker: str,
    new_ticker: str | None,
    isin: str | None,
    name: str | None,
    currency: str | None,
    price: float | None,
    exchange: str | None,
    sector: str | None,
    industry: str | None,
    country: str | None,
    region: str | None,
    market_cap: float | None,
    issuer: str | None,
    coupon_rate: float | None,
    maturity_date: str | None,
    face_value: float | None,
    payment_frequency: str | None,
) -> None:
    """Update security data manually.

    Use this command to fill in data for securities that cannot be fetched via API
    (e.g., bonds, delisted stocks, funds).

    Examples:
        # Update bond with all fields
        stocks-helper stock update --ticker BIG25-2035/1 \\
            --name "BigBank Bond 2035 Series 1" --currency EUR --price 1000.00 \\
            --issuer "BIGBANK AS" --coupon-rate 5.5 --maturity-date 2035-12-31 \\
            --face-value 1000 --payment-frequency quarterly

        # Update stock with all fields
        stocks-helper stock update --ticker AAPL \\
            --name "Apple Inc." --currency USD --price 175.50 \\
            --exchange NASDAQ --sector Technology --industry "Consumer Electronics" \\
            --country US --region "North America" --market-cap 2800

        # Update security fields only (ISIN, name, currency)
        stocks-helper stock update --ticker LHV1T \\
            --isin EE3100098328 --name "LHV Group" --currency EUR

        # Set current price only
        stocks-helper stock update --ticker IUTECR061026 --price 950.50

        # Rename ticker
        stocks-helper stock update --ticker OLD_TICKER --new-ticker NEW_TICKER
    """
    try:
        normalized_ticker = ticker.upper().strip()

        with db_session() as session:
            security = session.query(Security).filter(Security.ticker == normalized_ticker).first()

            if not security:
                console.print(f"[yellow]Security {normalized_ticker} not found[/yellow]")
                return

            updated_fields = []

            # Update Security fields
            if isin:
                security.isin = isin.upper().strip()
                updated_fields.append(f"isin={security.isin}")

            if name:
                security.name = name
                updated_fields.append(f"name={name}")

            if currency:
                security.currency = currency.upper()
                updated_fields.append(f"currency={security.currency}")

            if new_ticker:
                new_normalized = new_ticker.upper().strip()
                # Check if new ticker already exists
                existing = session.query(Security).filter(Security.ticker == new_normalized).first()
                if existing and existing.id != security.id:
                    console.print(f"[red]Error: Ticker {new_normalized} already exists[/red]")
                    return
                old_ticker = security.ticker
                security.ticker = new_normalized
                updated_fields.append(f"ticker={old_ticker} -> {new_normalized}")

            # Update Stock fields (only for stocks)
            if security.security_type == SecurityType.STOCK:
                stock = security.stock
                if not stock:
                    # Create Stock entry if doesn't exist
                    stock = Stock(
                        security_id=security.id,
                        exchange=exchange or "UNKNOWN",
                        sector=sector,
                        industry=industry,
                        country=country,
                        region=region,
                    )
                    session.add(stock)
                    updated_fields.append("created stock details")
                else:
                    # Update existing Stock
                    if exchange:
                        stock.exchange = exchange
                        updated_fields.append(f"exchange={exchange}")
                    if sector:
                        stock.sector = sector
                        updated_fields.append(f"sector={sector}")
                    if industry:
                        stock.industry = industry
                        updated_fields.append(f"industry={industry}")
                    if country:
                        stock.country = country
                        updated_fields.append(f"country={country}")
                    if region:
                        stock.region = region
                        updated_fields.append(f"region={region}")
                    if market_cap is not None:
                        stock.market_cap = Decimal(str(market_cap))
                        updated_fields.append(f"market_cap={market_cap}B")

            # Update Bond fields (only for bonds)
            if security.security_type == SecurityType.BOND:
                bond = security.bond
                if not bond:
                    # Create Bond entry if doesn't exist
                    bond = Bond(
                        security_id=security.id,
                        issuer=issuer,
                        coupon_rate=Decimal(str(coupon_rate)) if coupon_rate is not None else None,
                        maturity_date=(
                            datetime.strptime(maturity_date, "%Y-%m-%d").date()
                            if maturity_date
                            else None
                        ),
                        face_value=Decimal(str(face_value)) if face_value is not None else None,
                        payment_frequency=payment_frequency,
                    )
                    session.add(bond)
                    updated_fields.append("created bond details")
                else:
                    # Update existing Bond
                    if issuer:
                        bond.issuer = issuer
                        updated_fields.append(f"issuer={issuer}")
                    if coupon_rate is not None:
                        bond.coupon_rate = Decimal(str(coupon_rate))
                        updated_fields.append(f"coupon_rate={coupon_rate}%")
                    if maturity_date:
                        bond.maturity_date = datetime.strptime(maturity_date, "%Y-%m-%d").date()
                        updated_fields.append(f"maturity_date={maturity_date}")
                    if face_value is not None:
                        bond.face_value = Decimal(str(face_value))
                        updated_fields.append(f"face_value={face_value}")
                    if payment_frequency:
                        bond.payment_frequency = payment_frequency
                        updated_fields.append(f"payment_frequency={payment_frequency}")

            # Update price (create MarketData entry)
            if price is not None:
                if price <= 0:
                    console.print("[red]Error: Price must be positive[/red]")
                    return

                # Clear existing is_latest flags
                session.query(MarketData).filter(
                    MarketData.security_id == security.id, MarketData.is_latest
                ).update({"is_latest": False})

                # Create new market data entry
                market_data = MarketData(
                    security_id=security.id,
                    timestamp=datetime.now(timezone.utc),
                    price=Decimal(str(price)),
                    volume=None,
                    data_source="manual",
                    is_latest=True,
                )
                session.add(market_data)
                updated_fields.append(f"price={price}")

            if not updated_fields:
                console.print("[yellow]No fields to update. Provide at least one option.[/yellow]")
                return

            session.commit()

            console.print(f"[green]✓ Updated {normalized_ticker}[/green]")
            for field in updated_fields:
                console.print(f"  [dim]{field}[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@stock.command("archive")
@click.option("--ticker", required=True, help="Stock ticker to archive/unarchive")
@click.option("--unarchive", is_flag=True, help="Unarchive instead of archive")
def archive_stock(ticker: str, unarchive: bool) -> None:
    """Mark a security as archived (delisted/matured) or unarchive it.

    Archived securities:
    - Are excluded from Yahoo Finance price queries
    - Show $0.00 current value in holdings
    - Show -100% loss in holdings

    Examples:
        stocks-helper stock archive --ticker MAGIC
        stocks-helper stock archive --ticker MAGIC --unarchive
    """
    try:
        # Normalize ticker (no validation - accept any existing ticker)
        normalized_ticker = ticker.upper().strip()

        with db_session() as session:
            security = session.query(Security).filter(Security.ticker == normalized_ticker).first()

            if not security:
                console.print(f"[yellow]Security {normalized_ticker} not found[/yellow]")
                return

            # Toggle archived status
            security.archived = not unarchive

            action = "unarchived" if unarchive else "archived"
            console.print(f"[green]✓ {normalized_ticker} has been {action}[/green]")

            if not unarchive:
                console.print("  [dim]This security will no longer be queried for prices[/dim]")
                console.print("  [dim]Current value will show as $0.00 in holdings[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    stock()
