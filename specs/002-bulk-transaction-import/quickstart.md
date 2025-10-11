# Quickstart: Bulk Transaction Import

## Purpose
Manual validation workflow for CSV import feature. Execute these steps to verify correct behavior before deploying.

## Prerequisites
- ✅ Python 3.11+ environment activated
- ✅ All dependencies installed: `pip install -e .[dev]`
- ✅ Sample CSV files present in `research/` directory:
  - `swed_2020_2021.csv`
  - `swed_2022_2023.csv`
  - `swed_2024_2025.csv`
  - `lightyear_2022_2025.csv`
- ✅ Test database initialized: `stocks-helper db init`

## Test Scenarios

### Scenario 1: Import Swedbank CSV (First Import)
**Purpose**: Verify basic import workflow with Swedbank format

```bash
# Clean state - reset test database
stocks-helper db reset --confirm

# Import Swedbank CSV
stocks-helper import csv research/swed_2020_2021.csv --broker swedbank
```

**Expected Output**:
```
Importing transactions from research/swed_2020_2021.csv (Swedbank format)...
✓ Parsed 150 rows
✓ Validated transactions
✓ Importing to database...

Import Summary
┌────────────┬────────────┬────────────┬────────┬──────────┐
│ Total Rows │ Successful │ Duplicates │ Errors │ Duration │
├────────────┼────────────┼────────────┼────────┼──────────┤
│        150 │        150 │          0 │      0 │     2.3s │
└────────────┴────────────┴────────────┴────────┴──────────┘

✓ Import completed successfully
```

**Verification**:
```bash
# Check transaction count
stocks-helper transactions list --limit 10

# Verify holdings updated
stocks-helper holdings list

# Check import batch record
stocks-helper import history --limit 1
```

**Expected**:
- 150 transactions visible in database
- Holdings reflect imported buy/sell transactions
- Import history shows 1 batch with 150 successful

---

### Scenario 2: Re-import Same CSV (Duplicate Detection)
**Purpose**: Verify duplicate handling via broker reference ID

```bash
# Re-import same CSV file
stocks-helper import csv research/swed_2020_2021.csv --broker swedbank
```

**Expected Output**:
```
Importing transactions from research/swed_2020_2021.csv (Swedbank format)...
✓ Parsed 150 rows
✓ Validated transactions
✓ Checking for duplicates...

Import Summary
┌────────────┬────────────┬────────────┬────────┬──────────┐
│ Total Rows │ Successful │ Duplicates │ Errors │ Duration │
├────────────┼────────────┼────────────┼────────┼──────────┤
│        150 │          0 │        150 │      0 │     1.1s │
└────────────┴────────────┴────────────┴────────┴──────────┘

✓ Import completed successfully (all duplicates skipped)
```

**Verification**:
```bash
# Check transaction count unchanged
stocks-helper transactions list --count

# Check import history
stocks-helper import history --limit 2
```

**Expected**:
- Still 150 transactions (no new ones added)
- Import history shows 2 batches, second with 150 duplicates

---

### Scenario 3: Import Lightyear CSV
**Purpose**: Verify Lightyear format parsing and multi-currency support

```bash
# Import Lightyear CSV
stocks-helper import csv research/lightyear_2022_2025.csv --broker lightyear
```

**Expected Output**:
```
Importing transactions from research/lightyear_2022_2025.csv (Lightyear format)...
✓ Parsed 450 rows
✓ Validated transactions
✓ Importing to database...

Import Summary
┌────────────┬────────────┬────────────┬────────┬──────────┐
│ Total Rows │ Successful │ Duplicates │ Errors │ Duration │
├────────────┼────────────┼────────────┼────────┼──────────┤
│        450 │        450 │          0 │      0 │     5.8s │
└────────────┴────────────┴────────────┴────────┴──────────┘

✓ Import completed successfully
```

**Verification**:
```bash
# Check multi-currency transactions
stocks-helper transactions list --currency USD --limit 5
stocks-helper transactions list --currency EUR --limit 5

# Verify Lightyear-specific transaction types
stocks-helper transactions list --type distribution --limit 5
stocks-helper transactions list --type interest --limit 5
```

**Expected**:
- Transactions in both USD and EUR visible
- Distribution, Interest, Reward transaction types present
- Holdings updated with Lightyear transactions

---

### Scenario 4: Import with Validation Errors (Partial Success)
**Purpose**: Verify error handling and manual intervention workflow

**Setup**: Create test CSV with intentional errors
```bash
# Create invalid_test.csv with mixed valid/invalid rows
cat > /tmp/invalid_test.csv << 'EOF'
"Date","Reference","Ticker","ISIN","Type","Quantity","CCY","Price/share","Gross Amount","FX Rate","Fee","Net Amt.","Tax Amt."
"01/10/2025 12:16:17","OR-VALID001","AAPL","US0378331005","Buy","10.000000000","USD","150.00","1500.00","","0.00","1500.00",""
"02/10/2025 12:16:17","OR-INVALID001","","","Buy","","USD","","","","0.00","",""
"03/10/2025 12:16:17","OR-VALID002","MSFT","US5949181045","Buy","5.000000000","USD","300.00","1500.00","","0.00","1500.00",""
"04/10/2025 12:16:17","OR-INVALID002","GOOG","US02079K3059","Buy","-10.000000000","USD","100.00","-1000.00","","0.00","-1000.00",""
"05/10/2025 12:16:17","OR-VALID003","TSLA","US88160R1014","Sell","3.000000000","USD","250.00","750.00","","0.00","750.00",""
EOF

# Import with errors
stocks-helper import csv /tmp/invalid_test.csv --broker lightyear
```

**Expected Output**:
```
Importing transactions from /tmp/invalid_test.csv (Lightyear format)...
✓ Parsed 5 rows
⚠ Validation found 2 errors
✓ Importing valid transactions...

Import Summary
┌────────────┬────────────┬────────────┬────────┬──────────┐
│ Total Rows │ Successful │ Duplicates │ Errors │ Duration │
├────────────┼────────────┼────────────┼────────┼──────────┤
│          5 │          3 │          0 │      2 │     0.5s │
└────────────┴────────────┴────────────┴────────┴──────────┘

Errors Requiring Manual Intervention
┌─────┬──────────────────────┬───────────────────────────────────────────────────┐
│ Row │ Error Type           │ Message                                           │
├─────┼──────────────────────┼───────────────────────────────────────────────────┤
│   2 │ missing_required_field│ Missing required field: ticker (Buy requires ticker)│
│   4 │ validation           │ Invalid quantity: must be positive, got -10.0     │
└─────┴──────────────────────┴───────────────────────────────────────────────────┘

⚠ Import completed with errors. Review errors above for manual intervention.
```

**Verification**:
```bash
# Check that 3 valid transactions were imported
stocks-helper transactions list --reference OR-VALID001
stocks-helper transactions list --reference OR-VALID002
stocks-helper transactions list --reference OR-VALID003

# View error details for manual correction
stocks-helper import errors <batch_id>
```

**Expected**:
- 3 valid transactions imported (OR-VALID001, OR-VALID002, OR-VALID003)
- 2 invalid transactions skipped
- Error details available with original CSV data

---

### Scenario 5: Dry Run (Validation Without Import)
**Purpose**: Verify dry-run mode for pre-import validation

```bash
# Dry run - validate without importing
stocks-helper import csv research/swed_2022_2023.csv --broker swedbank --dry-run
```

**Expected Output**:
```
Dry Run - Validating research/swed_2022_2023.csv (Swedbank format)...
✓ Parsed 200 rows
✓ Validated transactions
✓ Checked for duplicates

Dry Run - No data imported
┌────────────┬───────────────┬────────────┬────────┐
│ Total Rows │ Would Import  │ Duplicates │ Errors │
├────────────┼───────────────┼────────────┼────────┤
│        200 │           195 │          5 │      0 │
└────────────┴───────────────┴────────────┴────────┘

✓ Validation successful. Use without --dry-run to import.
```

**Verification**:
```bash
# Confirm no transactions added
stocks-helper transactions list --count

# Confirm no import batch record created
stocks-helper import history --limit 1
```

**Expected**:
- Transaction count unchanged
- No new import batch in history

---

### Scenario 6: Negative Holdings (Short Position Support)
**Purpose**: Verify system allows negative holdings per FR-007a

**Setup**: Create CSV with sell before buy
```bash
# Create test CSV with sell-first scenario
cat > /tmp/short_position_test.csv << 'EOF'
"Date","Reference","Ticker","ISIN","Type","Quantity","CCY","Price/share","Gross Amount","FX Rate","Fee","Net Amt.","Tax Amt."
"01/10/2025 12:00:00","OR-SHORT001","AAPL","US0378331005","Sell","10.000000000","USD","150.00","1500.00","","0.00","1500.00",""
"02/10/2025 12:00:00","OR-SHORT002","AAPL","US0378331005","Buy","5.000000000","USD","145.00","725.00","","0.00","725.00",""
EOF

# Import and verify negative holdings allowed
stocks-helper import csv /tmp/short_position_test.csv --broker lightyear
```

**Expected Output**:
```
Import Summary
┌────────────┬────────────┬────────────┬────────┬──────────┐
│ Total Rows │ Successful │ Duplicates │ Errors │ Duration │
├────────────┼────────────┼────────────┼────────┼──────────┤
│          2 │          2 │          0 │      0 │     0.3s │
└────────────┴────────────┴────────────┴────────┴──────────┘

✓ Import completed successfully
```

**Verification**:
```bash
# Check holdings - should show -5 AAPL (sold 10, bought 5)
stocks-helper holdings list --ticker AAPL
```

**Expected**:
- Import succeeds without error
- Holdings show negative quantity: AAPL: -5 shares

---

### Scenario 7: Large File Performance Test
**Purpose**: Verify performance meets target (< 30s for 10k transactions)

```bash
# Time import of largest CSV file
time stocks-helper import csv research/swed_2022_2023.csv --broker swedbank
```

**Expected Output**:
```
Import Summary
┌────────────┬────────────┬────────────┬────────┬──────────┐
│ Total Rows │ Successful │ Duplicates │ Errors │ Duration │
├────────────┼────────────┼────────────┼────────┼──────────┤
│      10000 │      10000 │          0 │      0 │    12.5s │
└────────────┴────────────┴────────────┴────────┴──────────┘

real    0m12.8s
user    0m11.2s
sys     0m0.5s
```

**Performance Criteria**:
- ✅ Processing duration < 30s for 10k rows
- ✅ Total time (including DB writes) < 30s
- ✅ Memory usage < 200MB (check with `memory_profiler` if needed)

---

### Scenario 8: Unknown Ticker Handling (Manual Intervention)
**Purpose**: Verify ticker validation and manual correction workflow

**Setup**: Create test CSV with unknown tickers
```bash
# Create test CSV with mixed valid/unknown tickers
cat > /tmp/unknown_tickers_test.csv << 'EOF'
"Date","Reference","Ticker","ISIN","Type","Quantity","CCY","Price/share","Gross Amount","FX Rate","Fee","Net Amt.","Tax Amt."
"01/10/2025 12:00:00","OR-VALID001","AAPL","US0378331005","Buy","10.000000000","USD","150.00","1500.00","","0.00","1500.00",""
"02/10/2025 12:00:00","OR-TYPO001","APPL","","Buy","5.000000000","USD","150.00","750.00","","0.00","750.00",""
"03/10/2025 12:00:00","OR-VALID002","MSFT","US5949181045","Buy","8.000000000","USD","300.00","2400.00","","0.00","2400.00",""
"04/10/2025 12:00:00","OR-UNKNOWN001","XYZZ","","Buy","15.000000000","USD","25.00","375.00","","0.00","375.00",""
"05/10/2025 12:00:00","OR-REGIONAL001","TKM1T","EE0000001105","Buy","20.000000000","EUR","8.50","170.00","","0.00","170.00",""
"06/10/2025 12:00:00","OR-VALID003","GOOG","US02079K3059","Buy","3.000000000","USD","2800.00","8400.00","","0.00","8400.00",""
EOF

# Import with unknown tickers
stocks-helper import csv /tmp/unknown_tickers_test.csv --broker lightyear
```

**Expected Output**:
```
Importing transactions from /tmp/unknown_tickers_test.csv (Lightyear format)...
✓ Parsed 6 rows
⚠ Validating tickers... (found 3 unknown)
✓ Importing valid transactions...

Import Summary
┌────────────┬────────────┬────────────┬────────┬─────────────────┬──────────┐
│ Total Rows │ Successful │ Duplicates │ Errors │ Unknown Tickers │ Duration │
├────────────┼────────────┼────────────┼────────┼─────────────────┼──────────┤
│          6 │          3 │          0 │      3 │               3 │     3.2s │
└────────────┴────────────┴────────────┴────────┴─────────────────┴──────────┘

⚠ Unknown Tickers Requiring Review (Batch ID: 123)
┌─────┬────────┬────────────────────────┬──────────────────────┐
│ Row │ Ticker │ Suggestions            │ Transaction          │
├─────┼────────┼────────────────────────┼──────────────────────┤
│   2 │ APPL   │ AAPL, APL              │ Buy 5 @ $150.00 USD  │
│   4 │ XYZZ   │ (none)                 │ Buy 15 @ $25.00 USD  │
│   5 │ TKM1T  │ TKM1T.TL (Tallinn .TL) │ Buy 20 @ $8.50 EUR   │
└─────┴────────┴────────────────────────┴──────────────────────┘

To review and correct: stocks-helper import review-tickers 123
Import status: needs_review
```

**Step 1: Review Unknown Tickers**
```bash
stocks-helper import review-tickers 123
```

**Expected**: Same table as above with instructions for correction

**Step 2: Correct Typo (APPL → AAPL)**
```bash
# Fix typo: APPL should be AAPL
stocks-helper import correct-ticker 123 2 AAPL
```

**Expected Output**:
```
✓ Validating ticker AAPL... valid
✓ Corrected 1 rows to AAPL
✓ Imported 1 transaction

Remaining errors: 2 (unknown tickers: 2)
```

**Verification**:
```bash
# Check transaction imported with corrected ticker
stocks-helper transactions list --reference OR-TYPO001
```

**Expected**: Shows transaction with ticker "AAPL", quantity 5

**Step 3: Correct Regional Ticker (TKM1T → TKM1T.TL with .TL suffix)**
```bash
# TKM1T.TL is valid ticker on Yahoo Finance (Tallinn Stock Exchange)
# System auto-detected the suffix, now apply the suggestion
stocks-helper import correct-ticker 123 5 TKM1T.TL
```

**Expected Output**:
```
✓ Validating ticker TKM1T.TL... valid (Yahoo Finance)
✓ Corrected 1 rows to TKM1T.TL
✓ Imported 1 transaction

Remaining errors: 1 (unknown tickers: 1)
```

**Verification**:
```bash
# Check TKM1T.TL imported with correct suffix
stocks-helper transactions list --reference OR-REGIONAL001
```

**Expected**: Shows transaction with ticker "TKM1T.TL", quantity 20

**Step 4: Delete Invalid Ticker (XYZZ - Invalid)**
```bash
# XYZZ is not a real ticker, delete this row
stocks-helper import delete-rows 123 4
```

**Expected Output**:
```
✓ Deleted 1 error row

Remaining errors: 0
Import batch 123 status: completed
```

**Final Verification**:
```bash
# Check all transactions from batch
stocks-helper transactions list --batch 123 --count

# Check import history
stocks-helper import history --limit 1
```

**Expected**:
- 5 transactions imported (3 valid initially + 2 corrected: APPL→AAPL, TKM1T→TKM1T.TL)
- 1 row deleted (XYZZ)
- Batch status: completed
- Breakdown: 3 successful, 2 corrected (typo + suffix), 1 deleted

**Cleanup**:
```bash
rm /tmp/unknown_tickers_test.csv
```

---

## Success Criteria

All scenarios must pass:
- ✅ Scenario 1: First import succeeds, all rows imported
- ✅ Scenario 2: Re-import detects duplicates, no new rows added
- ✅ Scenario 3: Lightyear format parsed correctly, multi-currency support works
- ✅ Scenario 4: Partial import succeeds, errors reported for manual intervention
- ✅ Scenario 5: Dry run validates without database changes
- ✅ Scenario 6: Negative holdings allowed without error
- ✅ Scenario 7: Performance meets target (< 30s for 10k rows)
- ✅ Scenario 8: Unknown tickers detected, manual correction workflow successful

## Cleanup
```bash
# Remove test CSV files
rm /tmp/invalid_test.csv /tmp/short_position_test.csv /tmp/unknown_tickers_test.csv

# Reset database to clean state (optional)
stocks-helper db reset --confirm
```

## Troubleshooting

### Import fails with "FileNotFoundError"
- Verify CSV file exists at specified path
- Check file permissions (must be readable)

### Import fails with "CSVParseError: invalid delimiter"
- Verify broker type matches CSV format (Swedbank uses `;`, Lightyear uses `,`)
- Check file encoding (must be UTF-8)

### Validation errors on all rows
- Verify CSV has correct headers (check against contracts/csv_parser.py)
- Check date format matches broker (DD.MM.YYYY for Swedbank, DD/MM/YYYY HH:MM:SS for Lightyear)

### Performance slower than expected
- Check database indexes exist: `broker_source + broker_reference_id`
- Profile with: `python -m cProfile -o import.prof stocks-helper import csv ...`
- Verify not running in debug mode

### Duplicate detection not working
- Verify `broker_reference_id` field populated in transactions
- Check composite index exists: `CREATE UNIQUE INDEX idx_transactions_broker_ref ON transactions(broker_source, broker_reference_id)`
- Query database: `SELECT broker_reference_id FROM transactions WHERE broker_reference_id IS NOT NULL LIMIT 10`

## Next Steps

After all quickstart scenarios pass:
1. Run full test suite: `pytest tests/`
2. Run contract tests: `pytest tests/contract/ -v`
3. Run integration tests: `pytest tests/integration/ -v`
4. Check code coverage: `pytest --cov=src --cov-report=html`
5. Review generated artifacts in `specs/002-bulk-transaction-import/`
