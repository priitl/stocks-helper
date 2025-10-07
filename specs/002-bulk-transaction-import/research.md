# Phase 0: Technical Research - Bulk Transaction Import

## Research Questions & Decisions

### 1. CSV Parsing Strategy with pandas

**Question**: How to handle multiple delimiters, encodings, and decimal separators with pandas?

**Research**:
- pandas `read_csv()` supports delimiter parameter (`,` or `;`)
- encoding parameter handles UTF-8 with Estonian characters
- `decimal` parameter converts comma separators ("135,00" → 135.00)
- `parse_dates` with custom format strings for DD.MM.YYYY and DD/MM/YYYY

**Decision**: Use pandas read_csv with broker-specific configurations
```python
# Swedbank config
pd.read_csv(
    filepath,
    delimiter=';',
    encoding='utf-8',
    decimal=',',
    parse_dates=['Kuupäev'],
    dayfirst=True
)

# Lightyear config
pd.read_csv(
    filepath,
    delimiter=',',
    encoding='utf-8',
    parse_dates=['Date'],
    date_format='%d/%m/%Y %H:%M:%S'
)
```

**Rationale**:
- Native pandas features avoid custom parsing logic
- Well-tested library handles edge cases
- Configuration-based approach makes broker differences explicit

**Alternatives Considered**:
- ❌ Python csv module: Requires manual type conversion, date parsing
- ❌ Custom parser: Reinventing pandas, higher bug risk

### 2. Swedbank Description Field Parsing

**Question**: How to reliably extract ticker, quantity, price from Swedbank "Selgitus" field patterns?

**Research**: Examined sample data from research/swed_*.csv files:
- Buy pattern: `TICKER +quantity@price/SE:reference EXCHANGE`
  - Example: `LHV1T +10@13.5/SE:4100088 TSE`
- Sell pattern: `TICKER -quantity@price/SE:reference EXCHANGE`
  - Example: `CPA1T -60@1.804/SE:2173825 TSE`
- Dividend pattern: `'/reference/ ISIN COMPANY_NAME dividend X EUR, tulumaks Y EUR`
  - Example: `'/212759/ EE0000001105 TALLINNA KAUBAMAJA GRUPP AKTSIA dividend 5.53 EUR, tulumaks 0.00 EUR`
- Fee pattern: `K: TICKER +quantity@price/SE:reference EXCHANGE`
  - Example: `K: IWDA-NA +35@55.04/SE:01V!4B3H0000OS000001 SWEDBANK`

**Decision**: Use regex patterns with named capture groups
```python
BUY_SELL_PATTERN = r'(?P<ticker>[A-Z0-9\-]+)\s+(?P<sign>[+-])(?P<quantity>[\d.]+)@(?P<price>[\d.]+)/SE:(?P<reference>\S+)\s+(?P<exchange>\w+)'
DIVIDEND_PATTERN = r"'/(?P<reference>\d+)/ (?P<isin>[A-Z]{2}\d+) (?P<company>.+?) dividend (?P<gross>[\d.]+) EUR, tulumaks (?P<tax>[\d.]+) EUR"
FEE_PATTERN = r'K:\s+' + BUY_SELL_PATTERN
```

**Rationale**:
- Named groups make code self-documenting
- Patterns derived from actual data samples
- Easy to test against research CSV samples

**Alternatives Considered**:
- ❌ String splitting: Fragile, doesn't handle variations (e.g., spaces in ticker)
- ❌ Manual parsing: More code, harder to maintain

### 3. Date Format Handling

**Question**: How to consistently convert Estonian DD.MM.YYYY and English DD/MM/YYYY HH:MM:SS to Python datetime?

**Decision**: Use pandas parse_dates with dayfirst=True for both formats
```python
# Swedbank: DD.MM.YYYY
df['Kuupäev'] = pd.to_datetime(df['Kuupäev'], format='%d.%m.%Y', dayfirst=True)

# Lightyear: DD/MM/YYYY HH:MM:SS
df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y %H:%M:%S', dayfirst=True)
```

**Rationale**:
- dayfirst=True ensures 01/02/2024 → Feb 1 not Jan 2
- Explicit format strings avoid ambiguity
- pandas handles timezone-naive datetimes consistently

**Alternatives Considered**:
- ❌ Python datetime.strptime: More verbose, no DataFrame integration
- ❌ dateutil.parser: Too flexible, can misinterpret formats

### 4. Duplicate Detection Strategy

**Question**: Efficient lookup for broker reference IDs in existing database?

**Research**:
- SQLAlchemy indexed queries: O(log n) lookup with index on broker_reference_id
- Bulk query: Load all existing reference IDs for broker into set, O(1) membership test
- Database size: ~10k transactions expected, set fits in memory

**Decision**: Bulk load + set membership test
```python
existing_refs = set(
    session.query(Transaction.broker_reference_id)
    .filter(Transaction.broker == broker_type)
    .all()
)

for row in parsed_rows:
    if row.broker_reference_id in existing_refs:
        duplicate_count += 1
        continue
    # import row
```

**Rationale**:
- O(1) lookup per row after initial O(n) load
- Single database query vs thousands of individual lookups
- Memory efficient: ~100 bytes × 10k = ~1MB

**Alternatives Considered**:
- ❌ Per-row database query: N queries = slow for large imports
- ❌ Database UNIQUE constraint: Raises exception, requires transaction rollback

### 5. Validation Rules Per Transaction Type

**Question**: What makes each transaction type valid?

**Decision**: Transaction-type-specific validators using pydantic
```python
class BuySellValidator:
    required_fields = ['ticker', 'quantity', 'price', 'currency']
    quantity_must_be_positive = True
    price_must_be_positive = True

class DividendValidator:
    required_fields = ['ticker', 'amount', 'currency']
    quantity_optional = True  # Dividend on holdings
    price_not_required = True

class WithdrawalValidator:
    required_fields = ['amount', 'currency']
    ticker_not_required = True
    negative_amount_allowed = True  # Withdrawal = outflow
```

**Rationale**:
- Each transaction type has different required fields
- Validators document business rules explicitly
- pydantic provides clear error messages with field names

**Alternatives Considered**:
- ❌ Single validator with conditional logic: Hard to test, unclear rules
- ❌ Database constraints only: Errors not user-friendly

### 6. CSV File Size Limits

**Question**: Practical memory limits for pandas read_csv?

**Research**:
- pandas read_csv with default settings: ~5x file size in memory
- 10MB CSV file → ~50MB memory usage
- 50,000 rows × 12 columns × ~50 bytes/cell ≈ 30MB file → 150MB memory
- Target: Support up to 100MB CSV files (300k+ rows)

**Decision**: Use chunked reading for files > 50MB
```python
if file_size_mb > 50:
    chunks = pd.read_csv(filepath, chunksize=10000, **config)
    for chunk in chunks:
        process_chunk(chunk)
else:
    df = pd.read_csv(filepath, **config)
    process_dataframe(df)
```

**Rationale**:
- Most CSV files < 50MB, no chunking overhead
- Large files processed incrementally, bounded memory
- 10k row chunks = ~5MB memory per chunk

**Alternatives Considered**:
- ❌ Always chunk: Unnecessary complexity for small files
- ❌ No limit: Risk of OOM on large imports

### 7. Decimal Separator Handling

**Question**: Convert Estonian comma separator consistently?

**Decision**: Use pandas decimal parameter per broker
```python
# Swedbank: comma decimal separator
decimal=','  # "135,00" → 135.0

# Lightyear: dot decimal separator
decimal='.'  # "135.00" → 135.0
```

**Rationale**:
- pandas handles conversion natively
- No manual string replacement needed
- Preserves numeric precision

**Alternatives Considered**:
- ❌ String replace: Error-prone (e.g., thousands separator)
- ❌ Locale-based: Requires system locale configuration

## Technology Stack Decisions

### Core Libraries
- **pandas 2.3.3**: CSV parsing, data transformation
- **SQLAlchemy 2.0.43**: Database ORM, transaction management
- **pydantic 2.10.3**: Data validation, schema enforcement

### Why These Libraries?
- All already project dependencies (no new dependencies)
- pandas: Industry-standard CSV handling, battle-tested
- SQLAlchemy: Existing ORM in project, consistent with current models
- pydantic: Type-safe validation, clear error messages

### Testing Strategy
- **Contract tests**: Parse sample CSV files from research/ directory
- **Unit tests**: Test parsers, validators in isolation with mock data
- **Integration tests**: Full import workflow with test database
- **Property tests**: Random valid/invalid CSV data generation

## Implementation Patterns

### Parser Pattern
```python
class CSVParser(ABC):
    """Base class for broker-specific CSV parsers."""

    @abstractmethod
    def parse(self, filepath: Path) -> Iterator[ParsedTransaction]:
        """Parse CSV file, yield validated transactions."""
        pass

    def _validate_row(self, row: dict) -> ParsedTransaction:
        """Convert CSV row to pydantic model, validate."""
        pass

class SwedbankCSVParser(CSVParser):
    def parse(self, filepath: Path) -> Iterator[ParsedTransaction]:
        df = pd.read_csv(filepath, delimiter=';', decimal=',', ...)
        for idx, row in df.iterrows():
            try:
                yield self._parse_swedbank_row(row)
            except ValidationError as e:
                raise CSVParseError(row_number=idx+1, reason=str(e))
```

**Rationale**:
- Inheritance for shared validation logic
- Iterator pattern for memory efficiency
- Explicit exception handling at row level

### Service Pattern
```python
class ImportService:
    def __init__(self, session: Session):
        self.session = session
        self.parsers = {
            'swedbank': SwedbankCSVParser(),
            'lightyear': LightyearCSVParser()
        }

    def import_csv(self, filepath: Path, broker: str) -> ImportSummary:
        parser = self.parsers[broker]
        batch = ImportBatch(broker=broker, filename=filepath.name)

        existing_refs = self._load_existing_references(broker)

        for transaction in parser.parse(filepath):
            if transaction.broker_reference_id in existing_refs:
                batch.duplicate_count += 1
                continue

            try:
                self._import_transaction(transaction, batch)
                batch.successful_count += 1
            except ValidationError as e:
                batch.errors.append(ImportError(row=..., reason=str(e)))

        self.session.commit()
        return ImportSummary.from_batch(batch)
```

**Rationale**:
- Service orchestrates workflow
- Parser selection via strategy pattern
- Transaction management at service layer

## Risk Mitigation

### Risk: Regex patterns fail on unseen transaction formats
**Mitigation**: Comprehensive contract tests with all CSV samples, log unparseable rows for review

### Risk: Memory usage spikes on large CSV files
**Mitigation**: Chunked reading for files > 50MB, profile memory usage in integration tests

### Risk: Duplicate detection misses variations
**Mitigation**: Use broker reference ID (unique per broker), test with real duplicate scenarios

### Risk: Validation too strict, rejects valid transactions
**Mitigation**: Validation rules derived from spec requirements, manual intervention workflow for edge cases

## Performance Baseline

**Target**: Import 10,000 transactions in < 30 seconds

**Estimated Breakdown**:
- CSV parsing (pandas): ~1-2 seconds for 10k rows
- Duplicate detection: ~0.5 seconds (set lookup)
- Validation: ~2-3 seconds (pydantic per row)
- Database insertion: ~5-10 seconds (bulk insert 10k rows)
- **Total**: ~10-15 seconds (50% margin for safety)

**Monitoring**: Track import_batch.processing_duration, alert if > 30s

### 8. Ticker Validation Strategy

**Question**: How to handle unknown tickers (not found in market data APIs) during import?

**Research**:
- Edge case from spec (line 67): "What if a CSV contains transactions for tickers not yet in the system?"
- Scenarios:
  - Typos: "APPL" instead of "AAPL" (user error)
  - Regional exchanges: "TKM1T" (Tallinn exchange, not in Yahoo Finance/Alpha Vantage)
  - Delisted stocks: Historical transactions for stocks no longer trading
  - Invalid entries: Account transfers misidentified as stock transactions
- API lookup cost: ~100-200ms per ticker, but can batch unique tickers
- Risk: Importing invalid tickers breaks portfolio calculations later

**Decision**: Validate unique tickers during import, flag unknowns for manual review
```python
# Collect unique tickers from import batch
unique_tickers = set(t.ticker for t in parsed_transactions if t.ticker)

# Validate in parallel (async)
validation_results = await asyncio.gather(
    *[ticker_validator.validate_ticker(t) for t in unique_tickers]
)

# Categorize results
unknown_tickers = [v for v in validation_results if not v.valid]

# If unknowns found, add to import summary for manual intervention
if unknown_tickers:
    import_summary.unknown_ticker_count = len(unknown_tickers)
    import_summary.requires_ticker_review = True
```

**Rationale**:
- Validate during import = immediate user feedback (better UX)
- Only validate unique tickers = O(unique) not O(rows), typically 10-20 unique in 100+ row file
- Parallel validation = fast (~1-2s for 20 tickers)
- Fuzzy matching for typos = helpful suggestions ("Did you mean AAPL?")
- Keep as-is option = supports regional exchanges not in our APIs

**Alternatives Considered**:
- ❌ Validate after import: User discovers issues later, harder to fix
- ❌ Block import on unknown tickers: Too strict, rejects valid regional tickers
- ❌ Skip validation entirely: Portfolio calculations fail unexpectedly

**Exchange Suffix Auto-Detection**:
```python
# Common exchange suffixes for regional markets
EXCHANGE_SUFFIXES = {
    'TL': 'Tallinn Stock Exchange',
    'HE': 'Helsinki Stock Exchange',
    'ST': 'Stockholm Stock Exchange',
    'CO': 'Copenhagen Stock Exchange',
    'OL': 'Oslo Stock Exchange',
    'IC': 'Iceland Stock Exchange',
    'L': 'London Stock Exchange',
    'DE': 'XETRA (Germany)',
    'PA': 'Paris Euronext',
    'AS': 'Amsterdam Euronext',
}

async def validate_ticker_with_suffix_detection(ticker: str) -> TickerValidationResult:
    """
    Validate ticker, auto-detecting exchange suffix if needed.

    Strategy:
    1. Try exact ticker first (e.g., "AAPL")
    2. If not found, try with common suffixes (e.g., "TKM1T" → "TKM1T.TL")
    3. Return valid ticker with suffix if found
    """
    # Try exact ticker
    if await market_data_api.ticker_exists(ticker):
        return TickerValidationResult(ticker=ticker, valid=True, ...)

    # Try with exchange suffixes (for regional tickers)
    for suffix, exchange_name in EXCHANGE_SUFFIXES.items():
        suffixed_ticker = f"{ticker}.{suffix}"
        if await market_data_api.ticker_exists(suffixed_ticker):
            return TickerValidationResult(
                ticker=ticker,  # Original from CSV
                valid=False,  # Original not found, but we found alternative
                suggestions=[suffixed_ticker],
                confidence=['high'],
                validation_source=f'suffix_detected_{exchange_name}'
            )

    # Not found, try fuzzy matching
    suggestions = fuzzy_match_ticker(ticker)
    return TickerValidationResult(ticker=ticker, valid=False, suggestions=suggestions, ...)
```

**Fuzzy Matching Strategy** (fallback after suffix detection):
```python
def fuzzy_match_ticker(ticker: str, threshold: int = 2) -> List[str]:
    """
    Find similar tickers using Levenshtein distance.
    threshold: max character differences (default 2 for typos)
    """
    # Compare against cached known tickers from previous validations
    candidates = []
    for known in known_tickers_cache:
        distance = levenshtein_distance(ticker, known)
        if distance <= threshold:
            candidates.append((known, distance))

    # Return top 3 matches, sorted by distance
    return [t for t, d in sorted(candidates, key=lambda x: x[1])[:3]]
```

**Performance Impact**:
- Unique ticker extraction: O(n) = ~0.1s for 10k rows
- API validation (exact): O(unique) × 200ms = ~2-4s for 20 unique tickers (parallel)
- Exchange suffix detection: O(unique × 10 suffixes) × 200ms = ~2-4s (only for not-found tickers, parallel)
- Fuzzy matching: O(unique × cache_size) = ~0.01s (small cache)
- **Total overhead**: ~4-8s per import (acceptable for better UX)
- **Optimization**: Cache suffix detection results (TKM1T → TKM1T.TL cached for future imports)

## Open Questions Resolved

All NEEDS CLARIFICATION items from plan.md resolved:
- ✅ CSV parsing strategy: pandas with broker-specific configs
- ✅ Swedbank description parsing: Regex patterns with named groups
- ✅ Date format handling: pandas parse_dates with dayfirst=True
- ✅ Duplicate detection: Bulk load + set membership
- ✅ Validation rules: Transaction-type-specific validators
- ✅ File size limits: Chunked reading for > 50MB
- ✅ Decimal separators: pandas decimal parameter
- ✅ Unknown ticker handling: Validate during import, manual intervention for unknowns

Ready to proceed to Phase 1: Design & Contracts
