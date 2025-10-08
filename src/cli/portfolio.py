"""Portfolio subcommands."""

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import SQLAlchemyError

from src.lib.db import db_session
from src.models import Account, Holding, Portfolio
from src.services.currency_converter import CurrencyConverter
from src.services.market_data_fetcher import MarketDataFetcher

console = Console()


@click.group()
def portfolio() -> None:
    """Manage investment portfolios."""
    pass


@portfolio.command()
@click.option("--name", required=True, help="Portfolio name")
@click.option("--currency", required=True, help="Base currency (USD, EUR, etc.)")
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


@portfolio.command()
def list_portfolios() -> None:
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


@portfolio.command()
@click.argument("portfolio_id", required=False)
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


@portfolio.command("overview")
@click.argument("portfolio_id", required=False)
def overview(portfolio_id: str | None) -> None:
    """Show comprehensive portfolio overview with gains breakdown."""
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

            from decimal import Decimal

            from sqlalchemy.orm import joinedload

            from src.models import SecurityType, Transaction, TransactionType

            # Get all holdings with security relationship
            holdings = (
                session.query(Holding)
                .options(joinedload(Holding.security))
                .filter(Holding.portfolio_id == portfolio_obj.id)
                .all()
            )

            # Initialize market data fetcher and currency converter
            market_data_fetcher = MarketDataFetcher()
            currency_converter = CurrencyConverter()
            base_currency = portfolio_obj.base_currency

            # Bulk fetch all prices (for holdings)
            all_tickers = [h.ticker for h in holdings] if holdings else []
            current_prices = (
                market_data_fetcher.get_current_prices(all_tickers) if all_tickers else {}
            )

            # Calculate metrics for each holding
            holdings_data = []
            total_portfolio_value = Decimal("0")
            total_capital_gain = Decimal("0")
            total_fees = Decimal("0")
            total_income = Decimal("0")
            total_currency_gain = Decimal("0")

            for holding in holdings:
                security = holding.security

                # Get current exchange rate
                current_exchange_rate = Decimal("1.0")
                if security.currency != base_currency:
                    rate = asyncio.run(
                        currency_converter.get_rate(security.currency, base_currency, date.today())
                    )
                    if rate:
                        current_exchange_rate = Decimal(str(rate))

                # Get all transactions for this holding
                transactions = (
                    session.query(Transaction).filter(Transaction.holding_id == holding.id).all()
                )

                # === TOTAL VALUE APPROACH FOR ACCURATE GAIN CALCULATION ===
                # Calculate total costs from BUY transactions
                # and total proceeds from SELL transactions
                total_buy_cost_in_base = Decimal("0")
                total_buy_cost_in_local = Decimal("0")
                total_buy_cost_at_stored_rates = Decimal("0")  # Using stored (possibly wrong) rates
                total_sell_proceeds_in_base = Decimal("0")
                total_sell_proceeds_in_local = Decimal("0")
                total_sell_proceeds_at_stored_rates = Decimal("0")

                # Identify automatic reinvestments
                # (distributions/interest immediately reinvested)
                # These should not be counted in cost basis - part of capital gain
                reinvested_buy_ids = set()
                income_txns = [
                    t
                    for t in transactions
                    if t.type in [TransactionType.DISTRIBUTION, TransactionType.INTEREST]
                ]
                buy_txns = [t for t in transactions if t.type == TransactionType.BUY]

                # Check if this is a money market fund with automatic reinvestment
                is_money_market_fund = security.security_type == SecurityType.FUND and any(
                    t.type in [TransactionType.DISTRIBUTION, TransactionType.INTEREST]
                    for t in income_txns
                )

                for income_txn in income_txns:
                    # Find matching BUY on same date with same amount (within 1 day, 0.01 tolerance)
                    for buy_txn in buy_txns:
                        if abs((buy_txn.date - income_txn.date).days) <= 1 and abs(
                            buy_txn.amount - income_txn.amount
                        ) < Decimal("0.01"):
                            reinvested_buy_ids.add(buy_txn.id)
                            break

                for txn in transactions:
                    stored_rate = txn.exchange_rate

                    # Get correct exchange rate for accurate calculations
                    # Use historical rate at transaction date, not current rate
                    correct_rate = txn.exchange_rate
                    if security.currency != base_currency and correct_rate == Decimal("1.0"):
                        rate = asyncio.run(
                            currency_converter.get_rate(security.currency, base_currency, txn.date)
                        )
                        correct_rate = Decimal(str(rate)) if rate else current_exchange_rate

                    if txn.type == TransactionType.BUY:
                        # Skip reinvested distributions - they're not part of cost basis
                        if txn.id in reinvested_buy_ids:
                            continue

                        # Skip if quantity or price is missing
                        if txn.quantity and txn.price:
                            cost_local = txn.quantity * txn.price
                            cost_in_base = cost_local * correct_rate
                            cost_at_stored_rate = cost_local * stored_rate
                            total_buy_cost_in_base += cost_in_base
                            total_buy_cost_in_local += cost_local
                            total_buy_cost_at_stored_rates += cost_at_stored_rate

                    elif txn.type == TransactionType.SELL:
                        # Skip if quantity or price is missing
                        if txn.quantity and txn.price:
                            proceeds_local = txn.quantity * txn.price
                            proceeds_in_base = proceeds_local * correct_rate
                            proceeds_at_stored_rate = proceeds_local * stored_rate
                            total_sell_proceeds_in_base += proceeds_in_base
                            total_sell_proceeds_in_local += proceeds_local
                            total_sell_proceeds_at_stored_rates += proceeds_at_stored_rate

                # Current holdings value in security currency
                current_price = current_prices.get(holding.ticker)
                if current_price is not None:
                    current_value_local = holding.quantity * Decimal(str(current_price))
                elif security.archived:
                    current_value_local = Decimal("0")
                    current_price = Decimal("0")  # type: ignore[assignment]
                elif security.security_type in (SecurityType.BOND, SecurityType.FUND):
                    current_value_local = holding.quantity * holding.avg_purchase_price
                    current_price = holding.avg_purchase_price  # type: ignore[assignment]
                else:
                    current_value_local = holding.quantity * holding.avg_purchase_price
                    current_price = holding.avg_purchase_price  # type: ignore[assignment]

                # Current value at current exchange rate
                current_value_at_current_rate = current_value_local * current_exchange_rate

                # === CAPITAL GAIN (price effect) ===
                # Capital gain: price changes in local currency, converted at current rate
                # For money market funds with stable $1 value: capital gain should be 0
                # (distributions are shown as income instead)
                if is_money_market_fund:
                    capital_gain = Decimal("0")
                else:
                    # For stocks/ETFs: calculate price-based capital gain
                    total_value_in_local = current_value_local + total_sell_proceeds_in_local
                    capital_gain_in_local = total_value_in_local - total_buy_cost_in_local
                    capital_gain = capital_gain_in_local * current_exchange_rate

                # === CURRENCY GAIN (exchange rate effect) ===
                # Currency gain: effect of exchange rate changes on COST BASIS
                # Includes both:
                # - Unrealized: on shares still held (current_rate - purchase_rate)
                # - Realized: on shares sold and proceeds converted
                #   (conversion_rate - purchase_rate)
                # Uses precise currency lot tracking - each purchase allocated to
                # specific conversion lots using FIFO for accurate per-purchase rates

                if security.currency != base_currency:
                    # Use currency lot service for precise lot-based calculation
                    from src.models.stock_split import StockSplit
                    from src.services.currency_lot_service import CurrencyLotService

                    lot_service = CurrencyLotService(session)
                    weighted_avg_rate = lot_service.get_weighted_average_rate_for_holding(
                        holding.id, base_currency
                    )

                    if weighted_avg_rate:
                        # Get stock splits for split adjustment
                        splits = (
                            session.query(StockSplit)
                            .filter(StockSplit.security_id == holding.security_id)
                            .order_by(StockSplit.split_date)
                            .all()
                        )

                        # Calculate cost basis with split adjustments
                        all_buy_cost_local = Decimal("0")
                        total_qty_bought = Decimal("0")

                        for txn in transactions:
                            if txn.type == TransactionType.BUY:
                                quantity = txn.quantity or Decimal("0")
                                price = txn.price or Decimal("0")

                                # Apply split adjustments
                                for split in splits:
                                    should_apply = (
                                        txn.broker_source == "swedbank"
                                        or txn.date < split.split_date
                                    )
                                    if should_apply:
                                        quantity = quantity * split.split_ratio
                                        price = price / split.split_ratio

                                all_buy_cost_local += quantity * price
                                total_qty_bought += quantity

                        # Unrealized currency gain on remaining shares
                        unrealized_gain = Decimal("0")
                        if total_qty_bought > 0 and holding.quantity > 0:
                            avg_cost_per_share = all_buy_cost_local / total_qty_bought
                            remaining_cost_basis = holding.quantity * avg_cost_per_share

                            # Unrealized currency gain =
                            #   cost basis * (current_rate - lot_weighted_avg_rate)
                            # weighted_avg_rate calculated from SPECIFIC lots
                            # that funded purchases
                            unrealized_gain = remaining_cost_basis * (
                                current_exchange_rate - weighted_avg_rate
                            )

                        # Realized currency gain from sold shares
                        realized_gain = lot_service.get_realized_currency_gain_for_holding(
                            holding.id, base_currency
                        )

                        currency_gain = unrealized_gain + realized_gain
                    else:
                        # No lot allocations found - fall back to exchange rates from transactions
                        from src.models.stock_split import StockSplit

                        # Get stock splits for split adjustment
                        splits = (
                            session.query(StockSplit)
                            .filter(StockSplit.security_id == holding.security_id)
                            .order_by(StockSplit.split_date)
                            .all()
                        )

                        all_buy_cost_local = Decimal("0")
                        all_buy_cost_at_stored = Decimal("0")
                        total_qty_bought = Decimal("0")

                        for txn in transactions:
                            if txn.type == TransactionType.BUY:
                                quantity = txn.quantity or Decimal("0")
                                price = txn.price or Decimal("0")

                                # Apply split adjustments
                                for split in splits:
                                    should_apply = (
                                        txn.broker_source == "swedbank"
                                        or txn.date < split.split_date
                                    )
                                    if should_apply:
                                        quantity = quantity * split.split_ratio
                                        price = price / split.split_ratio

                                cost_local = quantity * price
                                all_buy_cost_local += cost_local
                                all_buy_cost_at_stored += cost_local * txn.exchange_rate
                                total_qty_bought += quantity

                        if all_buy_cost_local > 0:
                            weighted_avg_rate = all_buy_cost_at_stored / all_buy_cost_local
                            avg_cost_per_share = all_buy_cost_local / total_qty_bought
                            remaining_cost_basis = holding.quantity * avg_cost_per_share
                            currency_gain = remaining_cost_basis * (
                                current_exchange_rate - weighted_avg_rate
                            )
                        else:
                            currency_gain = Decimal("0")
                else:
                    currency_gain = Decimal("0")

                # Calculate fees (sum of all transaction fees in base currency)
                fees = Decimal("0")
                for txn in transactions:
                    if txn.fees > 0:
                        # Get correct exchange rate
                        txn_rate = txn.exchange_rate
                        if security.currency != base_currency and txn_rate == Decimal("1.0"):
                            rate = asyncio.run(
                                currency_converter.get_rate(
                                    security.currency, base_currency, txn.date
                                )
                            )
                            txn_rate = Decimal(str(rate)) if rate else current_exchange_rate

                        fee_in_base = txn.fees * txn_rate
                        fees += fee_in_base

                # Calculate income
                # (sum of dividends, distributions, interest in base currency)
                # Money market funds: show total distributions at current rate
                # Stocks: only count dividends that hit cash (not reinvested)
                income = Decimal("0")

                if is_money_market_fund:
                    # Money market funds: total distributions/interest at current rate
                    # (Lightyear approach)
                    total_distributions_local = sum(t.amount for t in income_txns)
                    income = total_distributions_local * current_exchange_rate
                else:
                    # For stocks: only count dividends not reinvested
                    # Build set of reinvested income transaction IDs
                    reinvested_income_ids = set()
                    for income_txn in income_txns:
                        for buy_txn in buy_txns:
                            if abs((buy_txn.date - income_txn.date).days) <= 1 and abs(
                                buy_txn.amount - income_txn.amount
                            ) < Decimal("0.01"):
                                reinvested_income_ids.add(income_txn.id)
                                break

                    for txn in transactions:
                        if txn.type in [
                            TransactionType.DIVIDEND,
                            TransactionType.DISTRIBUTION,
                            TransactionType.INTEREST,
                        ]:
                            # Skip reinvested income - it's already in capital gain
                            if txn.id in reinvested_income_ids:
                                continue

                            # Get correct exchange rate
                            txn_rate = txn.exchange_rate
                            if security.currency != base_currency and txn_rate == Decimal("1.0"):
                                rate = asyncio.run(
                                    currency_converter.get_rate(
                                        security.currency, base_currency, txn.date
                                    )
                                )
                                txn_rate = Decimal(str(rate)) if rate else current_exchange_rate

                            div_in_base = txn.amount * txn_rate
                            income += div_in_base

                # Total gain for this holding
                total_gain = capital_gain + income - fees + currency_gain

                holdings_data.append(
                    {
                        "ticker": holding.ticker,
                        "name": security.name,
                        "security_type": security.security_type,
                        "archived": security.archived,
                        "quantity": holding.quantity,
                        "current_price": current_price,
                        "market_value": current_value_at_current_rate,
                        "capital_gain": capital_gain,
                        "fees": fees,
                        "income": income,
                        "currency_gain": currency_gain,
                        "total_gain": total_gain,
                    }
                )

                # Add to portfolio totals
                total_portfolio_value += current_value_at_current_rate
                total_capital_gain += capital_gain
                total_fees += fees
                total_income += income
                total_currency_gain += currency_gain

            # Get cash accounts
            accounts = session.query(Account).filter(Account.portfolio_id == portfolio_obj.id).all()

            # Calculate cash balances by account
            cash_data = []
            total_cash_value = Decimal("0")

            for account in accounts:
                # Calculate balance from transactions
                transactions = (
                    session.query(Transaction).filter(Transaction.account_id == account.id).all()
                )

                # Group balances by currency (credits - debits)
                balances_by_currency = {}
                for txn in transactions:
                    currency = txn.currency
                    if currency not in balances_by_currency:
                        balances_by_currency[currency] = Decimal("0")

                    if txn.debit_credit == "K":  # Credit (money in)
                        balances_by_currency[currency] += txn.amount
                    else:  # Debit (money out)
                        balances_by_currency[currency] -= txn.amount

                # Create cash entry for each currency with non-zero balance
                for currency, balance in balances_by_currency.items():
                    if balance != 0:  # Only show non-zero balances
                        # Convert to base currency
                        if currency != base_currency:
                            rate = asyncio.run(
                                currency_converter.get_rate(currency, base_currency, date.today())
                            )
                            balance_in_base = balance * Decimal(str(rate)) if rate else balance
                        else:
                            balance_in_base = balance

                        cash_data.append(
                            {
                                "name": account.account_number or account.name,
                                "currency": currency,
                                "balance": balance,
                                "balance_in_base": balance_in_base,
                            }
                        )
                        total_cash_value += balance_in_base

            # Add cash to total portfolio value
            total_portfolio_value_with_cash = total_portfolio_value + total_cash_value

            # Calculate total gain
            total_gain = total_capital_gain + total_income - total_fees + total_currency_gain

            # Calculate cost basis for portfolio
            total_cost_basis = total_portfolio_value_with_cash - total_gain

            # Calculate percentages for summary
            capital_gain_pct = (
                (total_capital_gain / total_cost_basis * 100)
                if total_cost_basis > 0
                else Decimal("0")
            )
            fees_pct = (
                (total_fees / total_cost_basis * 100) if total_cost_basis > 0 else Decimal("0")
            )
            income_pct = (
                (total_income / total_cost_basis * 100) if total_cost_basis > 0 else Decimal("0")
            )
            currency_gain_pct = (
                (total_currency_gain / total_cost_basis * 100)
                if total_cost_basis > 0
                else Decimal("0")
            )
            total_gain_pct = (
                (total_gain / total_cost_basis * 100) if total_cost_basis > 0 else Decimal("0")
            )

            # Display summary metrics
            currency_symbol = _get_currency_symbol(base_currency)

            console.print(
                f"\n[bold cyan]{total_portfolio_value_with_cash:,.2f} {base_currency}[/bold cyan]"
            )
            console.print("Portfolio value\n")

            # Summary table
            summary_table = Table(show_header=False, box=None, padding=(0, 2))
            summary_table.add_column(justify="left")
            summary_table.add_column(justify="right")
            summary_table.add_column(justify="right")

            def format_gain(
                amount: Decimal, pct: Decimal, sign_prefix: bool = True
            ) -> tuple[str, str]:
                color = "green" if amount >= 0 else "red"
                sign = "+" if amount >= 0 and sign_prefix else ""
                amount_str = f"[{color}]{sign}{amount:,.2f} {base_currency}[/{color}]"
                pct_str = f"[{color}]{sign}{pct:.2f}%[/{color}]"
                return amount_str, pct_str

            cap_amt, cap_pct = format_gain(total_capital_gain, capital_gain_pct)
            fees_amt, fees_pct = format_gain(-total_fees, -fees_pct)  # type: ignore[assignment]
            inc_amt, inc_pct = format_gain(total_income, income_pct)
            curr_amt, curr_pct = format_gain(total_currency_gain, currency_gain_pct)
            tot_amt, tot_pct = format_gain(total_gain, total_gain_pct)

            summary_table.add_row("Capital gain", cap_amt, cap_pct)
            summary_table.add_row("Fees contribution", fees_amt, fees_pct)
            summary_table.add_row("Income gain", inc_amt, inc_pct)
            summary_table.add_row("Currency gain", curr_amt, curr_pct)
            summary_table.add_row("Total gain", tot_amt, tot_pct)

            console.print(summary_table)
            console.print()

            # Group holdings by security type
            equity_holdings = [
                h
                for h in holdings_data
                if h["security_type"] in (SecurityType.STOCK, SecurityType.ETF)
            ]
            bond_holdings = [h for h in holdings_data if h["security_type"] == SecurityType.BOND]
            fund_holdings = [h for h in holdings_data if h["security_type"] == SecurityType.FUND]

            # Holdings table
            holdings_table = Table(title="Portfolio holdings")
            holdings_table.add_column("Ticker", style="cyan", no_wrap=True)
            holdings_table.add_column("Name", style="white", overflow="ellipsis")
            holdings_table.add_column("Price", justify="right", style="white")
            holdings_table.add_column("Quantity", justify="right", style="yellow")
            holdings_table.add_column("Market value", justify="right", style="white")
            holdings_table.add_column("%", justify="right", style="white")
            holdings_table.add_column("CAPITAL", justify="right", style="white")
            holdings_table.add_column("FEES", justify="right", style="white")
            holdings_table.add_column("INCOME", justify="right", style="white")
            holdings_table.add_column("CURRENCY", justify="right", style="white")
            holdings_table.add_column("TOTAL", justify="right", style="white")

            def format_cell(value: Decimal) -> str:
                if value >= 0:
                    return f"[green]{value:,.2f}[/green]"
                else:
                    return f"[red]{value:,.2f}[/red]"

            def add_holdings_to_table(
                holdings_list: list[Any], section_title: str | None = None
            ) -> None:
                if section_title:
                    holdings_table.add_row(
                        f"[bold]{section_title}[/bold]",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        style="dim",
                    )

                for h in holdings_list:
                    pct = (
                        (h["market_value"] / total_portfolio_value_with_cash * 100)
                        if total_portfolio_value_with_cash > 0
                        else Decimal("0")
                    )

                    holdings_table.add_row(
                        h["ticker"],
                        h["name"][:20],  # Truncate long names
                        f"{h['current_price']:,.2f}",
                        f"{h['quantity']:,.2f}",
                        f"{h['market_value']:,.2f}",
                        f"{pct:.2f}%",
                        format_cell(h["capital_gain"]),
                        format_cell(-h["fees"]),
                        format_cell(h["income"]),
                        format_cell(h["currency_gain"]),
                        format_cell(h["total_gain"]),
                    )

            # Add sections
            if equity_holdings:
                add_holdings_to_table(equity_holdings, "Equity")

            if fund_holdings:
                add_holdings_to_table(fund_holdings, "Funds")

            # Add cash section
            holdings_table.add_row(
                "[bold]Cash[/bold]", "", "", "", "", "", "", "", "", "", "", style="dim"
            )

            # Group cash by currency
            cash_by_currency = {}
            for cash in cash_data:
                curr = cash["currency"]
                if curr not in cash_by_currency:
                    cash_by_currency[curr] = {"balance_in_base": Decimal("0"), "accounts": []}
                cash_by_currency[curr]["balance_in_base"] += cash["balance_in_base"]  # type: ignore[operator]
                cash_by_currency[curr]["accounts"].append(  # type: ignore[attr-defined]
                    {"name": cash["name"], "balance": cash["balance"]}
                )

            # Add currency subtotals
            for curr, data in sorted(cash_by_currency.items()):
                pct = (
                    (data["balance_in_base"] / total_portfolio_value_with_cash * 100)  # type: ignore[operator]
                    if total_portfolio_value_with_cash > 0
                    else Decimal("0")
                )
                holdings_table.add_row(
                    f"  {curr}",
                    "",
                    "",
                    "",
                    f"{data['balance_in_base']:,.2f}",
                    f"{pct:.2f}%",
                    "0.00",
                    "0.00",
                    "0.00",
                    "0.00",
                    "0.00",
                )

                # Add individual accounts under currency
                for account in data["accounts"]:  # type: ignore[attr-defined]
                    holdings_table.add_row(
                        f"    {account['name']}",
                        "",
                        f"{account['balance']:,.2f} {curr}",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        style="dim",
                    )

            if bond_holdings:
                add_holdings_to_table(bond_holdings, "Fixed income")

            # Add totals row
            if holdings_data or cash_data:
                holdings_table.add_row(
                    "[bold]Portfolio totals[/bold]",
                    "",
                    "",
                    "",
                    "",
                    "",
                    format_cell(total_capital_gain),
                    format_cell(-total_fees),
                    format_cell(total_income),
                    format_cell(total_currency_gain),
                    format_cell(total_gain),
                    style="bold",
                )

            console.print(holdings_table)

            # Grand total
            console.print("\n[bold]Grand total[/bold]")
            console.print(
                f"Portfolio value: {currency_symbol}{total_portfolio_value_with_cash:,.2f}"
            )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback

        traceback.print_exc()


@portfolio.command("set-currency")
@click.argument("portfolio_id")
@click.option("--currency", required=True, help="New base currency (USD, EUR, etc.)")
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
