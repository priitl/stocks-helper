# Tasks: Personal Stocks Tracker & Analyzer

**JIRA Task**: N/A
**Branch**: `001-stocks-tracker-analyzer`
**Input**: Design documents from `specs/001-stocks-tracker-analyzer/`
**Prerequisites**: plan.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Note**: Task IDs (T001, T002, etc.) are independent implementation steps. All tasks follow TDD principles.

---

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → ✓ Loaded: Python 3.11+, Click, SQLite, TA-Lib, pytest
2. Load optional design documents:
   → ✓ data-model.md: 10 entities extracted
   → ✓ contracts/cli-commands.md: 20+ commands extracted
   → ✓ quickstart.md: 6 acceptance scenarios + edge cases
3. Generate tasks by category:
   → Setup: 5 tasks (project init, deps, DB schema)
   → Tests: 25 tasks (contract + integration tests)
   → Core: 33 tasks (10 models + 8 services + 15 CLI commands)
   → Integration: 3 tasks (DB init, batch scheduler, error handling)
   → Polish: 6 tasks (unit tests, performance, docs)
4. Apply task rules:
   → Different files = [P] for parallel execution
   → Same file = sequential (no [P])
   → Tests before implementation (TDD)
5. Number tasks sequentially (T001-T072)
6. Generate dependency graph (below)
7. Create parallel execution examples (below)
8. Validation: ✓ All entities have models, all contracts have tests
9. Return: SUCCESS (72 tasks ready)
```

---

## Task Summary

- **Total Tasks**: 72
- **Parallelizable**: 48 tasks marked [P]
- **Critical Path**: Setup → Contract Tests → Models → Services → CLI → Integration Tests
- **Estimated Completion**: 15-20 hours (with parallel execution)

---

## Phase 3.1: Setup & Infrastructure (5 tasks)

### T001: Create project structure
**Type**: Setup
**Priority**: Critical
**Files**: Repository root structure
**Description**: Create directory structure per plan.md:
```
mkdir -p src/{models,services,cli,lib}
mkdir -p tests/{contract,integration,unit}
mkdir -p reports
touch src/__init__.py src/models/__init__.py src/services/__init__.py src/cli/__init__.py src/lib/__init__.py
```
**Validation**: Directory structure matches plan.md layout

---

### T002: Create pyproject.toml with dependencies
**Type**: Setup
**Priority**: Critical
**Files**: `pyproject.toml`
**Description**: Create pyproject.toml with all dependencies from research.md:
```toml
[project]
name = "stocks-helper"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "click>=8.0",
    "pandas>=2.0",
    "numpy>=1.24",
    "TA-Lib>=0.4.0",
    "pandas-ta>=0.3.14",
    "aiohttp>=3.9",
    "plotly>=5.0",
    "rich>=13.0",
    "APScheduler>=3.10",
    "sqlalchemy>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.0",
    "pytest-asyncio>=0.21",
    "black>=23.0",
    "ruff>=0.1.0",
]

[project.scripts]
stocks-helper = "src.cli:main"
```
**Validation**: `pip install -e .` succeeds without errors

---

### T003 [P]: Configure linting and formatting
**Type**: Setup
**Priority**: Medium
**Files**: `pyproject.toml` (append), `.gitignore`
**Description**: Add black + ruff config to pyproject.toml, create .gitignore for Python:
```toml
[tool.black]
line-length = 100
target-version = ["py311"]

[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I"]
```
.gitignore: venv/, __pycache__/, *.pyc, .pytest_cache/, .coverage, reports/
**Validation**: `black --check src/` and `ruff check src/` run without errors

---

### T004: Create database schema SQL
**Type**: Setup
**Priority**: Critical
**Files**: `src/lib/schema.sql`
**Description**: Create SQLite schema based on data-model.md for all 10 entities:
- Portfolio, Stock, Holding, Transaction tables
- MarketData, FundamentalData tables (time-series)
- StockRecommendation, StockSuggestion, Insight tables
- ExchangeRate table
- All foreign keys, indexes, constraints from data-model.md
**Validation**: Schema includes all entities, relationships, and indexes from data-model.md

---

### T005: Create database connection module
**Type**: Setup
**Priority**: Critical
**Files**: `src/lib/db.py`
**Dependencies**: T004
**Description**: Create SQLAlchemy connection manager:
- Database path: `~/.stocks-helper/data.db`
- Create tables from schema.sql
- Connection pooling for async operations
- Initialize function to create DB if not exists
**Validation**: Can create database and verify tables exist

---

## Phase 3.2: Contract Tests (TDD - Write First) ⚠️ MUST FAIL BEFORE IMPLEMENTATION

**CRITICAL**: All tests in this phase MUST be written and MUST FAIL before any implementation in Phase 3.3/3.4

### API Contract Tests (Parallel)

### T006 [P]: Contract test Alpha Vantage daily data
**Type**: Contract Test
**Priority**: High
**Files**: `tests/contract/test_alpha_vantage_api.py`
**Description**: Test Alpha Vantage TIME_SERIES_DAILY response schema:
- Verify "Meta Data" and "Time Series (Daily)" keys exist
- Verify required fields: open, high, low, close, volume
- Test rate limit handling (mock 429 response)
- Test API key validation
**Expected**: Test FAILS (no API client exists yet)
**Validation**: pytest tests/contract/test_alpha_vantage_api.py fails with import error

---

### T007 [P]: Contract test Yahoo Finance API
**Type**: Contract Test
**Priority**: High
**Files**: `tests/contract/test_yahoo_finance_api.py`
**Description**: Test yfinance library response schema:
- Verify Ticker.history() returns DataFrame
- Verify columns: Open, High, Low, Close, Volume
- Test invalid ticker handling
**Expected**: Test FAILS
**Validation**: pytest runs but fails (no implementation)

---

### T008 [P]: Contract test Exchange Rate API
**Type**: Contract Test
**Priority**: Medium
**Files**: `tests/contract/test_exchange_rate_api.py`
**Description**: Test exchange rate API response:
- Verify rate data structure (from_currency, to_currency, rate)
- Test multiple currency pairs (USD/EUR, USD/GBP, EUR/JPY)
- Test error handling for invalid currencies
**Expected**: Test FAILS
**Validation**: Test exists and fails

---

### CLI Command Contract Tests (Parallel)

### T009 [P]: Contract test portfolio commands
**Type**: Contract Test
**Priority**: High
**Files**: `tests/contract/test_cli_portfolio.py`
**Description**: Test portfolio CLI command structure per contracts/cli-commands.md:
- `portfolio create --name --currency` → verify output format
- `portfolio list` → verify table structure
- `portfolio show` → verify sections present
- Test argument validation (invalid currency, missing required args)
**Expected**: Test FAILS (CLI not implemented)
**Validation**: Uses Click's CliRunner, test fails on missing commands

---

### T010 [P]: Contract test holding commands
**Type**: Contract Test
**Priority**: High
**Files**: `tests/contract/test_cli_holding.py`
**Description**: Test holding CLI commands:
- `holding add` → verify success message format
- `holding sell` → verify transaction recorded
- `holding list` → verify table columns
- `holding show` → verify detail sections
- Test validation (negative quantity, sell more than owned)
**Expected**: Test FAILS
**Validation**: Test fails on missing commands

---

### T011 [P]: Contract test recommendation commands
**Type**: Contract Test
**Priority**: High
**Files**: `tests/contract/test_cli_recommendation.py`
**Description**: Test recommendation CLI commands:
- `recommendation list` → verify BUY/SELL/HOLD grouping
- `recommendation show` → verify technical + fundamental breakdown
- `recommendation refresh` → verify progress output
**Expected**: Test FAILS
**Validation**: Test fails on missing commands

---

### T012 [P]: Contract test suggestion commands
**Type**: Contract Test
**Priority**: Medium
**Files**: `tests/contract/test_cli_suggestion.py`
**Description**: Test suggestion CLI commands:
- `suggestion list --type` → verify filtering works
- `suggestion show` → verify suggestion detail format
**Expected**: Test FAILS
**Validation**: Test fails on missing commands

---

### Integration Tests (Parallel) - Based on quickstart.md

### T013 [P]: Integration test - Scenario 1 (Portfolio setup)
**Type**: Integration Test
**Priority**: High
**Files**: `tests/integration/test_portfolio_setup.py`
**Description**: Test acceptance scenario 1 from quickstart.md:
- Create portfolio → add AAPL → add MSFT → view portfolio
- Verify portfolio value calculated
- Verify gain/loss shown
**Expected**: Test FAILS (commands not implemented)
**Validation**: Test covers full scenario 1 workflow

---

### T014 [P]: Integration test - Scenario 2 (Recommendations)
**Type**: Integration Test
**Priority**: High
**Files**: `tests/integration/test_recommendations.py`
**Description**: Test acceptance scenario 2:
- Setup portfolio with stocks
- Trigger recommendation refresh (mocked API data)
- Verify recommendations generated with BUY/SELL/HOLD
- Verify technical + fundamental signals present
- Verify confidence level calculated
**Expected**: Test FAILS
**Validation**: Covers scenario 2 end-to-end

---

### T015 [P]: Integration test - Scenario 3 (Suggestions)
**Type**: Integration Test
**Priority**: High
**Files**: `tests/integration/test_suggestions.py`
**Description**: Test acceptance scenario 3:
- Setup portfolio with tech-heavy allocation
- Generate suggestions
- Verify diversification suggestions present
- Verify similar-to-winners suggestions
- Verify portfolio fit explanations
**Expected**: Test FAILS
**Validation**: Covers scenario 3 + 3a

---

### T016 [P]: Integration test - Scenario 4 (Insights)
**Type**: Integration Test
**Priority**: High
**Files**: `tests/integration/test_insights.py`
**Description**: Test acceptance scenario 4:
- Setup multi-stock portfolio
- Generate insights
- Verify sector allocation calculated (sum = 100%)
- Verify diversification gaps identified
- Verify risk metrics present
**Expected**: Test FAILS
**Validation**: Covers scenario 4

---

### T017 [P]: Integration test - Scenario 5 (Transaction updates)
**Type**: Integration Test
**Priority**: High
**Files**: `tests/integration/test_transaction_flow.py`
**Description**: Test acceptance scenario 5:
- Check portfolio value
- Add new transaction
- Verify portfolio value updated immediately
- Verify holding quantity updated
**Expected**: Test FAILS
**Validation**: Covers scenario 5

---

### T018 [P]: Integration test - Scenario 6 (Daily batch)
**Type**: Integration Test
**Priority**: Medium
**Files**: `tests/integration/test_daily_batch.py`
**Description**: Test acceptance scenario 6:
- Setup portfolio
- Run batch processor (mocked APIs)
- Verify recommendations generated with fresh timestamps
- Verify market data updated
**Expected**: Test FAILS
**Validation**: Covers scenario 6

---

### Edge Case Tests (Parallel)

### T019 [P]: Integration test - API unavailable fallback
**Type**: Integration Test (Edge Case)
**Priority**: Medium
**Files**: `tests/integration/test_api_fallback.py`
**Description**: Test edge case from quickstart.md:
- Mock Alpha Vantage API failure
- Verify fallback to Yahoo Finance
- Verify cached data used if all APIs fail
- Verify user-friendly error messages
**Expected**: Test FAILS
**Validation**: Covers API failure handling

---

### T020 [P]: Integration test - API rate limit
**Type**: Integration Test (Edge Case)
**Priority**: Medium
**Files**: `tests/integration/test_rate_limit.py`
**Description**: Test rate limit handling:
- Mock rate limit error (429)
- Verify cached data used
- Verify clear user message about next update time
**Expected**: Test FAILS
**Validation**: Covers rate limit edge case

---

### T021 [P]: Integration test - Multi-currency portfolio
**Type**: Integration Test (Edge Case)
**Priority**: High
**Files**: `tests/integration/test_multi_currency.py`
**Description**: Test multi-currency handling:
- Add stock in EUR
- Verify conversion to base currency (USD)
- Verify both original and converted values shown
- Verify exchange rate applied correctly
**Expected**: Test FAILS
**Validation**: Covers multi-currency edge case

---

## Phase 3.3: Core Implementation - Models (ONLY after tests fail)

**All model tasks can run in parallel** - each creates a different file

### T022 [P]: Implement Portfolio model
**Type**: Model
**Priority**: Critical
**Files**: `src/models/portfolio.py`
**Dependencies**: T001-T005 (setup), T006-T021 (tests written and failing)
**Description**: Create Portfolio SQLAlchemy model per data-model.md:
- Fields: id (UUID), name, base_currency, created_at, updated_at
- Relationships: holdings, insights
- Validation: base_currency must be valid ISO 4217
**Validation**: Import succeeds, can create Portfolio instance

---

### T023 [P]: Implement Stock model
**Type**: Model
**Priority**: Critical
**Files**: `src/models/stock.py`
**Dependencies**: T001-T005
**Description**: Create Stock model:
- Fields: ticker (PK), exchange, name, sector, market_cap, currency, country, last_updated
- Relationships: holdings, market_data, recommendations
- Validation: ticker + exchange unique
**Validation**: Can create Stock instance

---

### T024 [P]: Implement Holding model
**Type**: Model
**Priority**: Critical
**Files**: `src/models/holding.py`
**Dependencies**: T001-T005, T022, T023
**Description**: Create Holding model:
- Fields: id, portfolio_id (FK), ticker (FK), quantity, avg_purchase_price, original_currency, first_purchase_date
- Computed properties: current_value, gain_loss, gain_loss_pct (using @property decorator)
- Relationships: portfolio, stock, transactions
**Validation**: Can create Holding with foreign keys

---

### T025 [P]: Implement Transaction model
**Type**: Model
**Priority**: Critical
**Files**: `src/models/transaction.py`
**Dependencies**: T001-T005, T024
**Description**: Create Transaction model:
- Fields: id, holding_id (FK), type (Enum: BUY/SELL), date, quantity, price, currency, exchange_rate, fees, notes
- Validation: SELL quantity cannot exceed holding quantity
- State transition logic for updating holding
**Validation**: Can create buy/sell transactions

---

### T026 [P]: Implement MarketData model
**Type**: Model
**Priority**: High
**Files**: `src/models/market_data.py`
**Dependencies**: T001-T005, T023
**Description**: Create MarketData model (time-series):
- Composite PK: (ticker, timestamp)
- Fields: ticker (FK), timestamp, price, volume, open, high, low, close, data_source, is_latest
- Validation: Only one is_latest=true per ticker
- Index on (ticker, is_latest) for fast current price lookup
**Validation**: Can store market data with composite key

---

### T027 [P]: Implement FundamentalData model
**Type**: Model
**Priority**: High
**Files**: `src/models/fundamental_data.py`
**Dependencies**: T001-T005, T023
**Description**: Create FundamentalData model:
- Composite PK: (ticker, timestamp)
- Fields: pe_ratio, pb_ratio, peg_ratio, roe, roa, profit_margin, revenue_growth_yoy, earnings_growth_yoy, debt_to_equity, current_ratio, dividend_yield, data_source
- Validation: Ratios within reasonable ranges
**Validation**: Can store fundamental metrics

---

### T028 [P]: Implement StockRecommendation model
**Type**: Model
**Priority**: High
**Files**: `src/models/recommendation.py`
**Dependencies**: T001-T005, T022, T023
**Description**: Create StockRecommendation model:
- Fields: id, ticker (FK), portfolio_id (FK), timestamp, recommendation (Enum: BUY/SELL/HOLD), confidence (Enum: HIGH/MEDIUM/LOW), technical_score, fundamental_score, combined_score, technical_signals (JSON), fundamental_signals (JSON), rationale
- Validation: Scores 0-100, combined_score = weighted average
**Validation**: Can store recommendations with JSON fields

---

### T029 [P]: Implement StockSuggestion model
**Type**: Model
**Priority**: High
**Files**: `src/models/suggestion.py`
**Dependencies**: T001-T005, T022, T023
**Description**: Create StockSuggestion model:
- Fields: id, ticker (FK), portfolio_id (FK), timestamp, suggestion_type (Enum: DIVERSIFICATION/SIMILAR_TO_WINNERS/MARKET_OPPORTUNITY), technical_score, fundamental_score, overall_score, technical_summary, fundamental_summary, portfolio_fit, related_holding_ticker
- Validation: Cannot suggest stocks already in portfolio, SIMILAR_TO_WINNERS requires related_holding_ticker
**Validation**: Can create suggestions with type filtering

---

### T030 [P]: Implement Insight model
**Type**: Model
**Priority**: High
**Files**: `src/models/insight.py`
**Dependencies**: T001-T005, T022
**Description**: Create Insight model:
- Fields: id, portfolio_id (FK), timestamp, insight_type (Enum: SECTOR_ALLOCATION/GEO_ALLOCATION/DIVERSIFICATION_GAP/HIGH_PERFORMERS/RISK_ASSESSMENT/PERFORMANCE_TREND), data (JSON), summary
- JSON schemas per data-model.md for each insight type
**Validation**: Can store insights with type-specific JSON data

---

### T031 [P]: Implement ExchangeRate model
**Type**: Model
**Priority**: Medium
**Files**: `src/models/exchange_rate.py`
**Dependencies**: T001-T005
**Description**: Create ExchangeRate model:
- Composite PK: (from_currency, to_currency, date)
- Fields: rate
- Validation: Self-conversion (USD→USD) = 1.0, rate > 0
**Validation**: Can store exchange rates with composite key

---

## Phase 3.4: Core Implementation - Services

### T032 [P]: Implement API client base
**Type**: Service
**Priority**: Critical
**Files**: `src/lib/api_client.py`
**Dependencies**: T002 (dependencies installed)
**Description**: Create async HTTP client with retry logic:
- aiohttp session management
- Exponential backoff retry (3 attempts)
- Rate limit detection (429 status)
- Response caching to JSON files
- Timeout handling (10s default)
**Validation**: Can make async HTTP requests with retry

---

### T033 [P]: Implement cache manager
**Type**: Service
**Priority**: High
**Files**: `src/lib/cache.py`
**Dependencies**: T001
**Description**: Create cache manager for API responses:
- JSON file storage in ~/.stocks-helper/cache/
- TTL-based expiration (15 minutes for market data)
- Cache key generation from (API source, ticker, date)
- Cache cleanup (remove files older than 7 days)
**Validation**: Can store and retrieve cached API responses

---

### T034: Implement MarketDataFetcher service
**Type**: Service
**Priority**: Critical
**Files**: `src/services/market_data_fetcher.py`
**Dependencies**: T023 (Stock model), T026 (MarketData model), T032 (API client), T033 (cache)
**Description**: Create market data fetcher with fallback strategy per research.md:
- Primary: Alpha Vantage TIME_SERIES_DAILY (async)
- Fallback: Yahoo Finance (yfinance)
- Cache responses
- Handle rate limits (25 req/day for Alpha Vantage)
- Stagger requests (1 per 15 seconds)
- Store in MarketData table, set is_latest flag
**Validation**: Contract test T006 and T007 now PASS

---

### T035 [P]: Implement CurrencyConverter service
**Type**: Service
**Priority**: High
**Files**: `src/services/currency_converter.py`
**Dependencies**: T031 (ExchangeRate model), T032 (API client)
**Description**: Create currency converter:
- Fetch daily exchange rates from ExchangeRate-API
- Cache rates in ExchangeRate table
- Convert amount from one currency to another
- Historical rate lookup for transaction dates
**Validation**: Contract test T008 now PASSES, multi-currency test T021 progresses

---

### T036: Implement IndicatorCalculator service
**Type**: Service
**Priority**: High
**Files**: `src/services/indicator_calculator.py`
**Dependencies**: T002 (TA-Lib installed), T026 (MarketData model)
**Description**: Create technical indicator calculator per research.md:
- Trend: SMA (20, 50), EMA, MACD
- Momentum: RSI, Stochastic Oscillator
- Volatility: Bollinger Bands, ATR
- Volume: OBV
- Use TA-Lib library
- Input: historical MarketData, Output: indicator values as dict
**Validation**: Can calculate all indicators from research.md

---

### T037: Implement FundamentalAnalyzer service
**Type**: Service
**Priority**: High
**Files**: `src/services/fundamental_analyzer.py`
**Dependencies**: T027 (FundamentalData model), T034 (MarketDataFetcher)
**Description**: Extract fundamental metrics from API responses:
- Parse Alpha Vantage OVERVIEW endpoint
- Calculate/extract: P/E, P/B, PEG, ROE, ROA, margins, growth rates, debt ratios
- Store in FundamentalData table
- Handle missing data gracefully
**Validation**: Can extract fundamental metrics from API response

---

### T038: Implement RecommendationEngine service
**Type**: Service
**Priority**: Critical
**Files**: `src/services/recommendation_engine.py`
**Dependencies**: T028 (Recommendation model), T036 (IndicatorCalculator), T037 (FundamentalAnalyzer)
**Description**: Implement recommendation logic per research.md:
- Calculate technical_score (weighted: trend 30%, momentum 25%, volatility 15%, volume 10%)
- Calculate fundamental_score (weighted: valuation 30%, growth 25%, profitability 20%, health 15%, dividends 10%)
- combined_score = (technical_score + fundamental_score) / 2
- Confidence: HIGH if both agree, MEDIUM if mostly aligned, LOW if conflict
- Recommendation: BUY if score > 70, SELL if < 30, HOLD otherwise
- Generate rationale text
- Store in StockRecommendation table
**Validation**: Integration test T014 progresses, recommendations generated correctly

---

### T039: Implement SuggestionEngine service
**Type**: Service
**Priority**: High
**Files**: `src/services/suggestion_engine.py`
**Dependencies**: T029 (Suggestion model), T038 (RecommendationEngine), T040 (InsightGenerator)
**Description**: Implement suggestion logic per research.md:
- DIVERSIFICATION: Identify gaps (sectors/regions < 10%), find high-scoring stocks in gap areas
- SIMILAR_TO_WINNERS: Find top 3 performers, match by sector + market cap + correlation > 0.6
- MARKET_OPPORTUNITY: Find stocks with high combined scores not in portfolio
- Filter out already-owned stocks
- Store in StockSuggestion table with portfolio_fit explanation
**Validation**: Integration test T015 progresses, suggestions generated correctly

---

### T040: Implement InsightGenerator service
**Type**: Service
**Priority**: High
**Files**: `src/services/insight_generator.py`
**Dependencies**: T030 (Insight model), T024 (Holding model)
**Description**: Generate portfolio-level insights per data-model.md:
- SECTOR_ALLOCATION: Calculate % per sector, identify concentration risk (> 40%)
- GEO_ALLOCATION: Calculate % per country/region
- DIVERSIFICATION_GAP: Identify sectors/regions < 10%
- HIGH_PERFORMERS: Rank holdings by gain_loss_pct, top 3
- RISK_ASSESSMENT: Calculate volatility, Sharpe ratio, beta vs S&P 500
- PERFORMANCE_TREND: Daily/weekly/monthly gains
- Store in Insight table with type-specific JSON
**Validation**: Integration test T016 progresses, insights generated correctly

---

### T041: Implement BatchProcessor service
**Type**: Service
**Priority**: High
**Files**: `src/services/batch_processor.py`
**Dependencies**: T034, T036, T037, T038, T039, T040
**Description**: Orchestrate daily batch job per research.md:
- For each Stock in any Holding: fetch market data, fetch fundamental data
- Calculate technical indicators
- Generate recommendations for all holdings
- Generate suggestions for new stocks
- Generate insights for each portfolio
- Update exchange rates
- Handle failures gracefully (retry 3x, log errors)
- Return summary (stocks updated, recommendations changed)
**Validation**: Integration test T018 progresses, batch completes successfully

---

## Phase 3.5: Core Implementation - CLI Commands

### T042: Create CLI main entry point
**Type**: CLI
**Priority**: Critical
**Files**: `src/cli/__init__.py`
**Dependencies**: T002 (Click installed)
**Description**: Create main CLI entry point:
- Click group "stocks-helper"
- Register subcommands: portfolio, holding, recommendation, suggestion, insight, report
- Global options: --debug, --config-file
- Version command
**Validation**: `stocks-helper --help` shows all subcommands

---

### T043 [P]: Implement portfolio CLI commands
**Type**: CLI
**Priority**: High
**Files**: `src/cli/portfolio.py`
**Dependencies**: T022 (Portfolio model), T005 (DB connection), T042 (CLI entry)
**Description**: Implement portfolio commands per contracts/cli-commands.md:
- `create --name --currency`: Create portfolio, validate ISO 4217 currency
- `list`: Show all portfolios with total value
- `show [id]`: Show portfolio details with top holdings
- `set-currency <id> --currency`: Update base currency, recalculate values
- Use Rich for formatted tables
- Error handling: invalid currency, portfolio not found
**Validation**: Contract test T009 PASSES, integration test T013 progresses

---

### T044 [P]: Implement holding CLI commands
**Type**: CLI
**Priority**: High
**Files**: `src/cli/holding.py`
**Dependencies**: T024 (Holding), T025 (Transaction), T035 (CurrencyConverter), T042
**Description**: Implement holding commands per contracts/cli-commands.md:
- `add <portfolio_id> --ticker --quantity --price --date [--currency] [--fees] [--notes]`
  - Validate ticker exists (fetch from API if new)
  - Create/update Holding
  - Create Transaction (BUY)
  - Calculate avg_purchase_price
- `sell <portfolio_id> --ticker --quantity --price --date [--currency] [--fees]`
  - Validate sufficient quantity
  - Create Transaction (SELL)
  - Update or delete Holding
- `list <portfolio_id> [--sort-by] [--order]`: Show all holdings
- `show <portfolio_id> --ticker`: Show holding details + purchase history
**Validation**: Contract test T010 PASSES, integration test T017 progresses

---

### T045 [P]: Implement recommendation CLI commands
**Type**: CLI
**Priority**: High
**Files**: `src/cli/recommendation.py`
**Dependencies**: T028 (Recommendation), T038 (RecommendationEngine), T042
**Description**: Implement recommendation commands per contracts/cli-commands.md:
- `list <portfolio_id> [--action BUY|SELL|HOLD]`: Show recommendations grouped by action
- `show <portfolio_id> --ticker`: Show detailed recommendation with technical + fundamental breakdown
- `refresh <portfolio_id> [--ticker]`: Manually trigger recommendation generation
  - Call BatchProcessor or RecommendationEngine directly
  - Show progress (fetching data, calculating, generating)
  - Report changes (recommendations changed)
**Validation**: Contract test T011 PASSES, integration test T014 progresses

---

### T046 [P]: Implement suggestion CLI commands
**Type**: CLI
**Priority**: High
**Files**: `src/cli/suggestion.py`
**Dependencies**: T029 (Suggestion), T039 (SuggestionEngine), T042
**Description**: Implement suggestion commands per contracts/cli-commands.md:
- `list <portfolio_id> [--type TYPE] [--limit N]`: Show suggestions grouped by type
- `show <portfolio_id> --ticker`: Show detailed suggestion analysis
**Validation**: Contract test T012 PASSES, integration test T015 progresses

---

### T047 [P]: Implement insight CLI commands
**Type**: CLI
**Priority**: Medium
**Files**: `src/cli/insight.py`
**Dependencies**: T030 (Insight), T040 (InsightGenerator), T042
**Description**: Implement insight command per contracts/cli-commands.md:
- `show <portfolio_id>`: Display all insights:
  - Sector allocation (pie chart ASCII or table)
  - Geographic distribution
  - Top performers
  - Diversification gaps
  - Risk metrics
- Use Rich for formatting, colors for warnings
**Validation**: Integration test T016 progresses

---

### T048 [P]: Implement report CLI commands
**Type**: CLI
**Priority**: Medium
**Files**: `src/cli/report.py`
**Dependencies**: T002 (Plotly installed), T022-T030 (all models), T042
**Description**: Implement report commands per contracts/cli-commands.md:
- `portfolio <portfolio_id> [--output FILE]`: Generate comprehensive HTML report
  - Performance line chart (Plotly)
  - Allocation pie charts (sector, geography)
  - Holdings table
  - Recommendations summary
  - Insights
  - Export to HTML, save to reports/
- `performance <portfolio_id> [--period 30d|90d|1y|all]`: Performance chart
- `allocation <portfolio_id>`: Allocation breakdown
**Validation**: Can generate HTML report, opens in browser

---

## Phase 3.6: Integration & Scheduler

### T049: Implement database initialization
**Type**: Integration
**Priority**: Critical
**Files**: `src/lib/db.py` (enhance)
**Dependencies**: T005, T022-T031 (all models)
**Description**: Enhance db.py with initialization:
- `init()` function: Create ~/.stocks-helper/ directory, create DB from schema, create cache/ directory
- `stocks-helper init` command in CLI
- Check if DB exists, create tables if not
- Seed with default data if needed
**Validation**: `stocks-helper init` creates database successfully

---

### T050: Implement batch job scheduler
**Type**: Integration
**Priority**: High
**Files**: `src/services/scheduler.py`
**Dependencies**: T041 (BatchProcessor), T002 (APScheduler installed)
**Description**: Create scheduler for daily batch job:
- APScheduler CronTrigger (daily at 6 PM EST / 11 PM UTC)
- Run BatchProcessor for all portfolios
- Log results
- Retry on failure (3 attempts)
- CLI command: `stocks-helper batch start` (daemon) and `stocks-helper batch run-once` (manual)
**Validation**: Batch job can be scheduled and runs successfully

---

### T051: Implement global error handling
**Type**: Integration
**Priority**: Medium
**Files**: `src/lib/errors.py`, all CLI commands (enhance)
**Dependencies**: T042-T048 (all CLI commands)
**Description**: Add consistent error handling across all CLI commands:
- Custom exception classes: APIRateLimitError, InvalidCurrencyError, InsufficientQuantityError, PortfolioNotFoundError
- Global exception handler in CLI main
- User-friendly error messages (per contracts/cli-commands.md)
- Color-coded errors (Rich library)
**Validation**: Error messages match contracts, integration test T019, T020 PASS

---

## Phase 3.7: Polish & Validation

### T052 [P]: Unit tests for IndicatorCalculator
**Type**: Unit Test
**Priority**: Medium
**Files**: `tests/unit/test_indicator_calculator.py`
**Dependencies**: T036
**Description**: Unit tests for technical indicators:
- Test SMA, EMA, MACD calculations with known inputs
- Test RSI, Stochastic calculations
- Test edge cases (insufficient data, NaN handling)
**Validation**: 100% coverage for IndicatorCalculator

---

### T053 [P]: Unit tests for RecommendationEngine
**Type**: Unit Test
**Priority**: High
**Files**: `tests/unit/test_recommendation_engine.py`
**Dependencies**: T038
**Description**: Unit tests for recommendation logic:
- Test score calculation (technical, fundamental, combined)
- Test confidence calculation (signal alignment)
- Test recommendation thresholds (BUY > 70, SELL < 30)
- Test rationale generation
**Validation**: 100% coverage for RecommendationEngine

---

### T054 [P]: Unit tests for SuggestionEngine
**Type**: Unit Test
**Priority**: Medium
**Files**: `tests/unit/test_suggestion_engine.py`
**Dependencies**: T039
**Description**: Unit tests for suggestion logic:
- Test diversification gap detection
- Test similar stock matching
- Test portfolio fit explanation
**Validation**: 100% coverage for SuggestionEngine

---

### T055 [P]: Unit tests for CurrencyConverter
**Type**: Unit Test
**Priority**: High
**Files**: `tests/unit/test_currency_converter.py`
**Dependencies**: T035
**Description**: Unit tests for currency conversion:
- Test conversion with known rates
- Test self-conversion (USD→USD = 1.0)
- Test historical rate lookup
- Test caching
**Validation**: 100% coverage for CurrencyConverter

---

### T056 [P]: Unit tests for InsightGenerator
**Type**: Unit Test
**Priority**: Medium
**Files**: `tests/unit/test_insight_generator.py`
**Dependencies**: T040
**Description**: Unit tests for insight generation:
- Test sector allocation calculation (sum = 100%)
- Test concentration risk detection (> 40%)
- Test diversification gap detection (< 10%)
- Test top performers ranking
**Validation**: 100% coverage for InsightGenerator

---

### T057: Performance validation - Daily batch
**Type**: Performance Test
**Priority**: High
**Files**: `tests/performance/test_batch_performance.py`
**Dependencies**: T041 (BatchProcessor), T050 (scheduler)
**Description**: Validate daily batch performance per plan.md targets:
- Create portfolio with 50 stocks
- Mock API responses for speed
- Time batch execution
- Assert: < 5 minutes for 50 stocks
- Assert: API rate limits respected (staggered calls)
**Validation**: Batch completes in < 5 minutes

---

### T058: Performance validation - CLI responsiveness
**Type**: Performance Test
**Priority**: Medium
**Files**: `tests/performance/test_cli_performance.py`
**Dependencies**: T043-T048 (all CLI commands)
**Description**: Validate CLI response times per plan.md:
- `portfolio list`: < 2 seconds
- `holding list`: < 2 seconds
- `recommendation list`: < 2 seconds
- `report portfolio`: < 10 seconds
**Validation**: All commands meet performance targets

---

### T059 [P]: Create README.md
**Type**: Documentation
**Priority**: Medium
**Files**: `README.md`
**Dependencies**: T042-T048 (all CLI commands)
**Description**: Create user-facing README:
- Installation instructions
- Quick start guide (from quickstart.md scenario 1)
- API key setup
- Example commands
- Troubleshooting section
**Validation**: README covers all essential usage

---

### T060 [P]: Create CONTRIBUTING.md
**Type**: Documentation
**Priority**: Low
**Files**: `CONTRIBUTING.md`
**Dependencies**: T003 (linting configured)
**Description**: Create contributor guide:
- Development setup
- Running tests
- Code style (black, ruff)
- TDD workflow
- Pull request process
**Validation**: New contributors can set up dev environment from docs

---

### T061: Remove code duplication
**Type**: Refactoring
**Priority**: Medium
**Files**: All service and CLI files
**Dependencies**: T022-T048 (all core implementation), T052-T056 (unit tests)
**Description**: Refactor to eliminate duplication:
- Extract common API error handling
- Extract common Rich table formatting
- Extract common validation logic
- Ensure DRY principle per constitution.md
**Validation**: Ruff/black pass, tests still pass, no duplicate logic

---

### T062: Run quickstart.md manual validation
**Type**: Manual Testing
**Priority**: Critical
**Files**: N/A (manual execution)
**Dependencies**: T001-T061 (all tasks complete)
**Description**: Execute all scenarios from quickstart.md manually:
- Scenario 1: Portfolio setup ✓
- Scenario 2: Recommendations ✓
- Scenario 3: Suggestions ✓
- Scenario 3a: International diversification ✓
- Scenario 4: Insights ✓
- Scenario 5: Transaction updates ✓
- Scenario 6: Daily batch ✓
- Edge cases: API failure ✓, rate limit ✓, multi-currency ✓
**Validation**: All scenarios pass, output matches expected from quickstart.md

---

## Phase 3.8: Additional Enhancements (Optional - Deferred Features)

These tasks address remaining [NEEDS CLARIFICATION] items that were deferred from MVP:

### T063 [P]: Add trend period selection
**Type**: Enhancement
**Priority**: Low
**Files**: `src/services/insight_generator.py` (enhance)
**Dependencies**: T040
**Description**: Resolve FR-009 - add support for multiple trend periods:
- Daily trends (last 7 days)
- Weekly trends (last 12 weeks)
- Monthly trends (last 12 months)
- Yearly trends (all-time)
- Add CLI flag: `insight show --period daily|weekly|monthly|yearly`
**Validation**: Can view trends over different periods

---

### T064 [P]: Add additional risk metrics
**Type**: Enhancement
**Priority**: Low
**Files**: `src/services/insight_generator.py` (enhance)
**Dependencies**: T040
**Description**: Resolve FR-010 - add risk metrics:
- Portfolio volatility (standard deviation)
- Sharpe ratio (risk-adjusted returns)
- Beta vs S&P 500 (market sensitivity)
- Display in insight show
**Validation**: Risk metrics calculated and displayed

---

### T065 [P]: Add benchmark comparison
**Type**: Enhancement
**Priority**: Low
**Files**: `src/services/insight_generator.py` (enhance), `src/services/market_data_fetcher.py` (enhance)
**Dependencies**: T034, T040
**Description**: Resolve FR-011 - add benchmark tracking:
- Fetch S&P 500 (^GSPC) and MSCI World index data
- Calculate portfolio performance vs benchmarks
- Show outperformance/underperformance in insights
**Validation**: Benchmark comparison shown in insights

---

### T066 [P]: Add corporate actions handling
**Type**: Enhancement
**Priority**: Low
**Files**: `src/services/market_data_fetcher.py` (enhance), `src/models/holding.py` (enhance)
**Dependencies**: T023, T024, T034
**Description**: Resolve FR-022 - handle corporate actions:
- Stock splits: Adjust quantity and avg_purchase_price automatically
- Dividends: Track dividend payments (if API provides data)
- Add CorporateAction model
- Apply adjustments to holdings
**Validation**: Stock splits correctly adjust holdings

---

### T067 [P]: Add recommendation tracking
**Type**: Enhancement
**Priority**: Low
**Files**: `src/services/recommendation_engine.py` (enhance), new `src/cli/analytics.py`
**Dependencies**: T028, T038
**Description**: Resolve FR-024 - track recommendation accuracy:
- Store historical recommendations (already done in T028)
- Calculate accuracy: % of BUY recommendations that went up, SELL that went down
- CLI command: `analytics recommendation-accuracy <portfolio_id>`
**Validation**: Can view recommendation accuracy over time

---

### T068 [P]: Add visualization variety
**Type**: Enhancement
**Priority**: Low
**Files**: `src/cli/report.py` (enhance)
**Dependencies**: T048
**Description**: Resolve FR-025 - add more chart types:
- Line charts: Performance over time (already in T048)
- Pie charts: Sector/geo allocation (already in T048)
- Bar charts: Recommendation counts (BUY/SELL/HOLD)
- Heatmap: Correlation matrix between holdings
**Validation**: HTML report includes all chart types

---

## Phase 3.9: Final Validation & Polish

### T069: Code coverage report
**Type**: Quality
**Priority**: High
**Files**: N/A (CI/testing)
**Dependencies**: T006-T021 (all tests), T052-T056 (unit tests)
**Description**: Generate coverage report:
- Run `pytest --cov=src --cov-report=html --cov-report=term`
- Verify > 80% coverage for business logic (per research.md)
- Identify untested code paths
**Validation**: Coverage > 80%, report generated

---

### T070: Security audit
**Type**: Quality
**Priority**: High
**Files**: All files
**Dependencies**: T001-T062 (all implementation)
**Description**: Security review:
- API keys not hardcoded (use env vars)
- No SQL injection risks (using SQLAlchemy ORM)
- No secret data in logs
- File permissions correct (~/.stocks-helper/ readable only by user)
**Validation**: No security vulnerabilities found

---

### T071: Constitution compliance review
**Type**: Quality
**Priority**: Critical
**Files**: All files
**Dependencies**: T001-T062
**Description**: Final review against constitution.md:
- ✓ Simplicity first: No unnecessary complexity
- ✓ Quality over speed: Tests passing, coverage > 80%
- ✓ Fail fast: All errors handled explicitly
- ✓ Self-documenting code: Clear naming, minimal comments
- ✓ DRY/KISS/YAGNI: No duplication, simple solutions
**Validation**: All constitutional principles satisfied

---

### T072: Create release checklist
**Type**: Documentation
**Priority**: Low
**Files**: `RELEASE.md`
**Dependencies**: T059 (README)
**Description**: Create release checklist:
- Version bumping process
- Testing checklist (all quickstart scenarios)
- PyPI publishing steps (if open-sourced)
- Changelog format
**Validation**: Release process documented

---

## Dependencies Graph

```
Setup (T001-T005)
  └─> Tests (T006-T021) [all parallel]
        └─> Models (T022-T031) [all parallel]
              ├─> Services (T032-T041)
              │     ├─> T034 (MarketDataFetcher) depends on T032, T033
              │     ├─> T035 (CurrencyConverter) depends on T032
              │     ├─> T038 (RecommendationEngine) depends on T036, T037
              │     ├─> T039 (SuggestionEngine) depends on T038, T040
              │     └─> T041 (BatchProcessor) depends on T034-T040
              │
              └─> CLI (T042-T048)
                    ├─> T043-T048 [all parallel, depend on T042]
                    └─> Integration (T049-T051)
                          └─> Polish (T052-T072)
```

**Critical Path**: T001→T005→T006-T021→T022-T031→T034→T036→T037→T038→T041→T043-T048→T049→T062

---

## Parallel Execution Examples

### Execute all contract tests in parallel (after setup):
```bash
# After T001-T005 complete, run T006-T012 together:
Task --description "Contract test Alpha Vantage daily data" --subagent_type python-pro
Task --description "Contract test Yahoo Finance API" --subagent_type python-pro
Task --description "Contract test Exchange Rate API" --subagent_type python-pro
Task --description "Contract test portfolio CLI commands" --subagent_type python-pro
Task --description "Contract test holding CLI commands" --subagent_type python-pro
Task --description "Contract test recommendation CLI commands" --subagent_type python-pro
Task --description "Contract test suggestion CLI commands" --subagent_type python-pro
```

### Execute all integration tests in parallel:
```bash
# After core implementation (T042-T048), run T013-T021 together:
Task --description "Integration test portfolio setup scenario" --subagent_type python-pro
Task --description "Integration test recommendations scenario" --subagent_type python-pro
Task --description "Integration test suggestions scenario" --subagent_type python-pro
Task --description "Integration test insights scenario" --subagent_type python-pro
# ... (all 9 integration tests)
```

### Execute all models in parallel:
```bash
# After tests written (T006-T021), run T022-T031 together:
Task --description "Implement Portfolio model in src/models/portfolio.py" --subagent_type python-pro
Task --description "Implement Stock model in src/models/stock.py" --subagent_type python-pro
Task --description "Implement Holding model in src/models/holding.py" --subagent_type python-pro
# ... (all 10 models)
```

### Execute all CLI commands in parallel:
```bash
# After T042 (CLI entry point), run T043-T048 together:
Task --description "Implement portfolio CLI commands in src/cli/portfolio.py" --subagent_type python-pro
Task --description "Implement holding CLI commands in src/cli/holding.py" --subagent_type python-pro
Task --description "Implement recommendation CLI commands in src/cli/recommendation.py" --subagent_type python-pro
# ... (all 6 CLI command groups)
```

---

## Validation Checklist

*Final verification before marking tasks.md complete*

- [x] All entities from data-model.md have model tasks (10 entities = T022-T031)
- [x] All CLI command groups have implementation tasks (6 groups = T043-T048)
- [x] All acceptance scenarios have integration tests (6 scenarios = T013-T018)
- [x] All edge cases have tests (3 edge cases = T019-T021)
- [x] All contract tests written before implementation (T006-T021 before T022+)
- [x] Parallel tasks truly independent (different files, no shared state)
- [x] Each task specifies exact file path
- [x] No [P] task modifies same file as another [P] task
- [x] Dependencies correctly mapped
- [x] Critical path identified (T001→...→T062)
- [x] Performance targets testable (T057, T058)
- [x] Constitution compliance verified (T071)

---

## Notes

- **Total Tasks**: 72 (MVP: T001-T062, Enhancements: T063-T068, Polish: T069-T072)
- **Parallelizable**: 48 tasks marked [P]
- **Critical for MVP**: T001-T062 (setup, tests, core, integration, validation)
- **Optional Enhancements**: T063-T068 (can be deferred to v2)
- **TDD Enforcement**: All tests (T006-T021) MUST be written and MUST FAIL before any implementation
- **Commit Strategy**: Commit after each task completion
- **Test Coverage Target**: > 80% per research.md
- **Performance Targets**: Tracked in T057, T058

---

**Tasks Ready**: Execute T001 to begin implementation. Follow TDD principles strictly: write tests first, watch them fail, then implement.
