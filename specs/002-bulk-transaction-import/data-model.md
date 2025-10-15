# Data Model: Bulk Transaction Import

## Entity Relationship Diagram

```
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│   ImportBatch    │1       *│   Transaction    │         │   ImportError    │
│──────────────────│◄────────│──────────────────│         │──────────────────│
│ id               │         │ id               │         │ id               │
│ filename         │         │ date             │         │ import_batch_id  │
│ broker_type      │         │ ticker           │         │ row_number       │
│ upload_timestamp │         │ quantity         │         │ error_type       │
│ total_rows       │         │ price            │         │ error_message    │
│ successful_count │         │ fees             │         │ original_row_data│
│ duplicate_count  │         │ transaction_type │         │ suggested_fix    │
│ error_count      │         │ currency         │         └──────────────────┘
│ unknown_ticker_ct│         │ broker_reference │                │
│ status           │         │ import_batch_id  │                │
│ processing_dur   │         │ broker_source    │                │
└──────────────────┘         └──────────────────┘                │
         │                            ▲                           │
         │                            │                           │
         └────────────────────────────┴───────────────────────────┘
                                1 : *
```

## Entities

### 1. ImportBatch (NEW)

**Purpose**: Track import session metadata, provide audit trail for bulk imports

**Fields**:
```python
class ImportBatch:
    id: int                          # Primary key
    filename: str                    # Original CSV filename
    broker_type: str                 # 'swedbank' or 'lightyear'
    upload_timestamp: datetime       # When import started
    total_rows: int                  # Total rows in CSV (excluding header)
    successful_count: int            # Successfully imported transactions
    duplicate_count: int             # Skipped duplicate transactions
    error_count: int                 # Rows with validation errors
    unknown_ticker_count: int        # Rows with unrecognized tickers (subset of error_count)
    status: str                      # 'pending', 'processing', 'completed', 'failed', 'needs_review'
    processing_duration: float       # Import duration in seconds
    user_id: str | None              # Optional: who triggered import
```

**Validation Rules**:
- `broker_type` must be in ['swedbank', 'lightyear']
- `status` must be in ['pending', 'processing', 'completed', 'failed', 'needs_review']
- `successful_count + duplicate_count + error_count = total_rows`
- `unknown_ticker_count <= error_count` (unknown tickers are a subset of errors)
- `processing_duration >= 0`
- `upload_timestamp` must be <= current time
- `status = 'needs_review'` when `unknown_ticker_count > 0` (requires manual ticker correction)

**State Transitions**:
```
pending → processing → completed (all rows imported successfully)
                    ├→ needs_review (unknown tickers detected, manual intervention required)
                    └→ failed (on unrecoverable error: file corrupt, database error)
```

**Indexes**:
- Primary key on `id`
- Index on `upload_timestamp` (for chronological queries)
- Index on `broker_type` (for broker-specific queries)

**Relationships**:
- One-to-many with Transaction (cascade delete)
- One-to-many with ImportError (cascade delete)

### 2. Transaction (MODIFIED)

**Purpose**: Store individual financial transactions from broker accounts

**New Fields**:
```python
# Existing fields (preserved):
# id, date, ticker, quantity, price, fees, transaction_type, currency

# NEW fields:
broker_reference_id: str             # Unique ID from broker (e.g., "2020100600247429", "OR-SNFM7WJGX2")
import_batch_id: int | None          # Foreign key to ImportBatch (NULL for manual entries)
broker_source: str | None            # 'swedbank', 'lightyear', or NULL for manual
```

**Validation Rules**:
- `broker_reference_id` must be unique per broker_source
- `import_batch_id` must reference valid ImportBatch.id if not NULL
- `broker_source` must be in ['swedbank', 'lightyear'] if not NULL
- All existing validation rules preserved

**Indexes**:
- Existing: Primary key on `id`, index on `date`
- NEW: Composite unique index on (`broker_source`, `broker_reference_id`)
  - Allows efficient duplicate detection
  - Enforces uniqueness per broker

**Relationships**:
- Many-to-one with ImportBatch (optional, NULL for manual entries)
- Existing relationships preserved (Portfolio, Holding, etc.)

**Migration Considerations**:
- Existing transactions: `broker_reference_id` will be NULL, `import_batch_id` will be NULL
- New transactions: Both fields populated during import
- No data loss, backward compatible

### 3. ImportError (NEW)

**Purpose**: Track validation failures for manual intervention

**Fields**:
```python
class ImportError:
    id: int                          # Primary key
    import_batch_id: int             # Foreign key to ImportBatch
    row_number: int                  # CSV row number (1-indexed, excluding header)
    error_type: str                  # Error category: 'parse', 'validation', 'unknown_ticker'
    error_message: str               # Detailed error description
    original_row_data: dict          # JSON: original CSV row for manual review
    suggested_fix: str | None        # JSON: suggested corrections (for unknown_ticker: fuzzy matches)
```

**Validation Rules**:
- `import_batch_id` must reference valid ImportBatch.id
- `row_number >= 1`
- `error_type` must be in ['parse', 'validation', 'unknown_ticker', 'missing_required_field', 'invalid_format']
- `original_row_data` must be valid JSON
- `suggested_fix` is JSON when error_type='unknown_ticker': `{"suggestions": ["AAPL", "APLE"], "confidence": ["high", "low"]}`

**Indexes**:
- Primary key on `id`
- Index on `import_batch_id` (for batch error queries)

**Relationships**:
- Many-to-one with ImportBatch

**Usage**:
```python
# Example validation error
ImportError(
    import_batch_id=123,
    row_number=45,
    error_type='validation',
    error_message='Invalid quantity: expected positive number, got "-10.5"',
    original_row_data={'Kuupäev': '01.10.2020', 'Selgitus': '...', 'Summa': '-10.5', ...},
    suggested_fix=None
)

# Example unknown ticker error with fuzzy match suggestions
ImportError(
    import_batch_id=123,
    row_number=67,
    error_type='unknown_ticker',
    error_message='Ticker "APPL" not found in market data APIs',
    original_row_data={'Date': '01/10/2025', 'Ticker': 'APPL', 'Type': 'Buy', ...},
    suggested_fix='{"suggestions": ["AAPL", "APL"], "confidence": ["high", "low"]}'
)
```

### 4. CSV Row Schemas (Pydantic Models)

**Purpose**: Type-safe CSV parsing with validation

#### SwedbankCSVRow
```python
class SwedbankCSVRow(BaseModel):
    """Pydantic model for Swedbank CSV row validation."""

    kliendi_konto: str                    # Account number (not imported)
    rea_tyup: str                         # Transaction type code
    kuupaev: date                         # Transaction date
    saaja_maksja: str                     # Payer/recipient
    selgitus: str                         # Description (parsed for transaction details)
    summa: Decimal                        # Amount
    valuuta: str                          # Currency code
    deebet_kreedit: str                   # D (debit) or K (credit)
    arhiveerimistunnus: str               # Archive reference (broker reference ID)
    tehingu_tyup: str                     # Transaction type
    viitenumber: str                      # Reference number (optional)
    dokumendi_number: str                 # Document number (optional)

    @field_validator('summa')
    def validate_amount(cls, v):
        if v == 0:
            raise ValueError('Amount cannot be zero')
        return v

    @field_validator('valuuta')
    def validate_currency(cls, v):
        if v not in ['EUR', 'USD', 'GBP']:
            raise ValueError(f'Unsupported currency: {v}')
        return v
```

#### LightyearCSVRow
```python
class LightyearCSVRow(BaseModel):
    """Pydantic model for Lightyear CSV row validation."""

    date: datetime                        # Transaction date with time
    reference: str                        # Broker reference ID
    ticker: str | None                    # Stock ticker (optional for some transaction types)
    isin: str | None                      # ISIN (optional)
    type: str                             # Transaction type
    quantity: Decimal | None              # Quantity (optional for dividends, deposits)
    ccy: str                              # Currency code
    price_per_share: Decimal | None       # Price (optional for non-trade transactions)
    gross_amount: Decimal | None          # Gross amount
    fx_rate: Decimal | None               # FX rate (optional)
    fee: Decimal                          # Transaction fee
    net_amt: Decimal                      # Net amount after fees/taxes
    tax_amt: Decimal | None               # Tax amount (optional)

    @field_validator('type')
    def validate_type(cls, v):
        valid_types = ['Buy', 'Sell', 'Dividend', 'Distribution', 'Deposit',
                      'Withdrawal', 'Conversion', 'Interest', 'Reward']
        if v not in valid_types:
            raise ValueError(f'Invalid transaction type: {v}')
        return v

    @field_validator('ccy')
    def validate_currency(cls, v):
        if v not in ['EUR', 'USD', 'GBP']:
            raise ValueError(f'Unsupported currency: {v}')
        return v
```

#### ParsedTransaction
```python
class ParsedTransaction(BaseModel):
    """Unified transaction model after parsing (used by import service)."""

    date: datetime
    ticker: str | None                    # NULL for deposits, withdrawals
    quantity: Decimal | None              # NULL for non-trade transactions
    price: Decimal | None                 # NULL for non-trade transactions
    fees: Decimal
    transaction_type: str                 # Normalized: 'buy', 'sell', 'dividend', etc.
    currency: str
    broker_reference_id: str              # Unique ID from broker
    broker_source: str                    # 'swedbank' or 'lightyear'
    net_amount: Decimal                   # Net amount after fees/taxes
    tax_amount: Decimal | None            # Tax withheld (NULL if not applicable)
    original_data: dict                   # Original CSV row for audit

    @field_validator('transaction_type')
    def validate_transaction_type(cls, v):
        valid_types = ['buy', 'sell', 'dividend', 'distribution', 'deposit',
                      'withdrawal', 'conversion', 'interest', 'reward', 'fee']
        if v not in valid_types:
            raise ValueError(f'Invalid normalized transaction type: {v}')
        return v

    @validator('quantity')
    def validate_quantity_for_type(cls, v, values):
        # Buy/Sell require quantity
        if values.get('transaction_type') in ['buy', 'sell'] and v is None:
            raise ValueError('Quantity required for buy/sell transactions')
        return v
```

### 5. TickerValidationResult (Runtime Model - not persisted)

**Purpose**: In-memory representation of ticker validation results during import

**Fields**:
```python
@dataclass
class TickerValidationResult:
    ticker: str                      # Ticker being validated
    valid: bool                      # True if found in market data APIs
    suggestions: List[str]           # Fuzzy match suggestions for typos (empty if valid)
    confidence: List[str]            # Confidence levels: 'high', 'medium', 'low' (parallel to suggestions)
    validation_source: str           # Which API validated: 'yahoo_finance', 'alpha_vantage', 'cache'
```

**Usage**:
```python
# Valid ticker (found in API)
TickerValidationResult(
    ticker='AAPL',
    valid=True,
    suggestions=[],
    confidence=[],
    validation_source='yahoo_finance'
)

# Invalid ticker with typo suggestions (fuzzy match)
TickerValidationResult(
    ticker='APPL',  # Typo
    valid=False,
    suggestions=['AAPL', 'APL'],
    confidence=['high', 'low'],
    validation_source='fuzzy_match'
)

# Regional ticker with exchange suffix detected
TickerValidationResult(
    ticker='TKM1T',  # Missing .TL suffix
    valid=False,
    suggestions=['TKM1T.TL'],
    confidence=['high'],
    validation_source='suffix_detected_Tallinn Stock Exchange'
)

# Unknown ticker, no suggestions
TickerValidationResult(
    ticker='XYZZ',
    valid=False,
    suggestions=[],
    confidence=[],
    validation_source='not_found'
)
```

**Note**: This is a runtime model, not persisted to database. Results are stored in `ImportError.suggested_fix` as JSON for unknown tickers.

## Database Schema Changes

### New Tables

#### import_batches
```sql
CREATE TABLE import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    broker_type TEXT NOT NULL CHECK(broker_type IN ('swedbank', 'lightyear')),
    upload_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_rows INTEGER NOT NULL CHECK(total_rows >= 0),
    successful_count INTEGER NOT NULL DEFAULT 0 CHECK(successful_count >= 0),
    duplicate_count INTEGER NOT NULL DEFAULT 0 CHECK(duplicate_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK(error_count >= 0),
    unknown_ticker_count INTEGER NOT NULL DEFAULT 0 CHECK(unknown_ticker_count >= 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'failed', 'needs_review')),
    processing_duration REAL CHECK(processing_duration IS NULL OR processing_duration >= 0),
    user_id TEXT,
    CHECK(successful_count + duplicate_count + error_count = total_rows),
    CHECK(unknown_ticker_count <= error_count)
);

CREATE INDEX idx_import_batches_timestamp ON import_batches(upload_timestamp);
CREATE INDEX idx_import_batches_broker ON import_batches(broker_type);
CREATE INDEX idx_import_batches_status ON import_batches(status);
```

#### import_errors
```sql
CREATE TABLE import_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER NOT NULL,
    row_number INTEGER NOT NULL CHECK(row_number >= 1),
    error_type TEXT NOT NULL CHECK(error_type IN ('parse', 'validation', 'unknown_ticker', 'missing_required_field', 'invalid_format')),
    error_message TEXT NOT NULL,
    original_row_data TEXT NOT NULL,  -- JSON
    suggested_fix TEXT,  -- JSON (for unknown_ticker: fuzzy match suggestions)
    FOREIGN KEY (import_batch_id) REFERENCES import_batches(id) ON DELETE CASCADE
);

CREATE INDEX idx_import_errors_batch ON import_errors(import_batch_id);
CREATE INDEX idx_import_errors_type ON import_errors(error_type);
```

### Modified Tables

#### transactions (add columns)
```sql
ALTER TABLE transactions ADD COLUMN broker_reference_id TEXT;
ALTER TABLE transactions ADD COLUMN import_batch_id INTEGER REFERENCES import_batches(id) ON DELETE SET NULL;
ALTER TABLE transactions ADD COLUMN broker_source TEXT CHECK(broker_source IS NULL OR broker_source IN ('swedbank', 'lightyear'));

CREATE UNIQUE INDEX idx_transactions_broker_ref ON transactions(broker_source, broker_reference_id)
WHERE broker_reference_id IS NOT NULL;
```

## Data Flow

### Import Workflow
```
1. CSV File
   ↓
2. pandas read_csv (broker-specific config)
   ↓
3. DataFrame → Iterator[CSVRow] (pydantic validation)
   ↓
4. CSVRow → ParsedTransaction (normalization)
   ↓
5. Duplicate Detection (check broker_reference_id in existing transactions)
   ↓ (if not duplicate)
6. Transaction Model (SQLAlchemy ORM)
   ↓
7. Database INSERT (with import_batch_id foreign key)
```

### Error Handling
```
Validation Error (pydantic) → ImportError record + continue
Parse Error (pandas) → ImportError record + continue
Duplicate (reference ID exists) → Increment duplicate_count + skip
Database Error → Rollback transaction + mark batch as 'failed'
```

## Query Patterns

### Get Import Summary
```python
batch = session.query(ImportBatch).filter_by(id=batch_id).first()
summary = {
    'total': batch.total_rows,
    'successful': batch.successful_count,
    'duplicates': batch.duplicate_count,
    'errors': batch.error_count,
    'duration': batch.processing_duration
}
```

### Get Errors for Manual Review
```python
errors = (
    session.query(ImportError)
    .filter_by(import_batch_id=batch_id)
    .all()
)
for error in errors:
    print(f"Row {error.row_number}: {error.error_message}")
    print(f"Original data: {error.original_row_data}")
```

### Check for Duplicate Before Import
```python
exists = (
    session.query(Transaction.id)
    .filter_by(
        broker_source='swedbank',
        broker_reference_id='2020100600247429'
    )
    .first()
) is not None
```

### Get All Transactions from Import Batch
```python
transactions = (
    session.query(Transaction)
    .filter_by(import_batch_id=batch_id)
    .order_by(Transaction.date)
    .all()
)
```

## Performance Considerations

### Bulk Insert Optimization
```python
# Use bulk_insert_mappings for large imports
session.bulk_insert_mappings(
    Transaction,
    [t.dict() for t in parsed_transactions],
    return_defaults=False  # Skip ID retrieval for speed
)
```

### Index Strategy
- Composite index on (broker_source, broker_reference_id) for O(log n) duplicate detection
- Index on import_batch_id for fast batch queries
- Index on upload_timestamp for chronological import history

### Memory Management
- Use iterator pattern for CSV parsing (yield rows, don't load entire DataFrame)
- Batch database inserts (commit every 1000 rows)
- Clear pandas DataFrame after parsing to free memory

## Testing Strategy

### Contract Tests
- Parse each sample CSV file from research/ directory
- Assert expected row count, data types, no parsing errors
- Test: `test_swedbank_csv_contract.py`, `test_lightyear_csv_contract.py`

### Unit Tests
- Pydantic model validation (valid/invalid rows)
- Duplicate detection logic
- Transaction type normalization
- Test: `test_csv_schemas.py`, `test_duplicate_detection.py`

### Integration Tests
- Full import workflow with test database
- Verify transaction count, portfolio updates
- Test duplicate handling, error collection
- Test: `test_import_workflow.py`
