# Implementation Plan: Personal Stocks Tracker & Analyzer

**JIRA Task**: N/A
**Branch**: `001-stocks-tracker-analyzer` | **Date**: 2025-10-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-stocks-tracker-analyzer/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → ✓ Loaded successfully
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → ✓ Project Type: Single (CLI tool)
   → ✓ Structure Decision: src/ + tests/ layout
3. Fill the Constitution Check section
   → ✓ Constitution loaded and evaluated
4. Evaluate Constitution Check section
   → ✓ PASS - No violations
   → ✓ Progress Tracking: Initial Constitution Check complete
5. Execute Phase 0 → research.md
   → ✓ research.md created with all decisions documented
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, AGENTS.md update
   → ✓ data-model.md created (10 entities, relationships, lifecycle)
   → ✓ contracts/cli-commands.md created (complete CLI specification)
   → ✓ quickstart.md created (all acceptance scenarios)
   → ✓ AGENTS.md created at project root
7. Re-evaluate Constitution Check section
   → ✓ PASS - Design adheres to constitutional principles
   → ✓ Progress Tracking: Post-Design Constitution Check complete
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
   → ✓ Task generation strategy documented below
9. STOP - Ready for /tasks command
   → ✓ Phase 0-1 complete, ready for /tasks
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

---

## Summary

Build a personal stocks tracker and analyzer CLI tool that:
- Tracks multi-currency stock portfolios with transaction history
- Fetches market data from free APIs (Alpha Vantage, Yahoo Finance)
- Generates buy/sell/hold recommendations using combined technical + fundamental analysis
- Suggests new stocks based on diversification gaps, similar high performers, and market opportunities
- Provides portfolio insights (allocation, risk metrics, performance trends)
- Runs daily batch updates for fresh recommendations
- Exports HTML reports with interactive charts

**Technical Approach**:
- Python 3.11+ CLI tool with Click framework
- SQLite database for portfolio data + API response caching
- TA-Lib + pandas-ta for technical indicators
- Rule-based recommendation engine (weighted scoring)
- Async API calls for efficient batch processing
- Plotly for HTML chart generation

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Click 8.x (CLI), Pandas (data), TA-Lib + pandas-ta (indicators), aiohttp (async HTTP), Plotly 5.x (charts)
**Storage**: SQLite 3.40+ (portfolio data + API cache)
**Testing**: pytest 7.x (contract + integration + unit tests)
**Target Platform**: macOS/Linux CLI (personal tool)
**Project Type**: Single (CLI application)
**Performance Goals**:
- Daily batch: < 5 minutes for 50 stocks
- CLI commands: < 2 seconds response
- Report generation: < 10 seconds
**Constraints**:
- Free API rate limits (Alpha Vantage: 25 req/day, 5 req/min)
- 15-minute delayed market data acceptable
- Single-user (no auth/multi-tenancy needed)
**Scale/Scope**:
- Personal portfolio (10-50 stocks expected)
- 2-year historical data retention
- < 1000 transactions expected

---

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ Initial Check (Before Phase 0)

| Principle | Evaluation | Status |
|-----------|------------|--------|
| **Simplicity First** | CLI tool, SQLite database, rule-based engine (no ML), proven libraries | ✅ PASS |
| **Quality Over Speed** | TDD approach planned, contract tests first, comprehensive test layers | ✅ PASS |
| **Fail Fast & Loud** | Explicit error handling for API failures, rate limits, invalid input | ✅ PASS |
| **Technology Constraints** | Single language (Python), < 3 projects (only 1: CLI tool) | ✅ PASS |
| **Proven Technology** | Python ecosystem (Click, pandas, TA-Lib), SQLite - all battle-tested | ✅ PASS |
| **Evidence-Based** | API choice based on verified capabilities, not assumptions | ✅ PASS |

**Complexity Check**:
- Projects in repo: 1 (CLI tool) - ✅ Under 3-project limit
- Languages: 1 (Python) - ✅ Under 2-language limit
- Abstraction layers: Direct DB access via SQLite ORM - ✅ No unnecessary layers
- Custom implementations: Using TA-Lib/pandas-ta instead of custom indicators - ✅ Prefer libraries

**Verdict**: ✅ **PASS** - All constitutional principles satisfied

---

### ✅ Post-Design Check (After Phase 1)

| Principle | Design Evaluation | Status |
|-----------|-------------------|--------|
| **Simplicity First** | Data model: 10 entities with clear relationships, no over-engineering | ✅ PASS |
| **Self-Documenting Code** | CLI commands designed with clear names, explicit error messages | ✅ PASS |
| **DRY** | Shared logic in services layer, reusable components (currency conversion, scoring) | ✅ PASS |
| **KISS** | Rule-based recommendation (no complex ML), straightforward scoring algorithm | ✅ PASS |
| **YAGNI** | Only features from spec, no speculative additions | ✅ PASS |
| **SRP** | Each service has single responsibility (MarketDataFetcher, RecommendationEngine, etc.) | ✅ PASS |

**Architecture Review**:
- ✅ Clear separation: models, services, CLI commands, utilities
- ✅ No unnecessary abstraction (direct SQLite, no repository pattern needed for single-user app)
- ✅ API fallback strategy (Alpha Vantage → Yahoo Finance → cached data) = pragmatic, not over-engineered
- ✅ Async for batch processing = justified by performance requirements (50 stocks in < 5 min)

**Verdict**: ✅ **PASS** - Design adheres to constitutional principles

---

## Project Structure

### Documentation (this feature)
```
specs/001-stocks-tracker-analyzer/
├── spec.md              # Feature specification (input)
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command) ✓
├── data-model.md        # Phase 1 output (/plan command) ✓
├── quickstart.md        # Phase 1 output (/plan command) ✓
├── contracts/           # Phase 1 output (/plan command) ✓
│   └── cli-commands.md  # CLI command specifications ✓
└── tasks.md             # Phase 2 output (/tasks command - NOT created yet)
```

### Source Code (repository root)
```
stocks-helper/
├── src/
│   ├── models/          # SQLite ORM models
│   │   ├── portfolio.py
│   │   ├── stock.py
│   │   ├── holding.py
│   │   ├── transaction.py
│   │   ├── market_data.py
│   │   ├── fundamental_data.py
│   │   ├── recommendation.py
│   │   ├── suggestion.py
│   │   ├── insight.py
│   │   └── exchange_rate.py
│   │
│   ├── services/        # Business logic
│   │   ├── market_data_fetcher.py    # API integration (Alpha Vantage, Yahoo Finance)
│   │   ├── currency_converter.py     # Exchange rate conversion
│   │   ├── indicator_calculator.py   # Technical indicators (TA-Lib wrapper)
│   │   ├── fundamental_analyzer.py   # Fundamental metrics extraction
│   │   ├── recommendation_engine.py  # Buy/sell/hold logic
│   │   ├── suggestion_engine.py      # New stock discovery
│   │   ├── insight_generator.py      # Portfolio-level analysis
│   │   └── batch_processor.py        # Daily batch job orchestration
│   │
│   ├── cli/             # Click commands
│   │   ├── __init__.py              # Main CLI entry point
│   │   ├── portfolio.py             # portfolio create/list/show/set-currency
│   │   ├── holding.py               # holding add/sell/list/show
│   │   ├── recommendation.py        # recommendation list/show/refresh
│   │   ├── suggestion.py            # suggestion list/show
│   │   ├── insight.py               # insight show
│   │   └── report.py                # report portfolio/performance/allocation
│   │
│   └── lib/             # Utilities
│       ├── db.py                    # SQLite connection and ORM setup
│       ├── api_client.py            # HTTP client with retry/caching
│       ├── cache.py                 # API response caching
│       ├── formatters.py            # Rich table formatting
│       └── constants.py             # API keys, thresholds, etc.
│
├── tests/
│   ├── contract/        # API contract tests
│   │   ├── test_alpha_vantage_api.py
│   │   ├── test_yahoo_finance_api.py
│   │   └── test_exchange_rate_api.py
│   │
│   ├── integration/     # End-to-end CLI tests
│   │   ├── test_portfolio_workflow.py
│   │   ├── test_recommendation_workflow.py
│   │   ├── test_suggestion_workflow.py
│   │   └── test_multi_currency.py
│   │
│   └── unit/            # Business logic tests
│       ├── test_indicator_calculator.py
│       ├── test_recommendation_engine.py
│       ├── test_suggestion_engine.py
│       ├── test_currency_converter.py
│       └── test_insight_generator.py
│
├── reports/             # Generated HTML reports (user data, not in git)
├── .venv/               # Virtual environment
├── pyproject.toml       # Dependencies and project config
├── README.md            # User-facing documentation
├── constitution.md      # Project constitution ✓
└── AGENTS.md            # Development guidelines ✓
```

**Structure Decision**: Single CLI application using standard Python project layout (src/ + tests/). No separate frontend/backend needed. This follows constitutional principle of simplicity - avoid multiple projects when one suffices.

---

## Phase 0: Outline & Research
**Status**: ✅ Complete

**Output**: [research.md](./research.md)

**Key Decisions Documented**:
1. **Language**: Python 3.11+ (strong financial/data ecosystem)
2. **APIs**: Alpha Vantage (primary) + Yahoo Finance (fallback) - free tier verified
3. **Storage**: SQLite + JSON cache (perfect for single-user, zero config)
4. **Technical Analysis**: TA-Lib + pandas-ta (industry standard, 200+ indicators)
5. **Recommendation Engine**: Rule-based weighted scoring (technical 50% + fundamental 50%)
6. **CLI Framework**: Click 8.x (best Python CLI library)
7. **Async Strategy**: asyncio + aiohttp for concurrent API calls (batch performance)
8. **Charts**: Plotly 5.x (HTML export, interactive)
9. **Scheduling**: APScheduler 3.x (Python-based cron alternative)
10. **Currency**: ExchangeRate-API or similar free service

**All NEEDS CLARIFICATION resolved**:
- FR-009: Trend periods → Daily, weekly, monthly, yearly (all supported)
- FR-010: Risk metrics → Volatility, Sharpe ratio, sector beta
- FR-011: Benchmarks → S&P 500 (US), MSCI World (international)
- FR-022: Corporate actions → Stock splits supported, dividends best-effort
- FR-024: Recommendation tracking → Yes, store historical for accuracy analysis
- FR-025: Visualizations → Line charts (performance), pie charts (allocation), bar charts (recommendations)

---

## Phase 1: Design & Contracts
**Status**: ✅ Complete

### Outputs Created:

1. **[data-model.md](./data-model.md)**: Complete data model
   - 10 core entities: Portfolio, Stock, Holding, Transaction, MarketData, FundamentalData, StockRecommendation, StockSuggestion, Insight, ExchangeRate
   - Entity relationships and foreign keys
   - Validation rules and constraints
   - JSON schemas for complex fields
   - Lifecycle examples (adding stock, daily batch)
   - Index strategy for performance

2. **[contracts/cli-commands.md](./contracts/cli-commands.md)**: Complete CLI specification
   - 20+ commands across 6 groups (portfolio, holding, recommendation, suggestion, insight, report)
   - Argument contracts with validation rules
   - Success/error output formats
   - Edge case handling (API errors, rate limits, multi-currency)
   - Rich formatting standards (colors, tables, symbols)

3. **[quickstart.md](./quickstart.md)**: Acceptance scenario validation
   - 6 main scenarios (from spec.md)
   - Step-by-step CLI commands for each scenario
   - Expected outputs and validation criteria
   - Edge case testing (API failures, rate limits, multi-currency)
   - Performance validation tests
   - Troubleshooting guide

4. **[AGENTS.md](../../../AGENTS.md)**: Development guidelines (project root)
   - Active technologies: Python 3.11+, Click, Pandas, TA-Lib, SQLite
   - Project structure reference
   - Common commands (dev setup, testing, batch jobs, DB management)
   - Code style conventions (naming, type hints, error handling, async patterns)
   - Recent changes log

---

## Phase 2: Task Planning Approach
**Status**: ✅ Planned (execution by /tasks command)

*This section describes what the /tasks command will do - DO NOT execute during /plan*

### Task Generation Strategy:

**Input Sources**:
1. Load `~/.ai/1_templates/tasks-template.md` as base structure
2. Extract entities from `data-model.md` (10 entities)
3. Extract CLI commands from `contracts/cli-commands.md` (20+ commands)
4. Extract test scenarios from `quickstart.md` (6 acceptance scenarios + edge cases)

**Task Categories**:

1. **Infrastructure Tasks** (Priority: Highest)
   - Setup: pyproject.toml, virtual env, database initialization
   - Database schema: Create tables, indexes, constraints
   - Configuration: API keys, environment variables

2. **Contract Test Tasks** [P] (TDD: Write first)
   - Alpha Vantage API contract tests
   - Yahoo Finance API contract tests
   - Exchange Rate API contract tests
   - CLI command contract tests (argument parsing, output format)

3. **Model Tasks** [P] (After contract tests)
   - Create SQLite ORM models for each entity (10 models)
   - Add validation rules
   - Add computed properties (e.g., gain/loss)

4. **Service Tasks** (After models)
   - MarketDataFetcher: API integration with retry/fallback
   - CurrencyConverter: Exchange rate fetching and caching
   - IndicatorCalculator: TA-Lib wrapper for technical indicators
   - FundamentalAnalyzer: Extract metrics from API responses
   - RecommendationEngine: Scoring algorithm and confidence calculation
   - SuggestionEngine: Diversification + similar-winners + market-opportunity logic
   - InsightGenerator: Portfolio-level analysis (allocation, risk, trends)
   - BatchProcessor: Daily job orchestration

5. **CLI Command Tasks** (After services)
   - Portfolio commands: create, list, show, set-currency
   - Holding commands: add, sell, list, show
   - Recommendation commands: list, show, refresh
   - Suggestion commands: list, show
   - Insight commands: show
   - Report commands: portfolio, performance, allocation

6. **Integration Test Tasks** (After CLI commands)
   - Scenario 1: Portfolio setup and stock entry
   - Scenario 2: Stock recommendations with rationale
   - Scenario 3: New stock suggestions
   - Scenario 3a: International diversification
   - Scenario 4: Portfolio insights
   - Scenario 5: Transaction update flow
   - Scenario 6: Daily batch update
   - Edge case: API unavailable
   - Edge case: API rate limit
   - Edge case: Multi-currency portfolio

7. **Reporting Tasks** (After integration tests)
   - HTML report generation with Plotly charts
   - Performance chart (line)
   - Allocation chart (pie)
   - Recommendations table

**Ordering Strategy**:
- **TDD order**: Contract tests → Models → Unit tests → Services → Integration tests → CLI → End-to-end tests
- **Dependency order**: Models before services, services before CLI, tests alongside each layer
- **Parallelizable tasks** marked with [P]: Multiple models, multiple contract tests, multiple CLI command groups

**Estimated Task Count**:
- Infrastructure: 5 tasks
- Contract tests: 10 tasks [P]
- Models: 10 tasks [P]
- Services: 8 tasks
- CLI commands: 15 tasks (5 groups × 3 commands each)
- Integration tests: 12 tasks
- Reporting: 3 tasks
- **Total: ~63 tasks**

**Task Format Example**:
```
### Task 001: Create pyproject.toml with dependencies
**Type**: Infrastructure
**Priority**: High
**Depends On**: None
**Parallelizable**: Yes [P]
**Description**: Create pyproject.toml with all dependencies from research.md
**Files**: pyproject.toml
**Tests**: None (setup task)
**Validation**: pip install -e . succeeds
```

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

---

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md with ~63 ordered tasks)
**Phase 4**: Implementation (execute tasks.md following TDD and constitutional principles)
**Phase 5**: Validation (run all tests, execute quickstart.md scenarios, performance validation)

---

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

**No violations found** - this section is empty.

---

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command) ✓
- [x] Phase 1: Design complete (/plan command) ✓
- [x] Phase 2: Task planning complete (/plan command - approach described) ✓
- [ ] Phase 3: Tasks generated (/tasks command) - NEXT STEP
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS ✓
- [x] Post-Design Constitution Check: PASS ✓
- [x] All NEEDS CLARIFICATION resolved ✓
- [x] Complexity deviations documented (N/A - no deviations) ✓

**Artifacts Generated**:
- [x] constitution.md (project root) ✓
- [x] research.md ✓
- [x] data-model.md ✓
- [x] contracts/cli-commands.md ✓
- [x] quickstart.md ✓
- [x] AGENTS.md (project root) ✓
- [x] plan.md (this file) ✓

---

## Next Steps

**Ready for**: `/tasks` command

The /plan phase is complete. All design artifacts generated and validated against constitutional principles.

To proceed:
```bash
/tasks
```

This will:
1. Load tasks-template.md
2. Generate ~63 ordered, dependency-aware tasks from Phase 1 design documents
3. Create `specs/001-stocks-tracker-analyzer/tasks.md`
4. Mark parallelizable tasks with [P]
5. Include validation criteria for each task

---

*Based on Constitution - See `constitution.md` at project root*
