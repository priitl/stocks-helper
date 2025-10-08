"""Accounting subcommands for viewing financial reports."""

from datetime import date, datetime
from decimal import Decimal

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError

from src.lib.db import db_session
from src.models import (
    AccountCategory,
    AccountType,
    ChartAccount,
    JournalEntry,
    JournalEntryStatus,
    JournalEntryType,
    JournalLine,
    Portfolio,
)
from src.services.accounting_service import (
    get_account_balance,
    get_next_entry_number,
)

console = Console()


@click.group(name="accounting")
def accounting_group() -> None:
    """View accounting reports and financial statements."""
    pass


@accounting_group.command(name="chart")
@click.option("--portfolio-id", help="Portfolio ID (defaults to first portfolio)")
def chart_of_accounts(portfolio_id: str | None) -> None:
    """Show chart of accounts."""
    try:
        with db_session() as session:
            # Get portfolio
            if portfolio_id:
                portfolio = session.get(Portfolio, portfolio_id)
                if not portfolio:
                    console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
                    return
            else:
                portfolio = session.execute(select(Portfolio).limit(1)).scalar_one_or_none()
                if not portfolio:
                    console.print("[red]No portfolios found[/red]")
                    return

            # Get chart of accounts
            accounts = (
                session.execute(
                    select(ChartAccount)
                    .where(ChartAccount.portfolio_id == portfolio.id)
                    .order_by(ChartAccount.code)
                )
                .scalars()
                .all()
            )

            if not accounts:
                console.print("[yellow]No chart of accounts found[/yellow]")
                return

            # Group by type
            table = Table(title=f"Chart of Accounts - {portfolio.name}")
            table.add_column("Code", style="cyan")
            table.add_column("Account Name", style="green")
            table.add_column("Type", style="yellow")
            table.add_column("Category", style="magenta")
            table.add_column("Currency", style="blue")
            table.add_column("Status", style="dim")

            current_type = None
            for acc in accounts:
                # Add section header when type changes
                if current_type != acc.type:
                    if current_type is not None:
                        table.add_row("", "", "", "", "", "")  # Blank row
                    current_type = acc.type

                status = "Active" if acc.is_active else "Inactive"
                table.add_row(
                    acc.code,
                    acc.name,
                    acc.type.value,
                    acc.category.value,
                    acc.currency,
                    status,
                )

            console.print(table)

    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


@accounting_group.command(name="trial-balance")
@click.option("--portfolio-id", help="Portfolio ID (defaults to first portfolio)")
@click.option(
    "--as-of",
    help="Date (YYYY-MM-DD, defaults to today)",
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
def trial_balance(portfolio_id: str | None, as_of: datetime | None) -> None:
    """Show trial balance (account balances)."""
    try:
        with db_session() as session:
            # Get portfolio
            if portfolio_id:
                portfolio = session.get(Portfolio, portfolio_id)
                if not portfolio:
                    console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
                    return
            else:
                portfolio = session.execute(select(Portfolio).limit(1)).scalar_one_or_none()
                if not portfolio:
                    console.print("[red]No portfolios found[/red]")
                    return

            as_of_date = as_of.date() if as_of else date.today()

            # Get chart of accounts
            accounts = (
                session.execute(
                    select(ChartAccount)
                    .where(
                        and_(
                            ChartAccount.portfolio_id == portfolio.id,
                            ChartAccount.is_active == True,  # noqa: E712
                        )
                    )
                    .order_by(ChartAccount.code)
                )
                .scalars()
                .all()
            )

            if not accounts:
                console.print("[yellow]No accounts found[/yellow]")
                return

            # Calculate balances
            table = Table(title=f"Trial Balance - {portfolio.name} (as of {as_of_date})")
            table.add_column("Code", style="cyan")
            table.add_column("Account", style="green")
            table.add_column("Debit", style="yellow", justify="right")
            table.add_column("Credit", style="magenta", justify="right")

            total_debits = Decimal("0")
            total_credits = Decimal("0")

            for acc in accounts:
                balance = get_account_balance(session, acc.id, as_of_date)

                if balance == 0:
                    continue

                # Display based on normal balance side
                if acc.normal_balance == "DEBIT":
                    debit_amt = abs(balance) if balance > 0 else Decimal("0")
                    credit_amt = abs(balance) if balance < 0 else Decimal("0")
                else:
                    credit_amt = abs(balance) if balance > 0 else Decimal("0")
                    debit_amt = abs(balance) if balance < 0 else Decimal("0")

                total_debits += debit_amt
                total_credits += credit_amt

                debit_str = f"{acc.currency} {debit_amt:,.2f}" if debit_amt > 0 else ""
                credit_str = f"{acc.currency} {credit_amt:,.2f}" if credit_amt > 0 else ""

                table.add_row(acc.code, acc.name, debit_str, credit_str)

            # Add totals
            table.add_row("", "", "", "", end_section=True)
            table.add_row(
                "",
                "[bold]TOTAL[/bold]",
                f"[bold]{portfolio.base_currency} {total_debits:,.2f}[/bold]",
                f"[bold]{portfolio.base_currency} {total_credits:,.2f}[/bold]",
            )

            # Check if balanced
            if total_debits == total_credits:
                table.add_row(
                    "",
                    "[green]✓ BALANCED[/green]",
                    "",
                    "",
                )
            else:
                diff = abs(total_debits - total_credits)
                table.add_row(
                    "",
                    f"[red]✗ OUT OF BALANCE: {portfolio.base_currency} {diff:,.2f}[/red]",
                    "",
                    "",
                )

            console.print(table)

    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


@accounting_group.command(name="balance-sheet")
@click.option("--portfolio-id", help="Portfolio ID (defaults to first portfolio)")
@click.option(
    "--as-of",
    help="Date (YYYY-MM-DD, defaults to today)",
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
def balance_sheet(portfolio_id: str | None, as_of: datetime | None) -> None:
    """Show balance sheet (Assets = Liabilities + Equity)."""
    try:
        with db_session() as session:
            # Get portfolio
            if portfolio_id:
                portfolio = session.get(Portfolio, portfolio_id)
                if not portfolio:
                    console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
                    return
            else:
                portfolio = session.execute(select(Portfolio).limit(1)).scalar_one_or_none()
                if not portfolio:
                    console.print("[red]No portfolios found[/red]")
                    return

            as_of_date = as_of.date() if as_of else date.today()

            # Get accounts by type
            accounts = (
                session.execute(
                    select(ChartAccount)
                    .where(ChartAccount.portfolio_id == portfolio.id)
                    .order_by(ChartAccount.code)
                )
                .scalars()
                .all()
            )

            table = Table(title=f"Balance Sheet - {portfolio.name} (as of {as_of_date})")
            table.add_column("Account", style="green", width=40)
            table.add_column("Amount", style="cyan", justify="right")

            # ASSETS
            total_assets = Decimal("0")
            table.add_row("[bold]ASSETS[/bold]", "")

            for acc in accounts:
                if acc.type != AccountType.ASSET:
                    continue

                balance = get_account_balance(session, acc.id, as_of_date)
                if balance == 0:
                    continue

                total_assets += balance
                table.add_row(f"  {acc.name}", f"{acc.currency} {balance:,.2f}")

            table.add_row(
                "[bold]Total Assets[/bold]",
                f"[bold]{portfolio.base_currency} {total_assets:,.2f}[/bold]",
                end_section=True,
            )

            # LIABILITIES
            total_liabilities = Decimal("0")
            table.add_row("[bold]LIABILITIES[/bold]", "")

            has_liabilities = False
            for acc in accounts:
                if acc.type != AccountType.LIABILITY:
                    continue

                balance = get_account_balance(session, acc.id, as_of_date)
                if balance == 0:
                    continue

                has_liabilities = True
                total_liabilities += balance
                table.add_row(f"  {acc.name}", f"{acc.currency} {balance:,.2f}")

            if not has_liabilities:
                table.add_row("  [dim]None[/dim]", "[dim]0.00[/dim]")

            table.add_row(
                "[bold]Total Liabilities[/bold]",
                f"[bold]{portfolio.base_currency} {total_liabilities:,.2f}[/bold]",
                end_section=True,
            )

            # EQUITY
            total_equity = Decimal("0")
            table.add_row("[bold]EQUITY[/bold]", "")

            for acc in accounts:
                if acc.type != AccountType.EQUITY:
                    continue

                balance = get_account_balance(session, acc.id, as_of_date)
                if balance == 0:
                    continue

                total_equity += balance
                table.add_row(f"  {acc.name}", f"{acc.currency} {balance:,.2f}")

            table.add_row(
                "[bold]Total Equity[/bold]",
                f"[bold]{portfolio.base_currency} {total_equity:,.2f}[/bold]",
                end_section=True,
            )

            # TOTAL L + E
            total_l_e = total_liabilities + total_equity
            table.add_row(
                "[bold]Total Liabilities + Equity[/bold]",
                f"[bold]{portfolio.base_currency} {total_l_e:,.2f}[/bold]",
                end_section=True,
            )

            # Check equation
            if abs(total_assets - total_l_e) < Decimal("0.01"):
                table.add_row("[green]✓ BALANCED (A = L + E)[/green]", "")
            else:
                diff = abs(total_assets - total_l_e)
                table.add_row(
                    f"[red]✗ OUT OF BALANCE: {portfolio.base_currency} {diff:,.2f}[/red]",
                    "",
                )

            console.print(table)

    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


@accounting_group.command(name="income-statement")
@click.option("--portfolio-id", help="Portfolio ID (defaults to first portfolio)")
@click.option(
    "--from-date",
    help="Start date (YYYY-MM-DD)",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
)
@click.option(
    "--to-date",
    help="End date (YYYY-MM-DD, defaults to today)",
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
def income_statement(
    portfolio_id: str | None, from_date: datetime, to_date: datetime | None
) -> None:
    """Show income statement (Revenue - Expenses = Net Income)."""
    try:
        with db_session() as session:
            # Get portfolio
            if portfolio_id:
                portfolio = session.get(Portfolio, portfolio_id)
                if not portfolio:
                    console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
                    return
            else:
                portfolio = session.execute(select(Portfolio).limit(1)).scalar_one_or_none()
                if not portfolio:
                    console.print("[red]No portfolios found[/red]")
                    return

            start_date = from_date.date()
            end_date = to_date.date() if to_date else date.today()

            # Get revenue and expense accounts
            accounts = (
                session.execute(
                    select(ChartAccount)
                    .where(ChartAccount.portfolio_id == portfolio.id)
                    .order_by(ChartAccount.code)
                )
                .scalars()
                .all()
            )

            table = Table(
                title=f"Income Statement - {portfolio.name}\n{start_date} to {end_date}"
            )
            table.add_column("Account", style="green", width=40)
            table.add_column("Amount", style="cyan", justify="right")

            # REVENUE
            total_revenue = Decimal("0")
            table.add_row("[bold]REVENUE[/bold]", "")

            for acc in accounts:
                if acc.type != AccountType.REVENUE:
                    continue

                # Get activity in date range
                activity = (
                    session.execute(
                        select(
                            func.sum(JournalLine.credit_amount).label("credits"),
                            func.sum(JournalLine.debit_amount).label("debits"),
                        )
                        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
                        .where(
                            and_(
                                JournalLine.account_id == acc.id,
                                JournalEntry.status == JournalEntryStatus.POSTED,
                                JournalEntry.entry_date >= start_date,
                                JournalEntry.entry_date <= end_date,
                            )
                        )
                    )
                    .one()
                )

                credits = activity.credits or Decimal("0")
                debits = activity.debits or Decimal("0")
                balance = credits - debits  # Revenue has credit balance

                if balance == 0:
                    continue

                total_revenue += balance
                table.add_row(f"  {acc.name}", f"{acc.currency} {balance:,.2f}")

            table.add_row(
                "[bold]Total Revenue[/bold]",
                f"[bold]{portfolio.base_currency} {total_revenue:,.2f}[/bold]",
                end_section=True,
            )

            # EXPENSES
            total_expenses = Decimal("0")
            table.add_row("[bold]EXPENSES[/bold]", "")

            for acc in accounts:
                if acc.type != AccountType.EXPENSE:
                    continue

                # Get activity in date range
                activity = (
                    session.execute(
                        select(
                            func.sum(JournalLine.debit_amount).label("debits"),
                            func.sum(JournalLine.credit_amount).label("credits"),
                        )
                        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
                        .where(
                            and_(
                                JournalLine.account_id == acc.id,
                                JournalEntry.status == JournalEntryStatus.POSTED,
                                JournalEntry.entry_date >= start_date,
                                JournalEntry.entry_date <= end_date,
                            )
                        )
                    )
                    .one()
                )

                debits = activity.debits or Decimal("0")
                credits = activity.credits or Decimal("0")
                balance = debits - credits  # Expenses have debit balance

                if balance == 0:
                    continue

                total_expenses += balance
                table.add_row(f"  {acc.name}", f"{acc.currency} {balance:,.2f}")

            table.add_row(
                "[bold]Total Expenses[/bold]",
                f"[bold]{portfolio.base_currency} {total_expenses:,.2f}[/bold]",
                end_section=True,
            )

            # NET INCOME
            net_income = total_revenue - total_expenses
            color = "green" if net_income >= 0 else "red"
            table.add_row(
                f"[bold {color}]NET INCOME[/bold {color}]",
                f"[bold {color}]{portfolio.base_currency} {net_income:,.2f}[/bold {color}]",
            )

            console.print(table)

    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


@accounting_group.command(name="ledger")
@click.option("--portfolio-id", help="Portfolio ID (defaults to first portfolio)")
@click.option("--account-code", help="Filter by account code", default=None)
@click.option("--limit", help="Number of entries to show", default=20, type=int)
def general_ledger(portfolio_id: str | None, account_code: str | None, limit: int) -> None:
    """Show general ledger (journal entries)."""
    try:
        with db_session() as session:
            # Get portfolio
            if portfolio_id:
                portfolio = session.get(Portfolio, portfolio_id)
                if not portfolio:
                    console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
                    return
            else:
                portfolio = session.execute(select(Portfolio).limit(1)).scalar_one_or_none()
                if not portfolio:
                    console.print("[red]No portfolios found[/red]")
                    return

            # Build query
            query = (
                select(JournalEntry)
                .where(JournalEntry.portfolio_id == portfolio.id)
                .order_by(JournalEntry.entry_number.desc())
            )

            if account_code:
                # Filter by account
                query = query.join(JournalLine).join(ChartAccount).where(
                    ChartAccount.code == account_code
                )

            query = query.limit(limit)

            entries = session.execute(query).scalars().all()

            if not entries:
                console.print("[yellow]No journal entries found[/yellow]")
                return

            title = f"General Ledger - {portfolio.name}"
            if account_code:
                title += f" (Account: {account_code})"

            table = Table(title=title)
            table.add_column("Entry #", style="cyan", justify="right")
            table.add_column("Date", style="yellow")
            table.add_column("Account", style="green")
            table.add_column("Debit", style="magenta", justify="right")
            table.add_column("Credit", style="magenta", justify="right")
            table.add_column("Description", style="dim", max_width=40)

            for entry in entries:
                # Add entry header
                first_line = True

                for line in entry.lines:
                    entry_num = str(entry.entry_number) if first_line else ""
                    entry_date = str(entry.entry_date) if first_line else ""
                    desc = entry.description if first_line else ""

                    debit_str = f"{line.currency} {line.debit_amount:,.2f}" if line.debit_amount > 0 else ""
                    credit_str = f"{line.currency} {line.credit_amount:,.2f}" if line.credit_amount > 0 else ""

                    table.add_row(
                        entry_num,
                        entry_date,
                        line.account.name,
                        debit_str,
                        credit_str,
                        desc,
                    )

                    first_line = False

                # Blank row between entries
                table.add_row("", "", "", "", "", "")

            console.print(table)

    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")


@accounting_group.command(name="close-period")
@click.option("--portfolio-id", help="Portfolio ID (defaults to first portfolio)")
@click.option(
    "--period-end",
    help="Period end date (YYYY-MM-DD, defaults to today)",
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--description",
    help="Closing entry description",
    default="Close revenue and expense accounts to retained earnings",
)
@click.confirmation_option(
    prompt="This will close all revenue and expense accounts to retained earnings. Continue?"
)
def close_period(
    portfolio_id: str | None, period_end: datetime | None, description: str
) -> None:
    """Close revenue and expense accounts to retained earnings.

    This creates closing entries that:
    1. Zero out all revenue accounts (transfer to retained earnings)
    2. Zero out all expense accounts (transfer to retained earnings)
    3. Net effect: Retained Earnings increases by net income

    This is typically done at year-end or period-end.
    """
    try:
        with db_session() as session:
            # Get portfolio
            if portfolio_id:
                portfolio = session.get(Portfolio, portfolio_id)
                if not portfolio:
                    console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
                    return
            else:
                portfolio = session.execute(select(Portfolio).limit(1)).scalar_one_or_none()
                if not portfolio:
                    console.print("[red]No portfolios found[/red]")
                    return

            close_date = period_end.date() if period_end else date.today()

            # Get retained earnings account
            retained_earnings = (
                session.execute(
                    select(ChartAccount).where(
                        and_(
                            ChartAccount.portfolio_id == portfolio.id,
                            ChartAccount.category == AccountCategory.RETAINED_EARNINGS,
                        )
                    )
                )
                .scalars()
                .first()
            )

            if not retained_earnings:
                console.print("[red]Retained Earnings account not found[/red]")
                return

            # Get all revenue and expense accounts
            revenue_expense_accounts = (
                session.execute(
                    select(ChartAccount)
                    .where(
                        and_(
                            ChartAccount.portfolio_id == portfolio.id,
                            ChartAccount.type.in_([AccountType.REVENUE, AccountType.EXPENSE]),
                        )
                    )
                    .order_by(ChartAccount.code)
                )
                .scalars()
                .all()
            )

            if not revenue_expense_accounts:
                console.print("[yellow]No revenue or expense accounts to close[/yellow]")
                return

            # Calculate balances and create closing entries
            total_revenue = Decimal("0")
            total_expenses = Decimal("0")
            lines_to_create = []
            line_num = 1

            console.print(f"\n[cyan]Calculating balances as of {close_date}...[/cyan]\n")

            # Create the closing entry
            entry = JournalEntry(
                portfolio_id=portfolio.id,
                entry_number=get_next_entry_number(session, portfolio.id),
                entry_date=close_date,
                type=JournalEntryType.CLOSING,
                status=JournalEntryStatus.POSTED,
                description=description,
                created_by="user",
            )
            session.add(entry)
            session.flush()

            # Close revenue accounts (debit revenue, credit retained earnings)
            for acc in revenue_expense_accounts:
                if acc.type != AccountType.REVENUE:
                    continue

                balance = get_account_balance(session, acc.id, close_date)
                if balance == 0:
                    continue

                total_revenue += balance
                console.print(f"  [green]Closing {acc.name}:[/green] {acc.currency} {balance:,.2f}")

                # Debit revenue account (to zero it)
                lines_to_create.append(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=acc.id,
                        line_number=line_num,
                        debit_amount=balance,
                        credit_amount=Decimal("0"),
                        currency=acc.currency,
                        description=f"Close {acc.name}",
                    )
                )
                line_num += 1

            # Close expense accounts (credit expense, debit retained earnings)
            for acc in revenue_expense_accounts:
                if acc.type != AccountType.EXPENSE:
                    continue

                balance = get_account_balance(session, acc.id, close_date)
                if balance == 0:
                    continue

                total_expenses += balance
                console.print(f"  [yellow]Closing {acc.name}:[/yellow] {acc.currency} {balance:,.2f}")

                # Credit expense account (to zero it)
                lines_to_create.append(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=acc.id,
                        line_number=line_num,
                        debit_amount=Decimal("0"),
                        credit_amount=balance,
                        currency=acc.currency,
                        description=f"Close {acc.name}",
                    )
                )
                line_num += 1

            # Net to retained earnings
            net_income = total_revenue - total_expenses

            if net_income > 0:
                # Profit: Credit retained earnings
                lines_to_create.append(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=retained_earnings.id,
                        line_number=line_num,
                        debit_amount=Decimal("0"),
                        credit_amount=net_income,
                        currency=portfolio.base_currency,
                        description="Net income for period",
                    )
                )
            elif net_income < 0:
                # Loss: Debit retained earnings
                lines_to_create.append(
                    JournalLine(
                        journal_entry_id=entry.id,
                        account_id=retained_earnings.id,
                        line_number=line_num,
                        debit_amount=abs(net_income),
                        credit_amount=Decimal("0"),
                        currency=portfolio.base_currency,
                        description="Net loss for period",
                    )
                )

            # Add all lines
            for line in lines_to_create:
                session.add(line)

            session.flush()

            # Verify balanced
            if not entry.is_balanced:
                console.print(
                    f"[red]Error: Closing entry not balanced "
                    f"(DR={entry.total_debits}, CR={entry.total_credits})[/red]"
                )
                return

            # Show summary
            console.print("\n[bold green]✓ Period closed successfully![/bold green]\n")

            table = Table(title="Closing Entry Summary")
            table.add_column("Item", style="cyan")
            table.add_column("Amount", style="green", justify="right")

            table.add_row("Total Revenue", f"{portfolio.base_currency} {total_revenue:,.2f}")
            table.add_row("Total Expenses", f"{portfolio.base_currency} {total_expenses:,.2f}")
            table.add_row("", "")

            color = "green" if net_income >= 0 else "red"
            label = "Net Income" if net_income >= 0 else "Net Loss"
            table.add_row(
                f"[bold {color}]{label}[/bold {color}]",
                f"[bold {color}]{portfolio.base_currency} {net_income:,.2f}[/bold {color}]",
            )
            table.add_row("", "")
            table.add_row(
                "Transferred to Retained Earnings",
                f"{portfolio.base_currency} {net_income:,.2f}",
            )
            table.add_row("Journal Entry #", str(entry.entry_number))

            console.print(table)

            console.print(
                f"\n[dim]Tip: Run 'stocks-helper accounting balance-sheet' "
                f"to see updated equity.[/dim]\n"
            )

    except SQLAlchemyError as e:
        console.print(f"[red]Database error: {e}[/red]")
