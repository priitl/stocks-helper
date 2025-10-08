# Unrealized Gains/Losses Implementation Plan

## Current State

As of this commit, the accounting system **fully supports realized transactions**:
- ✅ GAAP/IFRS compliant lot tracking with FIFO
- ✅ Realized capital gains/losses on SELL transactions
- ✅ Multi-currency support with FX gains/losses
- ✅ Proper cost basis tracking via SecurityLot model
- ✅ Balance sheet includes net income from temporary accounts
- ✅ All journal entries balanced with Numeric(20, 8) precision

**Portfolio Overview:**
- Total portfolio value: EUR 74,556.45 (market value)
- Accounting assets: EUR 56,377.68 (cost basis)
- **Gap: EUR 18,178.77 = Unrealized gains not yet tracked**

## Objective

Implement IFRS 9 mark-to-market accounting for **unrealized gains/losses** on securities still held in the portfolio.

## Technical Requirements

### 1. Market Data Integration

**Required:**
- Fetch current market prices for all holdings
- Convert prices to portfolio base currency
- Handle bonds/fixed income separately (amortized cost vs fair value)

**Implementation location:**
- Already have `src/services/market_data_fetcher.py`
- Extend to support batch price fetching for mark-to-market

### 2. Fair Value Calculation

**Algorithm:**
```python
For each holding:
    current_market_value = quantity * current_price * exchange_rate
    cost_basis = sum(lot.total_cost_base for lot in open_lots)
    unrealized_gain_loss = current_market_value - cost_basis
```

**Data sources:**
- SecurityLot table: cost basis for open lots
- Market data service: current prices
- Exchange rate service: current FX rates

### 3. Journal Entry Creation

**Placeholder exists:** `src/services/lot_tracking_service.py:194`
- Function: `mark_securities_to_market()`
- Currently returns None

**Journal entry format:**
```
If market value > cost basis (unrealized gain):
    DR Fair Value Adjustment - Investments    [amount]
        CR Unrealized Gains on Investments            [amount]

If market value < cost basis (unrealized loss):
    DR Unrealized Losses on Investments       [amount]
        CR Fair Value Adjustment - Investments        [amount]
```

**Accounts already exist:**
- 1210: Fair Value Adjustment - Investments (ASSET)
- 4210: Unrealized Gains on Investments (REVENUE)
- 5210: Unrealized Losses on Investments (EXPENSE)

### 4. Incremental Adjustments

**Important:** Track previous fair value adjustment to avoid duplicates

**Approach:**
1. Get existing Fair Value Adjustment balance
2. Calculate required adjustment = new unrealized G/L - existing adjustment
3. Create journal entry for the **difference only**

**Example:**
```
Previous adjustment: +10,000 EUR (unrealized gain)
Current unrealized G/L: +18,179 EUR
Required adjustment: +8,179 EUR (incremental)
```

## Implementation Steps

### Phase 1: Core Mark-to-Market
1. ✅ Chart of accounts includes fair value accounts (DONE)
2. ✅ SecurityLot model tracks cost basis (DONE)
3. 🔲 Implement `mark_securities_to_market()` function
   - Fetch current prices for all securities
   - Calculate unrealized G/L per holding
   - Get existing fair value adjustment balance
   - Create incremental adjustment entry
   - Post journal entry

### Phase 2: Automation & Scheduling
1. 🔲 Add CLI command: `stocks-helper accounting mark-to-market`
2. 🔲 Add `--as-of` date parameter for historical marks
3. 🔲 Add dry-run mode to preview adjustments
4. 🔲 Consider daily/weekly auto-mark option

### Phase 3: Reporting Enhancements
1. 🔲 Update portfolio overview to show realized vs unrealized separately
2. 🔲 Add unrealized G/L report by security
3. 🔲 Show fair value adjustment in balance sheet separately
4. 🔲 Track historical unrealized G/L trends

### Phase 4: Advanced Features
1. 🔲 Implement IAS 21 FX mark-to-market for foreign currency cash
   - Function: `mark_currency_to_market()` at line 238
   - Track unrealized FX gains/losses on cash positions
2. 🔲 Support different valuation methods (FIFO, LIFO, Average Cost)
3. 🔲 Add tax lot selection for optimized tax planning

## Testing Strategy

### Unit Tests
- Test mark-to-market calculation accuracy
- Test incremental adjustment logic
- Test multi-currency scenarios
- Test bonds vs equities handling

### Integration Tests
- Import transactions → mark to market → verify balance sheet
- Multiple mark-to-market runs → verify no duplicates
- Sell transaction after mark → verify realized G/L correct

### Reconciliation Tests
- Portfolio value should equal:
  - Cash + Investments at Cost + Fair Value Adjustment
- Net income should equal:
  - Realized G/L + Unrealized G/L + Dividends - Fees - Taxes

## Success Criteria

✅ **Balance Sheet Reconciliation:**
```
Assets (EUR 74,557) = Liabilities (EUR 0) + Equity (EUR 56,378) + Net Income (EUR 18,179)

Where Net Income includes:
- Realized gains/losses: EUR 7,325 ✅ (already tracked)
- Unrealized gains/losses: EUR 18,179 🔲 (to be implemented)
- Other income/expenses: EUR (7,325) ✅ (already tracked)
```

✅ **Portfolio Value Match:**
- Accounting total assets = Portfolio market value
- Currently: EUR 56,378 ≠ EUR 74,557
- After implementation: EUR 74,557 = EUR 74,557

## Files to Modify

1. **`src/services/lot_tracking_service.py:194-235`**
   - Implement `mark_securities_to_market()`
   - Add logic for incremental adjustments

2. **`src/cli/accounting_cli.py`**
   - Add `mark-to-market` command
   - Add dry-run and date options

3. **`tests/test_lot_tracking.py`** (create if needed)
   - Test unrealized G/L calculations
   - Test mark-to-market journal entries

## Notes

- **Timing:** Run mark-to-market at period-end (daily, monthly, yearly)
- **Close period:** Before closing, run mark-to-market to capture all unrealized G/L
- **Tax reporting:** Unrealized G/L is for GAAP/IFRS only, not taxable until realized
- **Performance:** Batch price fetching to minimize API calls

## References

- IFRS 9: Financial Instruments (Fair Value Through Profit or Loss)
- IAS 21: Foreign Currency Translation
- Current implementation: `docs/GAAP-IFRS-COMPLIANCE-PLAN.md`
