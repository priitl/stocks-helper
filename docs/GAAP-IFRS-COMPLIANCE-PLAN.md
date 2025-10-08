# GAAP/IFRS Compliance Implementation Plan

## Overview

Transform the accounting system to full GAAP/IFRS compliance for:
1. **Securities**: IFRS 9 (Fair Value Through Profit or Loss)
2. **Foreign Currency**: IAS 21 (Monetary items remeasurement)

## Current State vs. Target State

### Securities Accounting

**Current (Simplified):**
```
BUY:
  DR Investments (amount)
  CR Cash (amount)

SELL:
  DR Cash (proceeds)
  CR Investments (proceeds)  ← WRONG: No cost basis tracking
```

**Target (GAAP/IFRS):**
```
BUY:
  DR Investments at Cost (amount)
  CR Cash (amount)
  + Create SecurityLot record

SELL:
  DR Cash (proceeds)
  CR Investments at Cost (cost basis from FIFO lots)
  CR Realized Gain (OR DR Realized Loss)
  + Update SecurityLot records (reduce remaining_quantity)

MARK-TO-MARKET (after each transaction or period-end):
  DR Unrealized Gain/Loss (adjustment)
  CR Investments Fair Value Adjustment (adjustment)
```

### Foreign Currency Accounting

**Current (Option A - Partial):**
- Records FX gain/loss only when foreign currency is spent
- Cash shows historical cost

**Target (IAS 21 Compliant - Option B):**
- Mark-to-market after EVERY transaction
- Cash always shows current market value
- Unrealized FX gains/losses recorded continuously

---

## Database Changes

### 1. New Model: SecurityLot

**File**: `src/models/security_lot.py`

```python
class SecurityLot(Base):
    """Track individual security purchase lots for FIFO cost basis.

    GAAP/IFRS requires tracking cost basis of individual lots
    to calculate realized gains/losses on sales.
    """
    __tablename__ = "security_lots"

    id: UUID (PK)
    holding_id: UUID (FK to holdings)
    transaction_id: UUID (FK to transactions - the BUY)
    security_ticker: str
    purchase_date: date
    quantity: Decimal  # Original quantity purchased
    remaining_quantity: Decimal  # After partial sales
    cost_per_share: Decimal  # In transaction currency
    cost_per_share_base: Decimal  # In base currency (EUR)
    currency: str
    exchange_rate: Decimal
    is_closed: bool  # True when remaining_quantity = 0

    # Relationships
    holding: Holding
    transaction: Transaction
```

### 2. New Model: SecurityAllocation

**File**: `src/models/security_lot.py`

```python
class SecurityAllocation(Base):
    """Track which lots were used for each SELL transaction (FIFO matching)."""
    __tablename__ = "security_allocations"

    id: UUID (PK)
    lot_id: UUID (FK to security_lots)
    sell_transaction_id: UUID (FK to transactions - the SELL)
    quantity_allocated: Decimal
    cost_basis: Decimal  # In base currency
    realized_gain_loss: Decimal  # Proceeds - cost_basis

    # Relationships
    lot: SecurityLot
    transaction: Transaction
```

### 3. Chart of Accounts Updates

Add new accounts to `initialize_chart_of_accounts()`:

```python
# Realized gains/losses (when securities sold)
"realized_gains": ChartAccount(
    code="4200",
    name="Realized Capital Gains",
    type=AccountType.REVENUE,
    category=AccountCategory.CAPITAL_GAINS,
),
"realized_losses": ChartAccount(
    code="5200",
    name="Realized Capital Losses",
    type=AccountType.EXPENSE,
    category=AccountCategory.CAPITAL_LOSSES,
),

# Unrealized gains/losses (mark-to-market adjustments)
"unrealized_gains": ChartAccount(
    code="4210",
    name="Unrealized Gains on Investments",
    type=AccountType.REVENUE,
    category=AccountCategory.CAPITAL_GAINS,
),
"unrealized_losses": ChartAccount(
    code="5210",
    name="Unrealized Losses on Investments",
    type=AccountType.EXPENSE,
    category=AccountCategory.CAPITAL_LOSSES,
),

# Fair value adjustment (contra/adjunct to Investments)
"fair_value_adjustment": ChartAccount(
    code="1210",
    name="Fair Value Adjustment - Investments",
    type=AccountType.ASSET,
    category=AccountCategory.INVESTMENTS,
    description="Contra/adjunct account: Investments at Cost + FV Adjustment = Market Value",
),
```

**Balance Sheet Presentation:**
```
Assets:
  Investments at Cost:               EUR 50,000
  Fair Value Adjustment:             EUR  1,347
  Total Investments (Fair Value):    EUR 51,347  ← Market value
```

---

## Code Changes

### 1. Create Lot Tracking Functions

**File**: `src/services/lot_tracking_service.py` (NEW)

```python
def create_security_lot(
    session: Session,
    transaction: Transaction,
    holding_id: str,
) -> SecurityLot:
    """Create a new security lot from a BUY transaction."""

def allocate_lots_fifo(
    session: Session,
    holding_id: str,
    quantity_to_sell: Decimal,
    sell_date: date,
) -> list[tuple[SecurityLot, Decimal, Decimal]]:
    """
    Allocate lots using FIFO for a SELL transaction.

    Returns:
        List of (lot, quantity_allocated, cost_basis_eur)
    """

def mark_securities_to_market(
    session: Session,
    portfolio_id: str,
    as_of_date: date,
) -> JournalEntry | None:
    """
    Mark all securities to current market value.
    Creates adjustment entry for unrealized gains/losses.
    """

def mark_currency_to_market(
    session: Session,
    portfolio_id: str,
    cash_account_id: str,
    base_currency: str,
    as_of_date: date,
) -> JournalEntry | None:
    """
    Mark all foreign currency cash to current exchange rates.
    Creates adjustment entry for unrealized FX gains/losses.
    """
```

### 2. Update Accounting Service

**File**: `src/services/accounting_service.py`

#### BUY Transaction Changes:
```python
elif transaction.type == TransactionType.BUY:
    # ... existing code to create journal lines ...

    # NEW: Create security lot for cost basis tracking
    lot = create_security_lot(
        session=session,
        transaction=transaction,
        holding_id=holding.id,  # Need to get/create holding
    )
```

#### SELL Transaction Changes:
```python
elif transaction.type == TransactionType.SELL:
    # NEW: Get cost basis from FIFO lots
    allocations = allocate_lots_fifo(
        session=session,
        holding_id=holding.id,
        quantity_to_sell=transaction.quantity,
        sell_date=transaction.date,
    )

    total_cost_basis = sum(alloc[2] for alloc in allocations)
    proceeds = transaction.amount * exchange_rate
    realized_gain_loss = proceeds - total_cost_basis

    # Journal entry:
    lines = []

    # DR Cash
    lines.append(create_journal_line(..., debit_amount=proceeds, ...))

    # CR Investments at Cost
    lines.append(create_journal_line(..., credit_amount=total_cost_basis, ...))

    # CR Realized Gain OR DR Realized Loss
    if realized_gain_loss >= 0:
        lines.append(JournalLine(...
            account_id=accounts["realized_gains"].id,
            credit_amount=realized_gain_loss,
        ))
    else:
        lines.append(JournalLine(...
            account_id=accounts["realized_losses"].id,
            debit_amount=abs(realized_gain_loss),
        ))

    # Create allocation records
    for lot, qty_allocated, cost_basis in allocations:
        SecurityAllocation(
            lot_id=lot.id,
            sell_transaction_id=transaction.id,
            quantity_allocated=qty_allocated,
            cost_basis=cost_basis,
            realized_gain_loss=...,
        )
```

#### Add Mark-to-Market After Each Transaction:
```python
def record_transaction_as_journal_entry(...) -> JournalEntry:
    # ... existing code ...

    # NEW: Mark-to-market adjustments
    # 1. Mark securities to market
    mark_securities_to_market(session, portfolio_id, transaction.date)

    # 2. Mark foreign currency to market
    mark_currency_to_market(
        session, portfolio_id, accounts["cash"].id,
        base_currency, transaction.date
    )

    return entry
```

---

## Migration Strategy

### Option 1: Full Rebuild (Recommended)
1. Drop all journal entries and lots
2. Recreate chart of accounts with new accounts
3. Reprocess all transactions in chronological order
4. Creates lots as we go
5. Final mark-to-market at end

**Script**: `rebuild_journal_entries_gaap.py`

### Option 2: Incremental Migration
1. Create lot records from existing transactions
2. Add new accounts to existing chart
3. Reprocess only SELL transactions
4. Run mark-to-market

---

## Testing Plan

### Test Case 1: Simple Buy-Hold-Sell
```
T1: BUY 100 shares @ USD 10 (rate 0.90) → EUR 900
    - Creates Lot #1: 100 shares @ EUR 9.00/share
    - DR Investments EUR 900, CR Cash EUR 900

T2: Current price USD 12 (rate 0.85) → EUR 1,020 market value
    Mark-to-market:
    - Unrealized gain: EUR 1,020 - EUR 900 = EUR 120
    - DR Investments FV Adj EUR 120, CR Unrealized Gain EUR 120

T3: SELL 100 shares @ USD 12 (rate 0.85) → EUR 1,020 proceeds
    - Use Lot #1: Cost basis EUR 900
    - Realized gain: EUR 1,020 - EUR 900 = EUR 120
    - DR Cash EUR 1,020
    - CR Investments at Cost EUR 900
    - CR Realized Gain EUR 120
    - Reverse unrealized gain: DR Unrealized Gain EUR 120, CR Investments FV Adj EUR 120
```

### Test Case 2: Multiple Lots (FIFO)
```
T1: BUY 100 @ EUR 10 → Lot A
T2: BUY 100 @ EUR 12 → Lot B
T3: SELL 150
    - Use Lot A: 100 shares @ EUR 10 = EUR 1,000
    - Use Lot B: 50 shares @ EUR 12 = EUR 600
    - Total cost basis: EUR 1,600
```

### Test Case 3: Foreign Currency Mark-to-Market
```
T1: CONVERSION: EUR 1,000 → USD 1,100 @ rate 0.909
    Cash USD: +1,100 (cost basis EUR 1,000)

T2: Current rate: 0.85
    Market value: USD 1,100 * 0.85 = EUR 935
    Unrealized FX loss: EUR 935 - EUR 1,000 = EUR -65
    - DR FX Loss EUR 65, CR Cash EUR 65

T3: BUY stock for USD 500 @ rate 0.85
    - Spends USD 500 from position
    - Remaining: USD 600 (cost basis EUR 545.45)
    - Mark-to-market: USD 600 * 0.85 = EUR 510
    - Unrealized FX loss: EUR 510 - EUR 545.45 = EUR -35.45
```

---

## Success Criteria

✅ **Trial Balance = Portfolio Value** (within rounding)
✅ All securities tracked with individual lots
✅ Realized gains/losses calculated using FIFO
✅ Unrealized gains/losses updated after each transaction
✅ Foreign currency cash at current exchange rates
✅ Balance sheet shows fair value of investments
✅ Income statement separates realized vs unrealized gains

---

## Implementation Order

1. ✅ Design document (this file)
2. ⏳ Create SecurityLot and SecurityAllocation models
3. ⏳ Update chart of accounts
4. ⏳ Implement lot_tracking_service.py
5. ⏳ Update BUY transactions (create lots)
6. ⏳ Update SELL transactions (FIFO matching + realized G/L)
7. ⏳ Implement mark_securities_to_market()
8. ⏳ Implement mark_currency_to_market() (Option B)
9. ⏳ Create rebuild script
10. ⏳ Test and verify

---

## Estimated Effort

- Model creation: 1-2 hours
- Lot tracking service: 2-3 hours
- Accounting service updates: 3-4 hours
- Mark-to-market functions: 2-3 hours
- Testing and debugging: 2-3 hours

**Total: 10-15 hours of development**

---

## Notes

- This implements **FVTPL (Fair Value Through Profit or Loss)** classification per IFRS 9
- Alternative would be **FVOCI** (through other comprehensive income) but that's for strategic holdings, not trading portfolios
- The approach uses a **Fair Value Adjustment** contra account for clarity, but could also directly adjust Investments at Cost
- FIFO is used for lot matching (could also implement specific identification or average cost)
