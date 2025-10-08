# Multi-Currency Accounting Fix - Implementation Guide

## Problem Summary

The accounting system is currently **broken** due to currency mixing:

```python
# CURRENT (BROKEN):
JournalLine(
    debit_amount=100,        # Could be USD, NOK, or EUR!
    currency="NOK",          # Stored but not used for conversion
)

# Balance sheet naively sums all amounts:
Cash = €14,126 + NOK(-30,664) + USD(-11,769) = -€28,307 ❌
```

**Result:** Balance sheet shows **negative €28,307 cash** (nonsense)

**Actual cash:** €384 EUR + 12 NOK (€1.03) + ~$0 USD = **€385 total** ✓

---

## Solution: Proper Multi-Currency Accounting

Convert all amounts to base currency (EUR) while preserving original currency data:

```python
# NEW (CORRECT):
create_journal_line(
    debit_amount=100,                    # Amount in NOK
    currency="NOK",                      # Transaction currency
    base_currency="EUR",                 # Portfolio base currency
    exchange_rate=0.08608,               # NOK/EUR rate
    # Result stored in database:
    # debit_amount=8.61 EUR (100 * 0.08608)
    # foreign_amount=100 NOK
    # foreign_currency="NOK"
    # exchange_rate=0.08608
)
```

**Benefits:**
- ✅ Balance sheet sums correctly (all EUR)
- ✅ Preserves original transaction currency for reconciliation
- ✅ Can show ledger in both EUR and original currencies
- ✅ Tax reports have accurate original amounts

---

## Implementation Plan

### Step 1: Add Imports (src/services/accounting_service.py)

```python
# At top of file, add:
import asyncio
from src.services.currency_converter import CurrencyConverter
```

### Step 2: Copy Helper Function

Copy the `create_journal_line()` function from:
- **Source:** `src/services/accounting_service_multicurrency.py`
- **Destination:** `src/services/accounting_service.py` (after `get_next_entry_number()`)

### Step 3: Update `record_transaction_as_journal_entry()` Setup

Find this section (around line 243):

```python
portfolio_id = account.portfolio_id

# Create journal entry header
```

Replace with:

```python
portfolio_id = account.portfolio_id

# Get portfolio to determine base currency
portfolio = session.get(Portfolio, portfolio_id)
if not portfolio:
    raise ValueError(f"Portfolio {portfolio_id} not found")

base_currency = portfolio.base_currency

# Initialize currency converter for exchange rates
currency_converter = CurrencyConverter()

# Get exchange rate from transaction, or default to 1.0
exchange_rate = transaction.exchange_rate or Decimal("1.0")

# Create journal entry header
```

### Step 4: Replace All JournalLine() Calls

For **each** transaction type (BUY, SELL, DIVIDEND, etc.), replace:

**OLD:**
```python
lines.append(
    JournalLine(
        journal_entry_id=entry.id,
        account_id=accounts["cash"].id,
        line_number=line_num,
        debit_amount=transaction.amount,
        credit_amount=Decimal("0"),
        currency=transaction.currency,
        description="Dividend received",
    )
)
```

**NEW:**
```python
lines.append(
    create_journal_line(
        journal_entry_id=entry.id,
        account_id=accounts["cash"].id,
        line_number=line_num,
        debit_amount=transaction.amount,
        credit_amount=Decimal("0"),
        currency=transaction.currency,
        base_currency=base_currency,
        exchange_rate=exchange_rate,
        description="Dividend received",
        currency_converter=currency_converter,
        transaction_date=transaction.date,
    )
)
```

**Transaction types to update:**
1. ✅ BUY (2 journal lines)
2. ✅ SELL (2 journal lines)
3. DIVIDEND (3 journal lines - cash, tax, income)
4. INTEREST (2 journal lines)
5. DEPOSIT (2 journal lines)
6. WITHDRAWAL (2 journal lines)
7. FEE (2 journal lines)
8. TAX (2 journal lines)
9. DISTRIBUTION (3 journal lines - if exists)
10. REWARD (2 journal lines - if exists)
11. CONVERSION (1 memo line)
12. ADJUSTMENT (1 memo line)

**Total:** ~24-30 JournalLine() calls to replace

---

## Testing Plan

### Test 1: Verify Syntax
```bash
python3 -m py_compile src/services/accounting_service.py
```

### Test 2: Check Balance Sheet
```bash
source .venv/bin/activate
stocks-helper accounting balance-sheet --portfolio-id d97bf694-efc9-4c6a-ab97-367e8ab4f2b3
```

**Expected results:**
- ✅ Cash: **Positive** (around €385, not -€28,307)
- ✅ Total Assets: **Positive** (around €74,000)
- ✅ No "OUT OF BALANCE" error (after closing period)

### Test 3: Verify Foreign Currency Preservation
```bash
source .venv/bin/activate
stocks-helper accounting ledger --portfolio-id d97bf694-efc9-4c6a-ab97-367e8ab4f2b3 --account-code 1000 | head -20
```

**Expected:**
- Lines should show both EUR (base) and original currency (foreign)
- Example: `€8.61 [100 NOK @ 0.08608]`

---

## Current State

**Files modified:**
- ✅ `src/cli/portfolio.py` - Fixed ICSUSSDP currency gain (money market fund handling)
- ✅ `src/services/accounting_service_multicurrency.py` - Reference implementation created
- ⏳ `src/services/accounting_service.py` - **NEEDS UPDATE** (main fix)

**Portfolio status:**
- ✅ Portfolio overview: **CORRECT** (€74,138.91)
- ❌ Accounting balance sheet: **BROKEN** (-€28,307 cash)
- ⏳ Accounting reports: Will be fixed after this implementation

---

## Next Steps

1. Start new clean terminal session
2. Read this file: `cat MULTICURRENCY_ACCOUNTING_FIX.md`
3. Read reference implementation: `cat src/services/accounting_service_multicurrency.py`
4. Follow implementation plan step-by-step
5. Test after each major section
6. Validate with balance sheet command

---

## Key Files

- **Fix implementation:** `src/services/accounting_service.py` (main file to edit)
- **Reference helper:** `src/services/accounting_service_multicurrency.py` (copy from here)
- **This guide:** `MULTICURRENCY_ACCOUNTING_FIX.md`
- **Portfolio ID:** `d97bf694-efc9-4c6a-ab97-367e8ab4f2b3` (for testing)

---

## Questions?

- **Why not just convert at display time?** We need accurate balances for double-entry validation
- **Will this affect existing data?** No - this only changes how NEW journal entries are created
- **What about existing broken entries?** Those would need a migration script (separate task)
- **Exchange rates missing?** The helper function fetches them via CurrencyConverter if needed

---

**Status:** Ready for implementation
**Complexity:** Medium (careful but straightforward)
**Estimated time:** 20-30 minutes
**Risk:** Low (can test incrementally)
