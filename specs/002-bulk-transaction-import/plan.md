# Implementation Plan: Bulk Transaction Import

**JIRA Task**: N/A
**Branch**: `002-bulk-transaction-import` | **Date**: 2025-10-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-bulk-transaction-import/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → ✅ Loaded spec.md
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → ✅ Detected Python 3.11, single project type
3. Fill the Constitution Check section based on the content of the constitution document.
   → ✅ Evaluated against constitutional principles
4. Evaluate Constitution Check section below
   → ✅ No violations, complexity justified
5. Execute Phase 0 → research.md
   → IN PROGRESS
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, AGENTS.md update
   → PENDING
7. Re-evaluate Constitution Check section
   → PENDING
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
   → PENDING
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 8. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Build a bulk CSV transaction import system for Swedbank and Lightyear broker accounts. The system will parse broker-specific CSV formats, validate transactions, detect duplicates using broker reference IDs, **validate tickers against market data APIs with exchange suffix auto-detection (e.g., TKM1T → TKM1T.TL) and fuzzy matching for typos**, handle invalid rows with manual intervention prompts (including unknown ticker correction workflow), and update portfolio holdings while maintaining multi-currency support without conversion at import time.

## Technical Context
**Language/Version**: Python 3.11
**Primary Dependencies**: pandas 2.3.3 (CSV parsing), SQLAlchemy 2.0.43 (storage), pydantic 2.10.3 (validation)
**Storage**: SQLite (existing database via SQLAlchemy)
**Testing**: pytest 8.3.4 with contract/integration/unit markers
**Target Platform**: CLI application (macOS/Linux)
**Project Type**: single (src/ with models/services/cli/lib structure)
**Performance Goals**: Process 10,000 transactions per import within 30 seconds
**Constraints**: Ticker validation during import (API calls to verify tickers exist), support comma and semicolon CSV delimiters, handle Estonian and English locale formats (DD.MM.YYYY vs DD/MM/YYYY)
**Scale/Scope**: Support 2 brokers initially (Swedbank, Lightyear), 10+ transaction types, handle CSV files up to 50,000 rows, validate unique tickers (~10-20 per import)

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Core Principles Alignment

**I. Simplicity First** ✅
- Use existing pandas for CSV parsing (no custom parser)
- Leverage SQLAlchemy ORM for storage (already in use)
- Single-pass import workflow (read → validate → store)
- No abstraction layers beyond existing models/services structure

**II. Quality Over Speed (NON-NEGOTIABLE)** ✅
- TDD approach: Contract tests for CSV parsers, integration tests for import workflow
- Small focused functions: CSV parser per broker, validator per transaction type
- Full test coverage required before merging

**III. Fail Fast & Loud** ✅
- Explicit validation errors with row numbers and reasons
- Invalid rows flagged for manual intervention (no silent skips)
- Duplicate detection reports skipped count explicitly
- Transaction parsing failures include original CSV data in error

**IV. Self-Documenting Code** ✅
- Clear naming: `SwedbankCSVParser`, `LightyearCSVParser`, `TransactionValidator`
- Type hints with pydantic models for CSV row schemas
- Comments only for non-obvious business rules (e.g., Swedbank description parsing patterns)

**V. Continuous Improvement** ✅
- Incremental feature: Add import without modifying existing transaction display/analysis
- Isolated changes: New models/services, minimal changes to existing code
- Refactor opportunities: Extract common CSV validation logic after both parsers work

### Technical Standards Alignment

**Code Organization** ✅
- DRY: Common validation logic in `lib/validators/transaction_validator.py`
- KISS: Direct CSV → Model → Database flow (no intermediate representations)
- YAGNI: Build only for 2 brokers now, easy to extend later
- SRP: Separate parser per broker, separate validator per transaction type

**Testing (NON-NEGOTIABLE)** ✅
- Contract tests: Verify CSV parsing against sample files (research/swed_*.csv, research/lightyear_*.csv)
- Integration tests: Full import workflow scenarios from spec acceptance criteria
- Unit tests: Transaction validators, duplicate detection, currency handling

**Error Handling** ✅
- Explicit exception types: `CSVParseError`, `DuplicateTransactionError`, `ValidationError`
- Contextual messages: Include row number, field name, expected format, actual value
- No silent failures: All errors logged and reported in import summary

**Performance** ✅
- Measure: Profile import time for 10k transaction CSV baseline
- Targets: <30s for 10k rows, <100MB memory usage
- Monitor: Track import duration in import_batch metadata

### Project Constraints Alignment

**Technology Choices** ✅
- Primary language: Python (existing)
- Established libraries: pandas (CSV), SQLAlchemy (DB), pydantic (validation) - all already in use
- No new external dependencies required

**Complexity Limits** ✅
- Single project structure: Adding to existing src/models, src/services, src/cli
- No new abstraction layers: Using existing SQLAlchemy models pattern
- No "just in case" features: Building only for 2 brokers, only required transaction types

### Decision Rationale

**Why pandas for CSV parsing?**
- Already a dependency (pandas 2.3.3)
- Handles multiple delimiters, encodings, decimal separators natively
- Well-tested library, avoids custom parsing bugs

**Why broker-specific parsers vs generic parser?**
- Swedbank CSV has complex description field parsing (regex patterns for ticker/quantity/price)
- Lightyear CSV is straightforward column mapping
- Generic parser would add complexity to handle both formats
- Constitution principle: Simplicity First - two simple parsers beats one complex configurable parser

**Why pydantic for validation?**
- Already a dependency (pydantic 2.10.3)
- Type-safe validation with clear error messages
- Easy to test validators in isolation

**Complexity Justified**:
- Two CSV parsers (Swedbank, Lightyear) required due to fundamentally different formats
- Pattern-based description parsing for Swedbank required due to broker format
- Manual intervention workflow adds complexity but required per spec FR-010

## Project Structure

### Documentation (this feature)
```
specs/002-bulk-transaction-import/
├── spec.md              # Feature specification with clarifications
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command) - PENDING
├── data-model.md        # Phase 1 output (/plan command) - PENDING
├── quickstart.md        # Phase 1 output (/plan command) - PENDING
├── contracts/           # Phase 1 output (/plan command) - PENDING
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
src/
├── models/
│   ├── transaction.py           # EXISTS - extend with broker_reference_id, import_batch_id
│   ├── import_batch.py          # NEW - import session metadata
│   ├── import_error.py          # NEW - validation failure tracking
│   └── csv_schemas.py           # NEW - pydantic models for CSV row validation
├── services/
│   ├── import_service.py        # NEW - orchestrates import workflow
│   ├── csv_parser.py            # NEW - base parser interface
│   ├── swedbank_parser.py       # NEW - Swedbank CSV parsing logic
│   └── lightyear_parser.py      # NEW - Lightyear CSV parsing logic
├── cli/
│   └── import.py                # NEW - CLI commands for import
└── lib/
    └── validators/
        └── transaction_validator.py  # NEW - transaction validation rules

tests/
├── contract/
│   ├── test_swedbank_csv_parsing.py    # NEW - verify Swedbank CSV contract
│   └── test_lightyear_csv_parsing.py   # NEW - verify Lightyear CSV contract
├── integration/
│   ├── test_bulk_import_workflow.py    # NEW - end-to-end import scenarios
│   └── test_duplicate_handling.py      # NEW - duplicate detection scenarios
└── unit/
    ├── test_transaction_validator.py   # NEW - validation logic tests
    ├── test_swedbank_parser.py         # NEW - Swedbank parser unit tests
    └── test_lightyear_parser.py        # NEW - Lightyear parser unit tests
```

**Structure Decision**: Single project structure maintained (src/ with models/services/cli/lib). No new top-level directories needed. Import functionality integrates cleanly into existing architecture.

## Phase 0: Outline & Research

### Unknowns to Research
1. **CSV Parsing Strategy**: Best practices for multi-delimiter, multi-encoding CSV handling with pandas
2. **Swedbank Description Parsing**: Reliable regex patterns for extracting ticker/quantity/price from "Selgitus" field
3. **Date Format Handling**: Converting Estonian (DD.MM.YYYY) and English (DD/MM/YYYY HH:MM:SS) formats consistently
4. **Duplicate Detection**: Efficient lookup strategy for broker reference IDs in existing database
5. **Validation Rules**: Per-transaction-type validation requirements (what makes each type valid?)
6. **CSV File Size Limits**: Practical limits for pandas read_csv with memory constraints
7. **Decimal Separator Handling**: Estonian format uses comma (e.g., "135,00"), need consistent conversion

### Research Tasks
1. Research pandas CSV parsing with multiple delimiters and encodings
2. Research regex patterns for Swedbank transaction description parsing
3. Research SQLAlchemy efficient duplicate lookup strategies (indexed queries)
4. Research pydantic validation patterns for financial data
5. Research pandas memory-efficient CSV reading for large files

**Output**: research.md with all technical decisions documented

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

### Entities to Design (data-model.md)

#### New Entities
1. **ImportBatch**: Tracks import session metadata
   - Fields: id, filename, broker_type, upload_timestamp, total_rows, successful_count, duplicate_count, error_count, status, processing_duration
   - Relationships: one-to-many with Transaction, one-to-many with ImportError
   - State: pending → processing → completed/failed

2. **ImportError**: Tracks validation failures
   - Fields: id, import_batch_id, row_number, error_type, error_message, original_row_data
   - Relationships: many-to-one with ImportBatch

3. **CSV Row Schemas** (pydantic models):
   - `SwedbankCSVRow`: Maps Estonian headers to typed fields
   - `LightyearCSVRow`: Maps English headers to typed fields
   - Both include validation rules from research

#### Modified Entities
1. **Transaction** (extend existing):
   - Add fields: broker_reference_id (unique per broker), import_batch_id (foreign key)
   - Add index on broker_reference_id for efficient duplicate lookup
   - Preserve existing fields: date, ticker, quantity, price, fees, type, currency

### API Contracts (contracts/)

#### CLI Interface Contract
```yaml
# contracts/import_cli.yaml
commands:
  - name: stocks-helper import csv
    args:
      - name: filepath
        type: path
        required: true
        description: Path to CSV file
      - name: --broker
        type: choice
        choices: [swedbank, lightyear]
        required: true
        description: Broker type
    outputs:
      - import_summary:
          total_rows: integer
          successful: integer
          duplicates: integer
          errors: integer
          invalid_rows: list[dict]  # Requires manual intervention
    exit_codes:
      0: Success (all rows imported or duplicates)
      1: Partial success (some rows need intervention)
      2: Total failure (parsing error, file not found)
```

#### Import Service Contract
```python
# contracts/import_service.py
from typing import Protocol, List
from pathlib import Path
from models.import_batch import ImportBatch, ImportSummary

class ImportService(Protocol):
    def import_csv(
        self,
        filepath: Path,
        broker_type: str
    ) -> ImportSummary:
        """
        Import transactions from CSV file.

        Returns:
            ImportSummary with counts and invalid rows for manual intervention

        Raises:
            CSVParseError: File format invalid
            FileNotFoundError: File doesn't exist
        """
        ...
```

#### CSV Parser Contract
```python
# contracts/csv_parser.py
from typing import Protocol, Iterator
from models.csv_schemas import ParsedTransaction

class CSVParser(Protocol):
    def parse(self, filepath: Path) -> Iterator[ParsedTransaction]:
        """
        Parse CSV file into validated transaction models.

        Yields:
            ParsedTransaction for each valid row

        Raises:
            CSVParseError: With row number and reason for failures
        """
        ...
```

### Integration Test Scenarios (from spec acceptance criteria)

1. **Scenario: Import Swedbank CSV with mixed transaction types**
   - Given: CSV file with buy/sell/dividend transactions
   - When: Execute import command
   - Then: Portfolio holdings updated, import summary shows success

2. **Scenario: Partial import with invalid rows**
   - Given: CSV with 100 rows (95 valid, 5 invalid)
   - When: Execute import
   - Then: 95 imported, 5 flagged for manual intervention

3. **Scenario: Duplicate handling**
   - Given: Previously imported transactions
   - When: Re-import same CSV
   - Then: Duplicates skipped, count reported in summary

4. **Scenario: Multi-currency import**
   - Given: CSV with EUR and USD transactions
   - When: Import completes
   - Then: Transactions stored in original currencies

5. **Scenario: Negative holdings allowed**
   - Given: Sell transaction before any buy
   - When: Import executes
   - Then: Negative holding recorded without error

### Quickstart Test Plan (quickstart.md)

```markdown
# Bulk Transaction Import Quickstart

## Prerequisites
- Sample CSV files in research/ directory
- Empty test database
- Python 3.11 environment activated

## Test Steps

### 1. Import Swedbank CSV
stocks-helper import csv research/swed_2020_2021.csv --broker swedbank

Expected output:
- Import summary with total/successful/duplicate/error counts
- No errors for valid rows
- Invalid rows (if any) listed for manual intervention

### 2. Verify Transactions Imported
stocks-helper holdings list

Expected: Holdings from imported transactions displayed

### 3. Re-import Same File (Duplicate Test)
stocks-helper import csv research/swed_2020_2021.csv --broker swedbank

Expected: All transactions marked as duplicates, count reported

### 4. Import Lightyear CSV
stocks-helper import csv research/lightyear_2022_2025.csv --broker lightyear

Expected: Lightyear transactions imported successfully

### 5. Multi-Currency Verification
stocks-helper holdings list --show-currency

Expected: Holdings shown in original currencies (EUR, USD)
```

### AGENTS.md Update Plan
- Add "Python 3.11 + pandas + SQLAlchemy" to Active Technologies (002-bulk-transaction-import)
- Add to Recent Changes: "002-bulk-transaction-import: Added CSV import with pandas CSV parsing"
- Keep file compact, remove oldest entry if exceeds 3 recent changes

**Outputs**:
- data-model.md (entities, relationships, validation rules, TickerValidationResult model)
- contracts/ (CLI with ticker review commands, service with ticker correction methods, parser contracts)
- quickstart.md (manual test scenarios including Scenario 8: Unknown Ticker Handling)
- AGENTS.md updated (technology stack entry)
- Contract tests (failing, TDD red phase)

**Ticker Validation Enhancement**:
- Unknown tickers detected during import via market data API validation
- **Exchange suffix auto-detection**: TKM1T → tries TKM1T.TL, TKM1T.HE, etc. (10 common exchanges)
- Fuzzy matching for typo suggestions (Levenshtein distance) as fallback
- Manual intervention workflow: review → correct/ignore/delete
- ImportBatch status='needs_review' when unknown tickers found
- 4 new CLI commands: review-tickers, correct-ticker, ignore-tickers, delete-rows
- Supported exchanges: Tallinn (.TL), Helsinki (.HE), Stockholm (.ST), Oslo (.OL), Copenhagen (.CO), Iceland (.IC), London (.L), XETRA (.DE), Paris (.PA), Amsterdam (.AS)

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
1. Load `~/.ai/1_templates/tasks-template.md` as base structure
2. Generate tasks from Phase 1 artifacts:
   - From contracts/ → contract test tasks (one per contract)
   - From data-model.md → model creation tasks (ImportBatch, ImportError, extend Transaction)
   - From CSV schemas → pydantic model tasks
   - From parsers → parser implementation tasks (Swedbank, Lightyear)
   - From service contract → import service orchestration task
   - From CLI contract → CLI command implementation task
   - From validation rules → validator implementation tasks
   - From integration scenarios → integration test tasks

**Task Dependencies**:
- Models must exist before services
- Parsers must exist before import service
- Import service must exist before CLI
- Contract tests before implementation
- Integration tests after all components exist

**Ordering Strategy** (TDD order):
1. Contract tests (Red phase - must fail)
2. Data models (Green phase - make contract tests pass)
3. Parsers with unit tests (Red → Green)
4. Validators with unit tests (Red → Green)
5. Import service with integration tests (Red → Green)
6. CLI with integration tests (Red → Green)
7. Refactor phase (cleanup, extract common logic)

**Parallelization Opportunities** [P]:
- Swedbank parser and Lightyear parser (independent) [P]
- Unit tests per parser (independent per file) [P]
- Contract tests per contract (independent) [P]

**Estimated Output**: 30-35 numbered tasks in tasks.md
- ~5 contract test tasks
- ~5 model tasks (new + migrations)
- ~8 parser tasks (2 parsers × 4 subtasks each)
- ~4 validator tasks
- ~6 service tasks
- ~4 CLI tasks
- ~3 integration test tasks
- ~2 refactor tasks

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)
**Phase 4**: Implementation (execute tasks.md following constitutional principles)
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

No violations detected. All complexity justified within constitutional limits:
- Two broker-specific parsers required due to fundamentally different CSV formats
- Pattern-based parsing for Swedbank justified by broker's data structure
- Manual intervention workflow adds necessary complexity per specification requirements

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command) - research.md created
- [x] Phase 1: Design complete (/plan command) - data-model.md, contracts/, quickstart.md, AGENTS.md updated
- [x] Phase 2: Task planning complete (/plan command - approach described, tasks.md NOT created)
- [ ] Phase 3: Tasks generated (/tasks command) - NEXT STEP
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS (no new violations)
- [x] All NEEDS CLARIFICATION resolved (Phase 0 research complete)
- [x] Complexity deviations documented (none - all within limits)

---
*Based on Constitution - See `constitution.md` at project root*
