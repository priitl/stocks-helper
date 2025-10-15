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


def _get_gains_from_accounting(session: Any, portfolio_id: str) -> dict[str, Decimal]:
    """Extract gains breakdown from accounting journal entries.

    Reads from chart of accounts to get the current state of gains/losses.
    This matches the balance sheet and income statement exactly.

    Args:
        session: Database session
        portfolio_id: Portfolio ID

    Returns:
        Dictionary with gain components: capital_gain, income, fees, taxes,
        currency_gain, total_gain
    """
    from src.models import ChartAccount
    from src.services.accounting_service import get_account_balance

    # Get chart of accounts for this portfolio
    accounts = session.query(ChartAccount).filter(ChartAccount.portfolio_id == portfolio_id).all()

    # Map account names to balances
    account_balances = {}
    for account in accounts:
        balance = get_account_balance(session, account.id, date.today())
        account_balances[account.name] = balance

    # Calculate gain components from account balances
    # Revenue accounts (credits) have positive balances that represent income
    # Expense accounts (debits) have positive balances that represent expenses (need to negate)

    # Capital gain = Realized + Unrealized (both gains and losses)
    realized_capital_gains = account_balances.get("Realized Capital Gains", Decimal("0"))
    realized_capital_losses = account_balances.get("Realized Capital Losses", Decimal("0"))
    unrealized_investment_gl = account_balances.get(
        "Unrealized Gain/Loss on Investments", Decimal("0")
    )

    capital_gain = realized_capital_gains - realized_capital_losses + unrealized_investment_gl

    # Income = Dividends + Interest
    dividend_income = account_balances.get("Dividend Income", Decimal("0"))
    interest_income = account_balances.get("Interest Income", Decimal("0"))
    income = dividend_income + interest_income

    # Fees (expense account - debit balance, so negate to show as negative)
    fees = account_balances.get("Fees and Commissions", Decimal("0"))

    # Taxes (expense account - debit balance, so negate to show as negative)
    taxes = account_balances.get("Tax Expense", Decimal("0"))

    # Currency gain = Realized + Unrealized (both gains and losses)
    realized_currency_gains = account_balances.get("Realized Currency Gains", Decimal("0"))
    realized_currency_losses = account_balances.get("Realized Currency Losses", Decimal("0"))
    unrealized_currency_gl = account_balances.get("Unrealized Currency Gain/Loss", Decimal("0"))

    currency_gain = realized_currency_gains - realized_currency_losses + unrealized_currency_gl

    # Total gain = capital + income - fees - taxes + currency
    total_gain = capital_gain + income - fees - taxes + currency_gain

    return {
        "capital_gain": capital_gain,
        "income": income,
        "fees": fees,
        "taxes": -taxes,  # Negate to show as negative expense
        "currency_gain": currency_gain,
        "total_gain": total_gain,
    }


@portfolio.command("overview")
@click.argument("portfolio_id", required=False)
@click.option(
    "--use-accounting/--use-transactions",
    default=False,
    help="Use accounting journal entries or calculate from transactions (default)",
)
def overview(portfolio_id: str | None, use_accounting: bool = False) -> None:
    """Show comprehensive portfolio overview with gains breakdown.

    By default, calculates from raw transactions (per-holding detail).
    Use --use-accounting to read from accounting journal entries (matches balance sheet exactly).
    """
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
            holding_fees = Decimal("0")  # Track fees from holdings separately for breakdown
            total_income = Decimal("0")
            total_currency_gain = Decimal("0")
            total_taxes = Decimal("0")  # Track withholding and other taxes

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

                # Get all transactions for this holding (with eager loading to prevent N+1)
                transactions = (
                    session.query(Transaction)
                    .options(joinedload(Transaction.holding))
                    .filter(Transaction.holding_id == holding.id)
                    .all()
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

                # Check if this is a money market fund (for capital gain calculation logic)
                income_txns = [
                    t
                    for t in transactions
                    if t.type in [TransactionType.DISTRIBUTION, TransactionType.INTEREST]
                ]
                is_money_market_fund = security.security_type == SecurityType.FUND and any(
                    t.type in [TransactionType.DISTRIBUTION, TransactionType.INTEREST]
                    for t in income_txns
                )

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
                        # GAAP: ALL purchases increase cost basis, including
                        # reinvested distributions. Reinvestment is a separate purchase
                        # transaction from receiving the distribution

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

                # If no Yahoo Finance price, check MarketData table (for bonds/funds)
                if current_price is None:
                    from src.models import MarketData

                    manual_price_record = (
                        session.query(MarketData)
                        .filter(
                            MarketData.security_id == security.id,
                            MarketData.is_latest == True,  # noqa: E712
                        )
                        .order_by(MarketData.timestamp.desc())
                        .first()
                    )

                    if manual_price_record:
                        current_price = float(manual_price_record.price)

                # Calculate current value
                if current_price is not None:
                    current_value_local = holding.quantity * Decimal(str(current_price))
                elif security.archived:
                    current_value_local = Decimal("0")
                    current_price = Decimal("0")  # type: ignore[assignment]
                else:
                    # Fallback to cost basis if no market price available
                    current_value_local = holding.quantity * holding.avg_purchase_price
                    current_price = holding.avg_purchase_price  # type: ignore[assignment]

                # Current value at current exchange rate
                current_value_at_current_rate = current_value_local * current_exchange_rate

                if security.currency != base_currency:
                    # Calculate weighted average rate from actual purchase transactions
                    # This separates price effects (capital) from FX effects (currency)
                    from src.models.stock_split import StockSplit

                    splits = (
                        session.query(StockSplit)
                        .filter(StockSplit.security_id == holding.security_id)
                        .order_by(StockSplit.split_date)
                        .all()
                    )

                    all_buy_cost_local = Decimal("0")
                    all_buy_cost_at_stored = Decimal("0")

                    for txn in transactions:
                        if txn.type == TransactionType.BUY:
                            # GAAP: ALL purchases increase cost basis
                            quantity = txn.quantity or Decimal("0")
                            price = txn.price or Decimal("0")

                            # Apply split adjustments
                            for split in splits:
                                should_apply = (
                                    txn.broker_source == "swedbank" or txn.date < split.split_date
                                )
                                if should_apply:
                                    quantity = quantity * split.split_ratio
                                    price = price / split.split_ratio

                            cost_local = quantity * price
                            all_buy_cost_local += cost_local
                            all_buy_cost_at_stored += cost_local * txn.exchange_rate

                # === CAPITAL GAIN (price effect) ===
                # Per IFRS 9 & IAS 21: Capital gain = price changes in local currency,
                # converted at CURRENT RATE to get the gain in reporting currency
                # Currency gain separately captures FX effects on cost basis
                if is_money_market_fund:
                    capital_gain = Decimal("0")
                else:
                    # Calculate price-based capital gain in local currency
                    total_value_in_local = current_value_local + total_sell_proceeds_in_local
                    capital_gain_in_local = total_value_in_local - total_buy_cost_in_local
                    # Convert at current rate to get capital gain in reporting currency
                    capital_gain = capital_gain_in_local * current_exchange_rate

                # === CURRENCY GAIN (exchange rate effect) ===
                # Currency gain: effect of exchange rate changes on COST BASIS ONLY
                # Per IAS 21: FX gain/loss on monetary items (the cost of the investment)
                # Includes both:
                # - Unrealized: on shares still held - FX effect on cost basis
                #   = cost_basis * (current_rate - purchase_rate)
                # - Realized: on shares sold and proceeds converted
                #   (conversion_rate - purchase_rate)
                # This ensures Capital + Currency = Total. Uses precise currency lot tracking.

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
                            # Per IAS 21: FX effect applies to cost basis (what we paid),
                            # while capital gain captures price changes at current rate
                            # weighted_avg_rate calculated from SPECIFIC lots that funded purchases
                            unrealized_gain = remaining_cost_basis * (
                                current_exchange_rate - weighted_avg_rate
                            )

                        # Realized currency gain from sold shares
                        # For money market funds: skip realized gain calc due to $1 stable NAV
                        # Selling at $1 and buying back at $1 creates no currency effect
                        # Only unrealized gain on remaining balance matters
                        if is_money_market_fund:
                            realized_gain = Decimal("0")
                        else:
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
                            # Per IAS 21: FX effect applies to cost basis only
                            currency_gain = remaining_cost_basis * (
                                current_exchange_rate - weighted_avg_rate
                            )
                        else:
                            currency_gain = Decimal("0")
                else:
                    currency_gain = Decimal("0")

                # Calculate fees (sum of all journalized transaction fees in base
                # currency)
                # - FEE transactions: fee in 'amount' field
                # - DIVIDEND/INTEREST/DISTRIBUTION/REWARD/DEPOSIT/WITHDRAWAL: fee in
                #   'fees' field (fee already deducted from amount)
                # - CONVERSION: DO NOT count 'fees' field (separate FEE transactions
                #   exist - would double-count)
                # - BUY/SELL: fees capitalized into cost basis, not expensed
                fees = Decimal("0")
                for txn in transactions:
                    # IMPORTANT: Match accounting_service.py create_journal_line() logic exactly:
                    # - If currency == base_currency: use rate=1.0 (no conversion needed)
                    # - Else if stored rate == 1.0: fetch from currency_converter
                    # - Else: use stored rate
                    if txn.currency == base_currency:
                        txn_rate = Decimal("1.0")
                    elif txn.exchange_rate == Decimal("1.0"):
                        rate = asyncio.run(
                            currency_converter.get_rate(txn.currency, base_currency, txn.date)
                        )
                        txn_rate = Decimal(str(rate)) if rate else Decimal("1.0")
                    else:
                        txn_rate = txn.exchange_rate

                    # FEE transactions: fee in 'amount' field
                    if txn.type == TransactionType.FEE:
                        fee_in_base = txn.amount * txn_rate
                        fees += fee_in_base

                    # DIVIDEND/INTEREST/DISTRIBUTION/REWARD/DEPOSIT/WITHDRAWAL: fee in
                    # 'fees' field. Fee was already deducted from amount by broker,
                    # we're just recognizing the expense
                    # EXCLUDE CONVERSION (has separate FEE transactions) and BUY/SELL
                    # (capitalized)
                    elif (
                        txn.type
                        in [
                            TransactionType.DIVIDEND,
                            TransactionType.INTEREST,
                            TransactionType.DISTRIBUTION,
                            TransactionType.REWARD,
                            TransactionType.DEPOSIT,
                            TransactionType.WITHDRAWAL,
                        ]
                        and txn.fees
                        and txn.fees > 0
                    ):
                        fee_in_base = txn.fees * txn_rate
                        fees += fee_in_base

                # Calculate income (gross) and track withholding taxes
                # (sum of dividends, distributions, interest in base currency)
                # Money market funds: show total distributions at current rate
                # Stocks: only count dividends that hit cash (not reinvested)
                income = Decimal("0")
                holding_taxes = Decimal("0")

                # GAAP/IFRS: ALL distributions/dividends/interest are income when received,
                # regardless of whether reinvested or taken as cash.
                # Reinvestment is a SEPARATE transaction (buying more shares).
                #
                # For all holdings (stocks, funds, money market funds):
                # - Count ALL income transactions (don't skip reinvested ones)
                # - Reinvested income increases cost basis (already handled in BUY
                #   transactions)
                # - This matches journal entries: DR Cash / CR Dividend Income (for
                #   all distributions)
                for txn in transactions:
                    if txn.type in [
                        TransactionType.DIVIDEND,
                        TransactionType.DISTRIBUTION,
                        TransactionType.INTEREST,
                    ]:
                        # IMPORTANT: Match accounting_service.py create_journal_line() logic exactly
                        if txn.currency == base_currency:
                            txn_rate = Decimal("1.0")
                        elif txn.exchange_rate == Decimal("1.0"):
                            rate = asyncio.run(
                                currency_converter.get_rate(txn.currency, base_currency, txn.date)
                            )
                            txn_rate = Decimal(str(rate)) if rate else Decimal("1.0")
                        else:
                            txn_rate = txn.exchange_rate

                        # GAAP: Income is GROSS amount (before tax deduction)
                        # Journal entries record: CR Dividend Income (gross = net + tax)
                        # transaction.amount is the NET cash received (after tax and fees)
                        # But accounting service grosses up by adding back BOTH tax AND fees
                        # So we need to match that by grossing up here too
                        gross_amount = txn.amount
                        if txn.tax_amount:
                            gross_amount += txn.tax_amount
                        if txn.fees:
                            gross_amount += txn.fees

                        div_in_base = gross_amount * txn_rate
                        income += div_in_base

                        # Track withholding taxes separately (as negative - they're expenses)
                        if txn.tax_amount:
                            holding_taxes -= txn.tax_amount * txn_rate

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
                holding_fees += fees  # Track holding fees separately for breakdown display
                total_income += income
                total_currency_gain += currency_gain
                total_taxes += holding_taxes

            # === ORPHAN TRANSACTIONS ===
            # Process transactions not attributed to any holding (holding_id
            # IS NULL). These include: dividends/interest from sold positions,
            # standalone fees, taxes, conversions
            orphan_income = Decimal("0")
            orphan_fees = Decimal("0")
            orphan_taxes = Decimal("0")

            # Query all transactions without holdings for this portfolio
            orphan_transactions = (
                session.query(Transaction)
                .join(Account, Transaction.account_id == Account.id)
                .filter(
                    Account.portfolio_id == portfolio_obj.id,
                    Transaction.holding_id.is_(None),  # No holding attribution
                )
                .all()
            )

            for txn in orphan_transactions:
                # IMPORTANT: Match accounting_service.py create_journal_line() logic exactly
                if txn.currency == base_currency:
                    txn_rate = Decimal("1.0")
                elif txn.exchange_rate == Decimal("1.0"):
                    rate = asyncio.run(
                        currency_converter.get_rate(txn.currency, base_currency, txn.date)
                    )
                    txn_rate = Decimal(str(rate)) if rate else Decimal("1.0")
                else:
                    txn_rate = txn.exchange_rate

                # Categorize orphan transactions
                if txn.type in [
                    TransactionType.DIVIDEND,
                    TransactionType.DISTRIBUTION,
                    TransactionType.INTEREST,
                ]:
                    # GAAP: Income is GROSS (before tax and fee deductions)
                    # Gross up the amount like we do for holding transactions
                    gross_amount = txn.amount
                    if txn.tax_amount:
                        gross_amount += txn.tax_amount
                    if txn.fees:
                        gross_amount += txn.fees

                    amount_in_base = gross_amount * txn_rate
                    # Income: credit (K) is money in, debit (D) is money out
                    if txn.debit_credit == "K":
                        orphan_income += amount_in_base
                    else:
                        orphan_income -= amount_in_base

                    # Track orphan taxes (negative for expenses)
                    if txn.tax_amount:
                        orphan_taxes -= txn.tax_amount * txn_rate

                    # Track orphan fees on dividends/distributions (if any)
                    if txn.fees and txn.fees > 0:
                        orphan_fees += txn.fees * txn_rate

                # Track standalone FEE transactions
                # FEE transactions store the fee amount in the 'amount' field.
                if txn.type == TransactionType.FEE:
                    orphan_fees += txn.amount * txn_rate

                # NOTE: CONVERSION transaction fees are NOT tracked here because
                # they are imported as separate FEE transactions (Lightyear broker).
                # The transaction.fees field on CONVERSION is informational only.
                # Counting it would double-count with the separate FEE transaction.

                if txn.type == TransactionType.TAX:
                    # Tax: amount is always positive, debit_credit indicates direction
                    # D (debit) = money out = expense (negative)
                    # K (credit) = money in = refund (positive)
                    tax_in_base = txn.amount * txn_rate
                    if txn.debit_credit == "D":
                        orphan_taxes -= tax_in_base  # Expense reduces gains
                    else:
                        orphan_taxes += tax_in_base  # Refund increases gains

            # Add orphan transactions to portfolio totals
            total_income += orphan_income
            # Only FEE transactions (CONVERSION fees are in separate FEE
            # transactions)
            total_fees += orphan_fees
            total_taxes += orphan_taxes  # Already negative for expenses

            # Override with accounting-based totals if requested
            # This ensures exact matching with balance sheet when mark-to-market was just run
            if use_accounting:
                accounting_gains = _get_gains_from_accounting(session, portfolio_obj.id)

                # Calculate scaling factors for each component to proportionally allocate
                # accounting values to holdings (makes columns sum to totals row exactly)
                capital_scale = (
                    accounting_gains["capital_gain"] / total_capital_gain
                    if total_capital_gain != Decimal("0")
                    else Decimal("1")
                )
                income_scale = (
                    accounting_gains["income"] / total_income
                    if total_income != Decimal("0")
                    else Decimal("1")
                )
                fees_scale = (
                    accounting_gains["fees"] / total_fees
                    if total_fees != Decimal("0")
                    else Decimal("1")
                )
                currency_scale = (
                    accounting_gains["currency_gain"] / total_currency_gain
                    if total_currency_gain != Decimal("0")
                    else Decimal("1")
                )

                # Scale each holding's values proportionally
                for h in holdings_data:
                    h["capital_gain"] = Decimal(str(h["capital_gain"])) * capital_scale
                    h["income"] = Decimal(str(h["income"])) * income_scale
                    h["fees"] = Decimal(str(h["fees"])) * fees_scale
                    h["currency_gain"] = Decimal(str(h["currency_gain"])) * currency_scale
                    # Recalculate total for this holding
                    h["total_gain"] = (
                        Decimal(str(h["capital_gain"]))
                        + Decimal(str(h["income"]))
                        - Decimal(str(h["fees"]))
                        + Decimal(str(h["currency_gain"]))
                    )

                # Update portfolio totals to accounting values
                total_capital_gain = accounting_gains["capital_gain"]
                total_income = accounting_gains["income"]
                total_fees = accounting_gains["fees"]
                total_taxes = accounting_gains["taxes"]
                total_currency_gain = accounting_gains["currency_gain"]

                # Also replace market value with accounting investment value
                # (Investments + Fair Value Adjustment from balance sheet)
                from src.models import ChartAccount
                from src.services.accounting_service import get_account_balance

                # Get Investments - Securities (1200)
                investments_account = (
                    session.query(ChartAccount)
                    .filter(
                        ChartAccount.portfolio_id == portfolio_obj.id, ChartAccount.code == "1200"
                    )
                    .first()
                )

                # Get Fair Value Adjustment - Investments (1210)
                fair_value_account = (
                    session.query(ChartAccount)
                    .filter(
                        ChartAccount.portfolio_id == portfolio_obj.id, ChartAccount.code == "1210"
                    )
                    .first()
                )

                if investments_account and fair_value_account:
                    investments_balance = get_account_balance(
                        session, investments_account.id, date.today()
                    )
                    fair_value_balance = get_account_balance(
                        session, fair_value_account.id, date.today()
                    )
                    total_portfolio_value = investments_balance + fair_value_balance

            # Get cash accounts
            accounts = session.query(Account).filter(Account.portfolio_id == portfolio_obj.id).all()

            # Calculate cash balances by account
            cash_data = []
            total_cash_value = Decimal("0")

            # In accounting mode, get cash balance from journal entries (historical rates)
            if use_accounting:
                from src.models import AccountCategory, ChartAccount
                from src.services.accounting_service import get_account_balance

                # Get all CASH category accounts (Cash + Currency Exchange Clearing)
                cash_accounts = (
                    session.query(ChartAccount)
                    .filter(
                        ChartAccount.portfolio_id == portfolio_obj.id,
                        ChartAccount.category == AccountCategory.CASH,
                    )
                    .all()
                )

                for cash_account in cash_accounts:
                    # Get cash balance at historical rates from journal entries
                    account_balance = get_account_balance(session, cash_account.id, date.today())
                    total_cash_value += account_balance

            for account in accounts:
                # Calculate balance from transactions (with eager loading to prevent N+1)
                transactions = (
                    session.query(Transaction)
                    .options(joinedload(Transaction.account))
                    .filter(Transaction.account_id == account.id)
                    .all()
                )

                # Group balances by currency (credits - debits)
                # Must match journal entry logic for cash impact
                balances_by_currency = {}
                for txn in transactions:
                    currency = txn.currency
                    if currency not in balances_by_currency:
                        balances_by_currency[currency] = Decimal("0")

                    # Calculate actual cash impact per transaction type
                    # (must match accounting_service.py journal entry logic)
                    cash_impact = Decimal("0")

                    if txn.type in [TransactionType.BUY]:
                        # CR Cash (purchase amount - fees already in amount)
                        cash_impact = -txn.amount

                    elif txn.type in [TransactionType.SELL]:
                        # DR Cash (sale proceeds - fees already in amount)
                        cash_impact = txn.amount

                    elif txn.type in [TransactionType.DEPOSIT]:
                        # DR Cash (amount is already NET - fees already deducted)
                        cash_impact = txn.amount

                    elif txn.type in [TransactionType.WITHDRAWAL]:
                        # CR Cash (amount + fees)
                        cash_impact = -(txn.amount + (txn.fees or Decimal("0")))

                    elif txn.type in [
                        TransactionType.DIVIDEND,
                        TransactionType.INTEREST,
                        TransactionType.DISTRIBUTION,
                        TransactionType.REWARD,
                    ]:
                        # DR Cash (net = amount, fees are separate)
                        cash_impact = txn.amount

                    elif txn.type in [TransactionType.FEE]:
                        # CR Cash (fee amount)
                        cash_impact = -txn.amount

                    elif txn.type == TransactionType.CONVERSION:
                        if txn.debit_credit == "D":
                            # CR Cash (amount only - fees handled by separate FEE transaction)
                            cash_impact = -txn.amount
                        else:  # K
                            # DR Cash (amount received)
                            cash_impact = txn.amount

                    elif txn.type == TransactionType.TAX:
                        # CR Cash (tax amount)
                        cash_impact = -txn.amount

                    balances_by_currency[currency] += cash_impact

                # Create cash entry for each currency with non-zero balance
                for currency, balance in balances_by_currency.items():
                    if balance != 0:  # Only show non-zero balances
                        # Convert to base currency
                        # When using accounting mode, use historical rates (from journal entries)
                        # When using transactions mode, use current rates
                        if use_accounting:
                            # Accounting mode: we'll get the EUR balance from journal entries later
                            # For now, just track the physical currency balance
                            balance_in_base = balance  # Will be replaced with accounting balance
                        elif currency != base_currency:
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
                        # Only add to total in transactions mode
                        # In accounting mode, we'll use the journal entry balance
                        if not use_accounting:
                            total_cash_value += balance_in_base

            # Add cash to total portfolio value
            total_portfolio_value_with_cash = total_portfolio_value + total_cash_value

            # Calculate total gain (including all taxes)
            total_gain = (
                total_capital_gain + total_income - total_fees + total_currency_gain + total_taxes
            )

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
            taxes_pct = (
                (total_taxes / total_cost_basis * 100) if total_cost_basis > 0 else Decimal("0")
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

            cap_amt_str, cap_pct_str = format_gain(total_capital_gain, capital_gain_pct)
            fees_amt_str, fees_pct_str = format_gain(-total_fees, -fees_pct)
            inc_amt_str, inc_pct_str = format_gain(total_income, income_pct)
            taxes_amt_str, taxes_pct_str = format_gain(total_taxes, taxes_pct)
            curr_amt_str, curr_pct_str = format_gain(total_currency_gain, currency_gain_pct)
            tot_amt_str, tot_pct_str = format_gain(total_gain, total_gain_pct)

            summary_table.add_row("Capital gain", cap_amt_str, cap_pct_str)
            summary_table.add_row("Fees contribution", fees_amt_str, fees_pct_str)
            summary_table.add_row("Income gain", inc_amt_str, inc_pct_str)
            summary_table.add_row("Tax expense", taxes_amt_str, taxes_pct_str)
            summary_table.add_row("Currency gain", curr_amt_str, curr_pct_str)
            summary_table.add_row("Total gain", tot_amt_str, tot_pct_str)

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

            # Add orphan fees row (fees not attributed to any holding)
            # This ensures the total row equals the sum of the columns
            # Only orphan_fees (FEE transactions) - CONVERSION fees are separate FEE transactions
            if orphan_fees > Decimal("0.01"):
                holdings_table.add_row(
                    "[bold]Orphan fees[/bold]",
                    "Fees not attributed to holdings",
                    "",
                    "",
                    "",
                    "",
                    "0.00",
                    format_cell(-orphan_fees),
                    "0.00",
                    "0.00",
                    format_cell(-orphan_fees),
                    style="dim",
                )

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
