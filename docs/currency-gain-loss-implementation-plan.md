# Currency Gain/Loss Accounting Implementation Plan

## Problem Statement

Currently, the trial balance shows EUR 1,702.81 total cash, but the actual cash in original currencies is:
- EUR: 384.03
- NOK: 12.00 (EUR 0.21 equivalent)
- USD: 0.00

The EUR 1,318.57 difference represents **unrealized currency exchange gains/losses** from USD transactions recorded at different historical exchange rates.

### Current Behavior

When a USD transaction occurs:
1. **Transaction date 1**: Buy stock for USD 1,000 @ rate 0.95 → recorded as EUR 950
2. **Transaction date 2**: Sell stock for USD 1,000 @ rate 0.85 → recorded as EUR 850

Even though USD in = USD out (USD 0), the EUR amounts don't balance:
- EUR 950 (credit) - EUR 850 (debit) = EUR 100 difference

This EUR 100 is an **exchange rate loss** but it's currently "hidden" in the Cash account.

## Solution: Foreign Exchange Gain/Loss Account

### Chart of Accounts Changes

Add new account to track currency fluctuations:

```
Account Code: 4300
Account Name: Foreign Exchange Gain
Account Type: Revenue
Normal Balance: Credit
Parent: Income Accounts
```

```
Account Code: 5300
Account Name: Foreign Exchange Loss
Account Type: Expense
Normal Balance: Debit
Parent: Expense Accounts
```

**Alternative**: Single account approach:
```
Account Code: 7000
Account Name: Foreign Exchange Gain/Loss
Account Type: Other Income/Expense
Normal Balance: Either (can be debit or credit)
```

### Implementation Approach

#### Option 1: Periodic Revaluation (Recommended for Phase 1)

**When**: Run monthly/quarterly as a separate process

**How**:
1. For each foreign currency (NOK, USD):
   - Sum all foreign_amount debits and credits → Net position
   - Get current exchange rate
   - Calculate expected EUR value: Net position × Current rate
   - Calculate actual EUR value: Sum of all EUR debits - credits
   - Difference = Unrealized gain/loss

2. Create adjusting journal entry:
   ```
   If gain (actual < expected):
     DR: Cash (EUR adjustment)
     CR: Foreign Exchange Gain

   If loss (actual > expected):
     DR: Foreign Exchange Loss
     CR: Cash (EUR adjustment)
   ```

**Pros**:
- Simple to implement
- Separates operational transactions from revaluation
- Easy to understand and audit

**Cons**:
- Doesn't track realized vs unrealized gains
- Requires periodic manual/scheduled runs

#### Option 2: Real-Time Tracking (Future Enhancement)

**When**: At each transaction

**How**:
1. Track "cost basis" in EUR for each foreign currency position
2. When foreign currency is spent/received:
   - Compare current exchange rate to original rate
   - Record gain/loss on the difference
   - Update cost basis using weighted average

**Pros**:
- More accurate, real-time tracking
- Distinguishes realized vs unrealized gains

**Cons**:
- Complex implementation
- Requires FIFO/LIFO/Weighted Average cost basis tracking
- Similar complexity to stock lot tracking

## Recommended Implementation: Option 1 (Periodic Revaluation)

### Phase 1: Basic Revaluation

#### 1. Add Accounts to Chart of Accounts

**File**: `src/services/accounting_service.py`

Add to `initialize_chart_of_accounts()`:

```python
# Foreign Exchange accounts
ChartAccount(
    portfolio_id=portfolio_id,
    code="7000",
    name="Foreign Exchange Gain/Loss",
    account_type=AccountType.OTHER_INCOME_EXPENSE,
    normal_balance=NormalBalance.EITHER,
    is_active=True,
),
```

#### 2. Create Revaluation Service

**File**: `src/services/currency_revaluation_service.py`

```python
"""
Currency revaluation service for foreign exchange gain/loss tracking.
"""

from decimal import Decimal
from datetime import date
from sqlalchemy.orm import Session

from src.models import (
    Portfolio,
    ChartAccount,
    JournalEntry,
    JournalLine,
    JournalEntryType,
    JournalEntryStatus,
)
from src.services.currency_converter import CurrencyConverter


async def revalue_foreign_currency_positions(
    session: Session,
    portfolio_id: str,
    as_of_date: date,
    currency_converter: CurrencyConverter,
) -> JournalEntry | None:
    """
    Revalue foreign currency cash positions and record gain/loss.

    Args:
        session: Database session
        portfolio_id: Portfolio to revalue
        as_of_date: Date to revalue as of
        currency_converter: Currency converter for current rates

    Returns:
        Journal entry with revaluation adjustments, or None if no adjustment needed
    """
    # Get portfolio
    portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    base_currency = portfolio.base_currency

    # Get Cash account
    cash_account = (
        session.query(ChartAccount)
        .filter_by(portfolio_id=portfolio_id, code="1000")
        .first()
    )

    # Get FX Gain/Loss account
    fx_account = (
        session.query(ChartAccount)
        .filter_by(portfolio_id=portfolio_id, code="7000")
        .first()
    )

    if not cash_account or not fx_account:
        raise ValueError("Required accounts not found")

    # Get all Cash journal lines
    cash_lines = (
        session.query(JournalLine)
        .join(JournalEntry)
        .filter(
            JournalLine.account_id == cash_account.id,
            JournalEntry.portfolio_id == portfolio_id,
            JournalEntry.status == JournalEntryStatus.POSTED,
            JournalEntry.entry_date <= as_of_date,
        )
        .all()
    )

    # Calculate position by currency
    positions = {}  # {currency: {"foreign": Decimal, "eur": Decimal}}

    for line in cash_lines:
        if not line.foreign_currency:
            continue

        curr = line.foreign_currency

        if curr not in positions:
            positions[curr] = {"foreign": Decimal("0"), "eur": Decimal("0")}

        # Track foreign amount
        if line.debit_amount > 0:
            positions[curr]["foreign"] += line.foreign_amount or Decimal("0")
            positions[curr]["eur"] += line.debit_amount
        else:
            positions[curr]["foreign"] -= line.foreign_amount or Decimal("0")
            positions[curr]["eur"] -= line.credit_amount

    # Calculate adjustments needed
    adjustments = {}

    for currency, position in positions.items():
        if currency == base_currency:
            continue  # Skip base currency

        foreign_amount = position["foreign"]
        book_eur = position["eur"]

        # Get current exchange rate
        current_rate = await currency_converter.get_rate(
            currency, base_currency, as_of_date
        )

        if not current_rate:
            print(f"Warning: No exchange rate for {currency}/{base_currency}")
            continue

        # Calculate current EUR value
        current_eur = foreign_amount * Decimal(str(current_rate))

        # Calculate adjustment needed
        adjustment = current_eur - book_eur

        if abs(adjustment) > Decimal("0.01"):  # Materiality threshold
            adjustments[currency] = {
                "foreign_amount": foreign_amount,
                "book_eur": book_eur,
                "current_rate": Decimal(str(current_rate)),
                "current_eur": current_eur,
                "adjustment": adjustment,
            }

    if not adjustments:
        return None

    # Create revaluation journal entry
    entry_number = (
        session.query(JournalEntry)
        .filter_by(portfolio_id=portfolio_id)
        .count()
    ) + 1

    entry = JournalEntry(
        portfolio_id=portfolio_id,
        entry_number=entry_number,
        entry_date=as_of_date,
        posting_date=as_of_date,
        type=JournalEntryType.ADJUSTMENT,
        status=JournalEntryStatus.POSTED,
        description=f"Foreign currency revaluation as of {as_of_date}",
        created_by="system",
    )
    session.add(entry)
    session.flush()

    # Create journal lines
    line_num = 1
    total_adjustment = Decimal("0")

    for currency, adj in adjustments.items():
        # Adjust Cash account
        if adj["adjustment"] > 0:
            # Gain: Cash increases
            line = JournalLine(
                journal_entry_id=entry.id,
                account_id=cash_account.id,
                line_number=line_num,
                debit_amount=adj["adjustment"],
                credit_amount=Decimal("0"),
                currency=base_currency,
                foreign_amount=Decimal("0"),  # This is an adjustment, not a real transaction
                foreign_currency=currency,
                exchange_rate=adj["current_rate"],
                description=f"Revaluation gain on {currency} position",
            )
        else:
            # Loss: Cash decreases
            line = JournalLine(
                journal_entry_id=entry.id,
                account_id=cash_account.id,
                line_number=line_num,
                debit_amount=Decimal("0"),
                credit_amount=abs(adj["adjustment"]),
                currency=base_currency,
                foreign_amount=Decimal("0"),
                foreign_currency=currency,
                exchange_rate=adj["current_rate"],
                description=f"Revaluation loss on {currency} position",
            )

        session.add(line)
        line_num += 1
        total_adjustment += adj["adjustment"]

    # Offset to FX Gain/Loss account
    if total_adjustment > 0:
        # Gain
        line = JournalLine(
            journal_entry_id=entry.id,
            account_id=fx_account.id,
            line_number=line_num,
            debit_amount=Decimal("0"),
            credit_amount=total_adjustment,
            currency=base_currency,
            exchange_rate=Decimal("1.0"),
            description="Foreign exchange revaluation gain",
        )
    else:
        # Loss
        line = JournalLine(
            journal_entry_id=entry.id,
            account_id=fx_account.id,
            line_number=line_num,
            debit_amount=abs(total_adjustment),
            credit_amount=Decimal("0"),
            currency=base_currency,
            exchange_rate=Decimal("1.0"),
            description="Foreign exchange revaluation loss",
        )

    session.add(line)

    return entry
```

#### 3. Add CLI Command

**File**: `src/cli/accounting_cli.py`

```python
@accounting.command()
@click.option("--portfolio-id", help="Portfolio ID")
@click.option("--as-of", type=click.DateTime(formats=["%Y-%m-%d"]), help="Revalue as of date")
def revalue_currency(portfolio_id: str | None, as_of: datetime | None) -> None:
    """Revalue foreign currency positions and record gain/loss."""
    from src.services.currency_revaluation_service import revalue_foreign_currency_positions
    from src.services.currency_converter import CurrencyConverter

    # Implementation...
```

### Phase 2: Enhancements

1. **Reverse Previous Revaluations**: Before creating new revaluation, reverse the previous one
2. **Realized vs Unrealized**: Track which gains/losses are realized (closed positions) vs unrealized (open positions)
3. **Per-Currency Reporting**: Show breakdown of gains/losses by currency
4. **Automated Scheduling**: Run revaluation automatically at month-end

## Testing Plan

### Test Case 1: Simple USD Gain

```
1. Buy USD 100 @ rate 0.90 → EUR 90
2. Sell USD 100 @ rate 1.00 → EUR 100
3. Net USD: 0, Net EUR: 10

Expected revaluation: 0 (position closed, no adjustment needed)
```

### Test Case 2: Open Position Gain

```
1. CONVERSION: EUR → USD 100 @ rate 0.90 → EUR 90
2. Current rate: 0.85
3. Position: USD 100, Book EUR: 90

Expected revaluation:
  Current value: USD 100 × 0.85 = EUR 85
  Adjustment: EUR 85 - EUR 90 = EUR -5 (loss)

  DR: Foreign Exchange Loss  EUR 5
  CR: Cash                   EUR 5
```

### Test Case 3: Multiple Currencies

```
1. NOK 1,000 position, Book: EUR 100, Current: EUR 105 → EUR 5 gain
2. USD 500 position, Book: EUR 50, Current: EUR 45 → EUR 5 loss
3. Net adjustment: EUR 0

Expected: No journal entry (immaterial or netting to zero)
```

## Migration Strategy

### For Existing Data

**Option A**: Run revaluation once to clean up historical data
```bash
stocks-helper accounting revalue-currency --portfolio-id <id> --as-of 2025-10-09
```

**Option B**: Accept current trial balance as-is, start fresh from next month
- Keep existing EUR 1,702.81 as baseline
- Only track changes going forward

## Documentation Requirements

1. **User Guide**: Explain what currency revaluation is and when to run it
2. **Accounting Policy**: Document approach (periodic vs real-time)
3. **Chart of Accounts**: Update documentation with new account 7000
4. **Trial Balance**: Add note explaining multi-currency accounting

## Success Criteria

✅ Trial balance Cash matches multi-currency cash positions within 1 EUR
✅ Foreign Exchange Gain/Loss account tracks all currency movements
✅ Revaluation can be run multiple times (reversible)
✅ Reports show breakdown by currency
✅ Documentation is clear and comprehensive

## Non-Goals (Out of Scope)

- Real-time gain/loss tracking (Phase 1)
- FIFO/LIFO cost basis for currencies
- Forward contracts or hedging
- Multi-currency P&L statements
- Cryptocurrency support

## Timeline Estimate

- **Phase 1 Implementation**: 4-6 hours
- **Testing**: 2-3 hours
- **Documentation**: 1-2 hours
- **Total**: 7-11 hours

## Related Issues

- Multi-currency trial balance reporting
- Currency conversion rate caching
- Historical rate accuracy
- Month-end close procedures
