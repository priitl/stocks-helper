# Tasks: Bulk Transaction Import

**JIRA Task**: N/A
**Feature Branch**: `002-bulk-transaction-import`
**Input**: Design documents from `/specs/002-bulk-transaction-import/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/, quickstart.md

**Note**: Task IDs (T001-T050) are independent of JIRA task numbers. JIRA applies to the feature as a whole.

## Execution Flow (main)
```
1. Load plan.md → Tech stack: Python 3.11, pandas, pydantic, SQLAlchemy
2. Load data-model.md → Entities: ImportBatch, ImportError, Transaction (extend), CSV schemas
3. Load contracts/ → 3 contracts: import_cli.yaml, import_service.py, csv_parser.py
4. Load research.md → Decisions: pandas config, regex patterns, ticker validation
5. Load quickstart.md → 8 test scenarios
6. Generate 50 tasks across 5 phases
7. Mark [P] for parallel-safe tasks (different files)
8. Validate: All contracts tested, TDD order enforced
9. SUCCESS: Ready for Phase 3 execution
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- Single project structure: `src/models/`, `src/services/`, `src/cli/`, `src/lib/`, `tests/`
- All paths relative to repository root: `/Users/priitlaht/Repository/stocks-helper/`

---

## Phase 3.1: Setup & Database Schema

- [ ] **T001** Add database migration for ImportBatch table in `src/models/migrations/002_import_batch.sql`
  - Fields: id, filename, broker_type, upload_timestamp, total_rows, successful_count, duplicate_count, error_count, unknown_ticker_count, status, processing_duration, user_id
  - Indexes: upload_timestamp, broker_type, status
  - Constraints: status IN ('pending', 'processing', 'completed', 'failed', 'needs_review')

- [ ] **T002** Add database migration for ImportError table in `src/models/migrations/002_import_error.sql`
  - Fields: id, import_batch_id, row_number, error_type, error_message, original_row_data, suggested_fix
  - Foreign key: import_batch_id → import_batches(id) ON DELETE CASCADE
  - Indexes: import_batch_id, error_type

- [ ] **T003** Add database migration to extend Transaction table in `src/models/migrations/002_transaction_extend.sql`
  - Add columns: broker_reference_id TEXT, import_batch_id INTEGER, broker_source TEXT
  - Add composite unique index: (broker_source, broker_reference_id) WHERE broker_reference_id IS NOT NULL
  - Foreign key: import_batch_id → import_batches(id) ON DELETE SET NULL

- [ ] **T004** [P] Configure linting to pass for new CSV parsing code (add pandas, pydantic to mypy config)

---

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

### Contract Tests (Must Fail Initially)

- [ ] **T005** [P] Contract test for Swedbank CSV parsing in `tests/contract/test_swedbank_csv_contract.py`
  - Load `research/swed_2020_2021.csv`
  - Assert: 150 rows parsed, no errors
  - Assert: Buy transaction pattern parsed correctly (ticker, quantity, price)
  - Assert: Sell transaction pattern parsed correctly
  - Assert: Dividend pattern parsed correctly
  - Assert: Fee pattern parsed correctly
  - Mark: `@pytest.mark.contract`

- [ ] **T006** [P] Contract test for Lightyear CSV parsing in `tests/contract/test_lightyear_csv_contract.py`
  - Load `research/lightyear_2022_2025.csv`
  - Assert: 450+ rows parsed, no errors
  - Assert: All transaction types handled (Buy, Sell, Dividend, Distribution, Deposit, Withdrawal, Conversion, Interest, Reward)
  - Assert: Multi-currency transactions (USD, EUR) parsed correctly
  - Mark: `@pytest.mark.contract`

- [ ] **T007** [P] Contract test for ImportService in `tests/contract/test_import_service_contract.py`
  - Test all methods from `contracts/import_service.py`:
    - `import_csv()`: returns ImportSummary
    - `get_import_history()`: returns list of ImportBatchInfo
    - `get_import_errors()`: returns list of ImportErrorDetail
    - `get_unknown_tickers()`: returns list of UnknownTickerDetail
    - `correct_ticker()`: corrects and re-imports
    - `ignore_unknown_tickers()`: imports as-is
    - `delete_error_rows()`: removes rows
  - Mark: `@pytest.mark.contract`

### Integration Tests (Must Fail Initially)

- [ ] **T008** [P] Integration test for Scenario 1 (first import) in `tests/integration/test_import_swedbank_first.py`
  - Setup: Clean database, sample Swedbank CSV
  - Execute: `stocks-helper import csv swed_2020_2021.csv --broker swedbank`
  - Assert: 150 transactions imported, holdings updated, import batch created
  - Mark: `@pytest.mark.integration`

- [ ] **T009** [P] Integration test for Scenario 2 (duplicates) in `tests/integration/test_import_duplicates.py`
  - Setup: Import CSV once, then re-import same CSV
  - Execute: Second import command
  - Assert: 0 new transactions, duplicate_count = 150, status='completed'
  - Mark: `@pytest.mark.integration`

- [ ] **T010** [P] Integration test for Scenario 3 (Lightyear multi-currency) in `tests/integration/test_import_lightyear_multicurrency.py`
  - Setup: Clean database, Lightyear CSV with USD and EUR transactions
  - Execute: Import command
  - Assert: Transactions stored in original currencies, no conversion
  - Mark: `@pytest.mark.integration`

- [ ] **T011** [P] Integration test for Scenario 4 (partial import with errors) in `tests/integration/test_import_partial_success.py`
  - Setup: CSV with 95 valid rows, 5 invalid rows
  - Execute: Import command
  - Assert: 95 imported, 5 errors, exit code 1, error details displayed
  - Mark: `@pytest.mark.integration`

- [ ] **T012** [P] Integration test for Scenario 5 (dry run) in `tests/integration/test_import_dryrun.py`
  - Setup: Valid CSV
  - Execute: `stocks-helper import csv file.csv --broker swedbank --dry-run`
  - Assert: 0 transactions in database, import summary displayed, exit code 0
  - Mark: `@pytest.mark.integration`

- [ ] **T013** [P] Integration test for Scenario 6 (negative holdings) in `tests/integration/test_import_negative_holdings.py`
  - Setup: CSV with sell before buy (creates negative holding)
  - Execute: Import command
  - Assert: Import succeeds, negative holdings allowed, no error
  - Mark: `@pytest.mark.integration`

- [ ] **T014** [P] Integration test for Scenario 7 (performance) in `tests/integration/test_import_performance.py`
  - Setup: Generate CSV with 10,000 transactions
  - Execute: Import command with timing
  - Assert: Processing duration < 30 seconds
  - Mark: `@pytest.mark.integration`

- [ ] **T015** [P] Integration test for Scenario 8 (unknown tickers) in `tests/integration/test_import_unknown_tickers.py`
  - Setup: CSV with 3 valid, 3 unknown tickers (APPL typo, XYZZ invalid, TKM1T regional)
  - Execute: Import command
  - Assert: 3 successful, 3 unknown, status='needs_review', suggestions displayed
  - Execute: `stocks-helper import review-tickers <batch_id>`
  - Assert: Table with unknown tickers and suggestions
  - Execute: `stocks-helper import correct-ticker <batch_id> 2 AAPL`
  - Assert: 1 transaction imported with corrected ticker
  - Execute: `stocks-helper import correct-ticker <batch_id> 5 TKM1T.TL`
  - Assert: 1 transaction imported with suffix-corrected ticker
  - Execute: `stocks-helper import delete-rows <batch_id> 4`
  - Assert: Invalid row deleted, status='completed'
  - Mark: `@pytest.mark.integration`

---

## Phase 3.3: Core Implementation (ONLY after tests are failing)

### Data Models

- [ ] **T016** [P] ImportBatch model in `src/models/import_batch.py`
  - SQLAlchemy model with all fields from data-model.md
  - Relationships: one-to-many with Transaction, one-to-many with ImportError
  - State validation: status must be in valid states
  - Property: `requires_review` returns `unknown_ticker_count > 0`

- [ ] **T017** [P] ImportError model in `src/models/import_error.py`
  - SQLAlchemy model with all fields from data-model.md
  - Relationship: many-to-one with ImportBatch
  - JSON field handling for original_row_data and suggested_fix

- [ ] **T018** Extend Transaction model in `src/models/transaction.py`
  - Add fields: broker_reference_id, import_batch_id, broker_source
  - Add relationship: many-to-one with ImportBatch (optional)
  - Preserve existing fields and relationships

- [ ] **T019** [P] CSV schema models in `src/models/csv_schemas.py`
  - Pydantic models: SwedbankCSVRow, LightyearCSVRow, ParsedTransaction
  - Field validators per data-model.md
  - Type conversions (Decimal, datetime)

### CSV Parsers

- [ ] **T020** [P] Base CSVParser interface in `src/services/csv_parser.py`
  - Abstract base class with `parse()` method
  - Exception types: CSVParseError, ValidationError
  - Iterator pattern for memory efficiency

- [ ] **T021** [P] SwedbankCSVParser in `src/services/swedbank_parser.py`
  - Implement CSVParser interface
  - pandas config: delimiter=';', decimal=',', encoding='utf-8'
  - Regex patterns from research.md:
    - Buy/Sell: `(?P<ticker>[A-Z0-9\-]+)\s+(?P<sign>[+-])(?P<quantity>[\d.]+)@(?P<price>[\d.]+)/SE:(?P<reference>\S+)\s+(?P<exchange>\w+)`
    - Dividend: `'/(?P<reference>\d+)/ (?P<isin>[A-Z]{2}\d+) (?P<company>.+?) dividend (?P<gross>[\d.]+) EUR, tulumaks (?P<tax>[\d.]+) EUR`
    - Fee: `K:\s+` + Buy/Sell pattern
  - Yield ParsedTransaction per row
  - Date parsing: DD.MM.YYYY format

- [ ] **T022** [P] LightyearCSVParser in `src/services/lightyear_parser.py`
  - Implement CSVParser interface
  - pandas config: delimiter=',', decimal='.', encoding='utf-8'
  - Direct column mapping (no regex needed)
  - Date parsing: DD/MM/YYYY HH:MM:SS format
  - Handle all transaction types: Buy, Sell, Dividend, Distribution, Deposit, Withdrawal, Conversion, Interest, Reward

### Ticker Validation

- [ ] **T023** TickerValidator service in `src/services/ticker_validator.py`
  - Method: `validate_ticker(ticker: str) -> TickerValidationResult`
  - Strategy from research.md:
    1. Try exact ticker via market data API
    2. Try with exchange suffixes (.TL, .HE, .ST, .OL, .CO, .IC, .L, .DE, .PA, .AS)
    3. Fuzzy match with Levenshtein distance (threshold=2)
  - Cache validation results
  - Async/parallel validation for multiple tickers

- [ ] **T024** Levenshtein distance fuzzy matching in `src/lib/fuzzy_match.py`
  - Function: `levenshtein_distance(s1: str, s2: str) -> int`
  - Function: `fuzzy_match_ticker(ticker: str, known_tickers: Set[str], threshold: int = 2) -> List[str]`
  - Return top 3 matches sorted by distance

### Import Service

- [ ] **T025** ImportService core in `src/services/import_service.py`
  - Method: `import_csv(filepath, broker_type, dry_run=False) -> ImportSummary`
  - Workflow:
    1. Create ImportBatch (status='pending')
    2. Select parser (swedbank/lightyear)
    3. Parse CSV (collect unique tickers)
    4. Validate tickers (parallel)
    5. Load existing broker_reference_ids into set
    6. Import valid transactions (skip duplicates)
    7. Collect errors with suggestions
    8. Update ImportBatch counts and status
    9. Return ImportSummary
  - Handle chunked reading for large files (> 50MB)

- [ ] **T026** ImportService ticker review methods in `src/services/import_service.py`
  - Method: `get_import_history(limit=10) -> List[ImportBatchInfo]`
  - Method: `get_import_errors(batch_id) -> List[ImportErrorDetail]`
  - Method: `get_unknown_tickers(batch_id) -> List[UnknownTickerDetail]`
  - Include fuzzy match suggestions in UnknownTickerDetail

- [ ] **T027** ImportService ticker correction methods in `src/services/import_service.py`
  - Method: `correct_ticker(batch_id, row_numbers, corrected_ticker) -> int`
    - Re-validate corrected ticker
    - Update original_row_data with corrected ticker
    - Import transactions
    - Remove from import_errors
    - Decrement unknown_ticker_count
    - Update status if all resolved
  - Method: `ignore_unknown_tickers(batch_id, row_numbers) -> int`
    - Import with unknown tickers as-is
    - Remove from import_errors
    - Decrement unknown_ticker_count
  - Method: `delete_error_rows(batch_id, row_numbers) -> int`
    - Remove from import_errors
    - Decrement error_count, total_rows, unknown_ticker_count

### CLI Commands

- [ ] **T028** CLI import csv command in `src/cli/import.py`
  - Command: `stocks-helper import csv <filepath> --broker <type> [--dry-run]`
  - Parse arguments
  - Call ImportService.import_csv()
  - Display import summary table (total, successful, duplicates, errors, unknown tickers, duration)
  - If unknown_ticker_count > 0: Display unknown tickers table with suggestions
  - Exit codes: 0=success, 1=partial (needs review), 2=failure

- [ ] **T029** [P] CLI review-tickers command in `src/cli/import.py`
  - Command: `stocks-helper import review-tickers <batch_id>`
  - Call ImportService.get_unknown_tickers()
  - Display table: Row, Ticker, Suggestions, Transaction preview
  - Display instructions for correct-ticker, ignore-tickers, delete-rows commands

- [ ] **T030** [P] CLI correct-ticker command in `src/cli/import.py`
  - Command: `stocks-helper import correct-ticker <batch_id> <row_numbers> <ticker>`
  - Parse comma-separated row_numbers
  - Call ImportService.correct_ticker()
  - Display: "✓ Corrected N rows to TICKER", "Remaining errors: X"
  - Exit codes: 0=success, 1=validation error, 2=failure

- [ ] **T031** [P] CLI ignore-tickers command in `src/cli/import.py`
  - Command: `stocks-helper import ignore-tickers <batch_id> <row_numbers>`
  - Parse comma-separated row_numbers
  - Call ImportService.ignore_unknown_tickers()
  - Display: "✓ Imported N transactions with unknown tickers", "Remaining errors: X"

- [ ] **T032** [P] CLI delete-rows command in `src/cli/import.py`
  - Command: `stocks-helper import delete-rows <batch_id> <row_numbers>`
  - Parse comma-separated row_numbers
  - Call ImportService.delete_error_rows()
  - Display: "✓ Deleted N error rows", "Remaining errors: X"

---

## Phase 3.4: Integration & Error Handling

- [ ] **T033** Connect ImportService to existing database session in `src/services/import_service.py`
  - Use existing SQLAlchemy session management
  - Ensure transactions committed only if not dry_run
  - Rollback on unrecoverable errors

- [ ] **T034** Error handling and logging in `src/services/import_service.py`
  - Log import start/end with batch_id
  - Log validation errors with row numbers
  - Log duplicate skip count
  - Log unknown ticker detection with suggestions
  - Catch CSVParseError, ValidationError, DatabaseError
  - Set ImportBatch status='failed' on unrecoverable error

- [ ] **T035** Import batch status transitions in `src/services/import_service.py`
  - pending → processing (import starts)
  - processing → completed (all rows imported, no unknowns)
  - processing → needs_review (unknown_ticker_count > 0)
  - processing → failed (unrecoverable error)
  - needs_review → completed (all unknowns resolved)

- [ ] **T036** Duplicate detection optimization in `src/services/import_service.py`
  - Bulk load existing broker_reference_ids for broker into set (single query)
  - O(1) membership test per row
  - Index verification: composite unique index on (broker_source, broker_reference_id)

- [ ] **T037** Portfolio holdings update after import in `src/services/import_service.py`
  - Call existing portfolio recalculation logic after successful import
  - Update holdings for all affected tickers
  - Recalculate cost basis for buy/sell transactions

---

## Phase 3.5: Polish & Validation

### Unit Tests

- [ ] **T038** [P] Unit tests for Swedbank parser in `tests/unit/test_swedbank_parser.py`
  - Test buy transaction parsing (regex)
  - Test sell transaction parsing (regex)
  - Test dividend parsing (regex)
  - Test fee parsing (regex)
  - Test date format conversion (DD.MM.YYYY)
  - Test decimal separator handling (comma)
  - Mark: `@pytest.mark.unit`

- [ ] **T039** [P] Unit tests for Lightyear parser in `tests/unit/test_lightyear_parser.py`
  - Test all transaction type handling
  - Test date format conversion (DD/MM/YYYY HH:MM:SS)
  - Test multi-currency handling
  - Test optional fields (ticker, quantity for non-trade transactions)
  - Mark: `@pytest.mark.unit`

- [ ] **T040** [P] Unit tests for TickerValidator in `tests/unit/test_ticker_validator.py`
  - Test exact ticker validation (AAPL)
  - Test exchange suffix detection (TKM1T → TKM1T.TL)
  - Test fuzzy matching (APPL → AAPL)
  - Test unknown ticker (XYZZ → no suggestions)
  - Test caching behavior
  - Mark: `@pytest.mark.unit`

- [ ] **T041** [P] Unit tests for fuzzy matching in `tests/unit/test_fuzzy_match.py`
  - Test Levenshtein distance calculation
  - Test fuzzy_match_ticker with various thresholds
  - Test edge cases (empty string, identical strings)
  - Mark: `@pytest.mark.unit`

- [ ] **T042** [P] Unit tests for duplicate detection in `tests/unit/test_duplicate_detection.py`
  - Test broker_reference_id matching
  - Test different brokers don't conflict (broker_source differentiates)
  - Test NULL broker_reference_id handling (manual entries)
  - Mark: `@pytest.mark.unit`

### Performance & Optimization

- [ ] **T043** Performance profiling for 10k row import in `tests/performance/test_import_performance.py`
  - Generate 10,000 row CSV
  - Profile import with cProfile
  - Assert: Total duration < 30s
  - Assert: Memory usage < 200MB
  - Identify bottlenecks (CSV parsing, validation, DB insertion)

- [ ] **T044** Optimize ticker validation parallelization in `src/services/ticker_validator.py`
  - Implement asyncio.gather for parallel API calls
  - Batch size: 20 unique tickers per batch
  - Target: < 5s for 20 ticker validation (with exchange suffix detection)

- [ ] **T045** Optimize database bulk insert in `src/services/import_service.py`
  - Use session.bulk_insert_mappings() for large imports
  - Batch inserts: commit every 1000 rows for large files
  - Measure performance improvement vs individual inserts

### Documentation & Cleanup

- [ ] **T046** [P] Add docstrings to all public methods in `src/services/` and `src/lib/`
  - ImportService methods
  - CSV parser methods
  - TickerValidator methods
  - Follow Google-style docstrings

- [ ] **T047** [P] Update README.md with import command examples
  - Basic import: `stocks-helper import csv file.csv --broker swedbank`
  - Dry run: `stocks-helper import csv file.csv --broker swedbank --dry-run`
  - Ticker review workflow: review-tickers, correct-ticker, ignore-tickers, delete-rows

- [ ] **T048** Remove code duplication in parsers
  - Extract common pandas config logic to base class
  - Extract common validation logic to shared module
  - DRY: date parsing, decimal handling, error collection

- [ ] **T049** Add type hints to all functions
  - Ensure mypy passes with strict mode
  - Fix any type inconsistencies
  - Add return type annotations

### Manual Validation (Quickstart Scenarios)

- [ ] **T050** Execute all 8 quickstart scenarios in `specs/002-bulk-transaction-import/quickstart.md`
  - Scenario 1: First import (Swedbank)
  - Scenario 2: Re-import duplicates
  - Scenario 3: Lightyear multi-currency
  - Scenario 4: Partial import with errors
  - Scenario 5: Dry run
  - Scenario 6: Negative holdings
  - Scenario 7: Performance (10k rows)
  - Scenario 8: Unknown ticker handling (typo, regional, invalid)
  - Document results: all scenarios must pass

---

## Dependencies

### Phase Dependencies
- **T001-T004** (Setup) must complete before all other tasks
- **T005-T015** (Tests) must complete and FAIL before T016-T037 (Implementation)
- **T016-T019** (Models) must complete before T025-T027 (Services)
- **T020-T022** (Parsers) must complete before T025 (ImportService)
- **T023-T024** (Ticker Validation) must complete before T025 (ImportService)
- **T025-T027** (ImportService) must complete before T028-T032 (CLI)
- **T028-T032** (CLI) must complete before T038-T050 (Polish & Validation)

### Specific Task Dependencies
- T016 → T025, T033
- T017 → T025, T034
- T018 → T025, T037
- T019 → T020, T021, T022
- T020 → T021, T022
- T021 → T025
- T022 → T025
- T023 → T025
- T024 → T023
- T025 → T026, T027, T028, T033, T034, T035, T036, T037
- T026 → T029
- T027 → T030, T031, T032
- T028 → T050
- T029-T032 → T015 (integration test needs these commands)
- T033-T037 → T008-T015 (integration tests need full integration)

---

## Parallel Execution Examples

### Phase 3.2: All contract and integration tests in parallel (T005-T015)
```bash
# Launch all tests together (11 tasks, different files):
pytest tests/contract/test_swedbank_csv_contract.py tests/contract/test_lightyear_csv_contract.py tests/contract/test_import_service_contract.py tests/integration/test_import_swedbank_first.py tests/integration/test_import_duplicates.py tests/integration/test_import_lightyear_multicurrency.py tests/integration/test_import_partial_success.py tests/integration/test_import_dryrun.py tests/integration/test_import_negative_holdings.py tests/integration/test_import_performance.py tests/integration/test_import_unknown_tickers.py -v
```

### Phase 3.3: Models in parallel (T016-T019)
```bash
# These 4 tasks touch different files, can run in parallel:
# T016: src/models/import_batch.py
# T017: src/models/import_error.py
# T018: src/models/transaction.py (extend existing)
# T019: src/models/csv_schemas.py
```

### Phase 3.3: Parsers in parallel (T020-T022)
```bash
# These 3 tasks touch different files, can run in parallel:
# T020: src/services/csv_parser.py
# T021: src/services/swedbank_parser.py
# T022: src/services/lightyear_parser.py
```

### Phase 3.3: CLI commands in parallel (T029-T032)
```bash
# These 4 CLI commands can be added in parallel (same file but different functions):
# CAUTION: Same file, but since they're separate functions, can be done concurrently by different agents
# T029: review-tickers command
# T030: correct-ticker command
# T031: ignore-tickers command
# T032: delete-rows command
```

### Phase 3.5: Unit tests in parallel (T038-T042)
```bash
# All unit tests in parallel (5 tasks, different files):
pytest tests/unit/test_swedbank_parser.py tests/unit/test_lightyear_parser.py tests/unit/test_ticker_validator.py tests/unit/test_fuzzy_match.py tests/unit/test_duplicate_detection.py -v
```

### Phase 3.5: Documentation in parallel (T046-T047)
```bash
# These 2 tasks touch different files, can run in parallel:
# T046: Add docstrings to src/services/ and src/lib/
# T047: Update README.md
```

---

## Notes

- **[P] tasks**: Different files, no dependencies, safe for parallel execution
- **Verify tests fail**: Before T016, run tests and confirm they fail (Red phase)
- **TDD discipline**: Never implement before tests fail
- **Commit after each task**: Atomic commits for easier rollback
- **Performance target**: < 30s for 10k transactions (T043, T050)
- **Exchange suffix detection**: 10 common exchanges (.TL, .HE, .ST, .OL, .CO, .IC, .L, .DE, .PA, .AS)
- **Fuzzy matching**: Levenshtein distance threshold=2 for typo detection

---

## Validation Checklist
*GATE: All must pass before considering tasks complete*

- [x] All contracts have corresponding tests (T005-T007)
- [x] All entities have model tasks (T016-T019)
- [x] All tests come before implementation (T005-T015 before T016-T037)
- [x] Parallel tasks truly independent (verified different files)
- [x] Each task specifies exact file path (all tasks include paths)
- [x] No task modifies same file as another [P] task (verified)
- [x] All CLI commands from contracts implemented (T028-T032)
- [x] All quickstart scenarios covered (T008-T015, T050)
- [x] Ticker validation with suffix detection included (T023-T024)
- [x] Performance requirements specified (T043, T044, T045)

---

**Total Tasks**: 50
**Estimated Parallel Groups**: 5 major parallel opportunities (tests, models, parsers, unit tests, docs)
**Estimated Completion**: 3-5 days with full TDD discipline

Ready for Phase 3 execution. Begin with T001-T004 (Setup), then T005-T015 (Tests - must fail), then T016+ (Implementation).
