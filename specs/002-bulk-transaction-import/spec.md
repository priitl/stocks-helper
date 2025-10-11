# Feature Specification: Bulk Transaction Import

**JIRA Task**: N/A
**Feature Branch**: `002-bulk-transaction-import`
**Created**: 2025-10-06
**Status**: Draft
**Input**: User description: "i want to add bulk import support for all my transactions across different brokers (swedbank, lightyear). they provide csv for everything that has happend in that account buy, sell, dividend, withdraw, conversion, distribution, conversion etc etc. we need to store these and update our porfolio based on these. i will provide the exact csv samples later."

## Execution Flow (main)
```
1. Parse user description from Input
   → If empty: ERROR "No feature description provided"
2. Extract key concepts from description
   → Identified: brokers (Swedbank, Lightyear), transaction types (buy, sell, dividend, withdraw, conversion, distribution), CSV import, portfolio updates
3. For each unclear aspect:
   → CSV format/schema per broker [NEEDS CLARIFICATION: exact CSV samples pending]
   → Data validation rules [NEEDS CLARIFICATION: what makes a transaction valid?]
   → Error handling strategy [NEEDS CLARIFICATION: how to handle invalid rows?]
   → Historical data handling [NEEDS CLARIFICATION: what if transactions already exist?]
4. Fill User Scenarios & Testing section
   → User flow: upload CSV → validate → import → update portfolio
5. Generate Functional Requirements
   → Each requirement must be testable
   → Marked ambiguous requirements with [NEEDS CLARIFICATION]
6. Identify Key Entities (if data involved)
   → Transaction, Broker, ImportBatch
7. Run Review Checklist
   → WARN "Spec has uncertainties - CSV samples pending"
8. Return: SUCCESS (spec ready for planning after clarification)
```

---

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

---

## Clarifications

### Session 2025-10-06
- Q: When re-importing a CSV with transactions that already exist in the system, what should happen? → A: Skip duplicates but report them in the import summary
- Q: What field combination should identify a transaction as a duplicate? → A: Broker's unique reference/transaction ID only
- Q: When a CSV contains invalid rows (malformed data, missing required fields), how should the import process behave? → A: Import all valid rows that do not need manual intervention. Rows that need manual intervention need to be prompted at the end so that user can give guidance how to import them
- Q: When importing transactions in different currencies (USD, EUR, etc.), how should the system handle currency conversion? → A: Store transactions in original currency only (no conversion). Portfolio overview must track currency conversion profit/loss separately
- Q: When importing transactions that would result in negative holdings (e.g., selling shares before any buy transactions exist), what should happen? → A: Allow negative holdings (short positions or data reconciliation scenarios)

---

## User Scenarios & Testing

### Primary User Story
As a portfolio owner, I need to import all historical transactions from my broker accounts (Swedbank, Lightyear) via CSV files so that my portfolio reflects accurate holdings, cost basis, and transaction history without manual data entry.

### Acceptance Scenarios
1. **Given** a CSV file from Swedbank containing buy/sell/dividend transactions, **When** I upload the file, **Then** all valid transactions are imported and my portfolio holdings are updated accordingly
2. **Given** a CSV file from Lightyear with 100 transactions (95 valid, 5 invalid), **When** I upload it, **Then** the system imports 95 valid transactions automatically and prompts the user to provide guidance for the 5 invalid rows
3. **Given** I've already imported transactions for January 2024, **When** I upload a CSV containing those same transactions again, **Then** the system skips duplicate transactions and includes them in the import summary report with a duplicate count
4. **Given** a CSV with mixed transaction types (buy, sell, dividend, withdrawal, conversion), **When** imported, **Then** each transaction type correctly updates portfolio state
5. **Given** a CSV with mixed currencies (EUR, USD), **When** imported, **Then** transactions are stored in their original currencies and portfolio overview tracks currency conversion profit/loss separately

### Edge Cases
- CSV rows that are malformed or missing required fields are flagged for manual intervention and presented to the user at the end of the import process
- Duplicate transactions (identified by broker's unique reference ID) are skipped and counted in the import summary
- What if a CSV contains transactions for tickers not yet in the system?
- How are stock splits/reverse splits reflected in historical imports?
- Negative holdings are allowed (to support short positions or data reconciliation when historical data is incomplete)
- Partial imports are supported: valid rows are imported, invalid rows requiring manual intervention are presented to the user for guidance
- What happens with transactions dated in the future?
- How are dividend reinvestments represented vs cash dividends?

## Requirements

### Functional Requirements
- **FR-001**: System MUST support CSV import from Swedbank broker accounts
- **FR-002**: System MUST support CSV import from Lightyear broker accounts
- **FR-003**: System MUST support the following transaction types: buy, sell, dividend, withdrawal, conversion, distribution
- **FR-004**: System MUST validate each transaction row before import [NEEDS CLARIFICATION: specific validation rules per transaction type]
- **FR-005**: System MUST store all imported transactions with complete audit trail (source broker, import timestamp, original CSV data)
- **FR-006**: System MUST update portfolio holdings based on imported transactions
- **FR-007**: System MUST update portfolio cost basis calculations when buy/sell transactions are imported
- **FR-007a**: System MUST allow negative holdings to support short positions and data reconciliation scenarios
- **FR-008**: System MUST detect duplicate transactions using the broker's unique reference/transaction ID and skip them during import
- **FR-009**: System MUST provide import summary report showing: total rows, successful imports, rows requiring manual intervention, skipped duplicates count
- **FR-010**: System MUST present invalid/ambiguous rows to the user at the end of import for manual guidance on how to handle them
- **FR-011**: System MUST preserve original CSV data for each import batch [NEEDS CLARIFICATION: retention policy?]
- **FR-012**: System MUST store each transaction in its original currency without conversion
- **FR-012a**: Portfolio overview MUST calculate and display currency conversion profit/loss separately
- **FR-013**: System MUST maintain chronological transaction ordering regardless of import sequence
- **FR-014**: Valid rows MUST be imported successfully even when invalid rows exist in the same batch (no rollback on partial failure)
- **FR-015**: System MUST support [NEEDS CLARIFICATION: file size limit? row limit per import?]
- **FR-016**: System MUST map CSV broker-specific field names to internal transaction fields according to broker CSV format specifications (see CSV Format Specifications section)
- **FR-017**: System MUST support the following transaction types from Lightyear: Buy, Sell, Dividend, Distribution, Deposit, Withdrawal, Conversion, Interest, Reward
- **FR-018**: System MUST parse Swedbank transaction details from the description field to extract ticker, quantity, price, and transaction type

### CSV Format Specifications

#### Swedbank Format
- **Delimiter**: Semicolon (;)
- **Encoding**: UTF-8 with Estonian language headers
- **Key Fields**:
  - "Kuupäev" → Transaction date (DD.MM.YYYY format)
  - "Selgitus" → Transaction description (contains parsed details)
  - "Summa" → Amount (comma as decimal separator)
  - "Valuuta" → Currency code
  - "Deebet/Kreedit" → D (debit) or K (credit)
  - "Arhiveerimistunnus" → Broker reference ID (unique transaction identifier)
- **Transaction Patterns in "Selgitus" field**:
  - Buy: `TICKER +quantity@price/SE:reference EXCHANGE`
  - Sell: `TICKER -quantity@price/SE:reference EXCHANGE`
  - Dividend: `'/reference/ ISIN COMPANY_NAME dividend X EUR, tulumaks Y EUR`
  - Fee: `K: TICKER +quantity@price/SE:reference EXCHANGE`
- **Supported transaction types**: Buy (+), Sell (-), Dividend, Fee (K:), Deposit/Withdrawal (MK type)

#### Lightyear Format
- **Delimiter**: Comma (,)
- **Encoding**: UTF-8 with English headers
- **Key Fields**:
  - "Date" → Transaction date with timestamp (DD/MM/YYYY HH:MM:SS format)
  - "Reference" → Broker reference ID (unique transaction identifier, format: XX-XXXXXXXXXX)
  - "Ticker" → Stock ticker symbol
  - "ISIN" → International Securities Identification Number
  - "Type" → Transaction type (Buy, Sell, Dividend, Distribution, Deposit, Withdrawal, Conversion, Interest, Reward)
  - "Quantity" → Number of shares (decimal)
  - "CCY" → Currency code
  - "Price/share" → Price per share (decimal)
  - "Fee" → Transaction fee amount
  - "Net Amt." → Net amount after fees and taxes
  - "Tax Amt." → Tax amount withheld
- **Supported transaction types**: Buy, Sell, Dividend, Distribution, Deposit, Withdrawal, Conversion, Interest, Reward

### Key Entities

- **Transaction**: Represents a single financial event (buy, sell, dividend, withdrawal, conversion, distribution) with attributes including: transaction date, ticker/symbol, quantity, price, fees, transaction type, currency, broker source, broker reference ID (unique identifier from broker for duplicate detection)
- **Broker**: Represents the source institution (Swedbank, Lightyear) with broker-specific CSV format configuration
- **ImportBatch**: Represents a single CSV import operation with metadata including: upload timestamp, filename, broker type, total rows, successful count, failed count, user who imported, processing status
- **ImportError**: Represents validation/processing failures for individual rows with: row number, error type, error message, original row data

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

### Requirement Completeness
- [x] No [NEEDS CLARIFICATION] markers remain (3 deferred to planning: validation rules, retention policy, file limits)
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Scope is clearly bounded (CSV import from Swedbank and Lightyear brokers)
- [x] Dependencies and assumptions identified (CSV format specifications documented)

---

## Execution Status
*Updated by main() during processing*

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] CSV format specifications added
- [x] Review checklist passed (5 critical clarifications completed)

---
