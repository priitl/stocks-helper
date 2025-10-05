# Phase 0: Technical Research - Stocks Tracker & Analyzer

**Feature**: Personal Stocks Tracker & Analyzer
**Date**: 2025-10-05

## Research Overview

This document resolves technical unknowns and establishes the technology stack for the stocks tracker/analyzer feature.

---

## 1. Language & Runtime Selection

### Decision: **Python 3.11+**

**Rationale**:
- Strong ecosystem for financial data analysis (pandas, numpy)
- Excellent API client libraries for stock market data
- Fast development for personal tools
- Good support for data visualization
- Async capabilities for batch processing

**Alternatives Considered**:
- **JavaScript/TypeScript**: Better for web apps, but weaker financial libraries
- **Go**: Better performance, but smaller data science ecosystem
- **Rust**: Best performance, but slower development for data-heavy app

---

## 2. Free Stock Market Data APIs

### Decision: **Multi-source strategy**
1. **Primary**: Alpha Vantage (free tier: 25 requests/day, 5 requests/minute)
2. **Fallback**: Yahoo Finance (yfinance library, unofficial but widely used)
3. **Currency**: Exchange Rates API or similar for FX conversion

**Rationale**:
- Alpha Vantage: Official API, reliable, supports international markets
- Yahoo Finance: Good backup, real-time-ish data, no API key required
- Fallback strategy handles API failures and rate limits
- Combined approach maximizes free tier benefits

**API Capabilities Verified**:
- ✅ US stocks (NYSE, NASDAQ)
- ✅ International markets (LSE, Euronext, major Asian exchanges)
- ✅ Historical price data
- ✅ Fundamental data (P/E, earnings, market cap)
- ✅ Technical indicators (moving averages, RSI, MACD)
- ⚠️ Corporate actions: Splits available, dividends limited
- ✅ Currency exchange rates

**Rate Limit Strategy**:
- Cache all API responses with TTL
- Daily batch: Run during off-peak hours
- Stagger API calls (1 per 15 seconds for Alpha Vantage)
- Persist data locally to minimize API calls

---

## 3. Storage Solution

### Decision: **SQLite + JSON files**

**Rationale**:
- **SQLite**: Perfect for single-user app, zero-configuration, ACID compliance
- **JSON files**: Cache API responses, easy inspection/debugging
- Lightweight, no database server required
- Easy backup (copy files)
- Sufficient for personal portfolio (< 1000 transactions expected)

**Schema Strategy**:
- Normalized schema for portfolio data (portfolios, holdings, transactions)
- Separate cache database for API responses (TTL-based cleanup)
- Full-text search for stock ticker lookup

**Alternatives Considered**:
- **PostgreSQL**: Overkill for single user, requires server
- **Files only**: No relational queries, harder to maintain consistency

---

## 4. Technical Analysis Library

### Decision: **TA-Lib (via ta-lib Python wrapper) + pandas-ta**

**Rationale**:
- **TA-Lib**: Industry standard, 200+ technical indicators, battle-tested
- **pandas-ta**: Pure Python, easier install, good complement
- Combined approach: TA-Lib for complex indicators, pandas-ta for simple ones

**Key Indicators Selected** (based on clarifications):
- **Trend**: Moving Averages (SMA, EMA), MACD
- **Momentum**: RSI, Stochastic Oscillator
- **Volatility**: Bollinger Bands, ATR
- **Volume**: OBV (On-Balance Volume)

**Alternatives Considered**:
- **Custom implementation**: Too time-consuming, error-prone
- **Pandas-ta only**: Missing some advanced indicators

---

## 5. Fundamental Analysis Metrics

### Decision: **Key metrics from API data + custom calculations**

**Metrics Prioritized**:
1. **Valuation**: P/E ratio, P/B ratio, PEG ratio
2. **Profitability**: ROE, ROA, profit margins
3. **Growth**: Revenue growth (YoY), earnings growth
4. **Financial Health**: Debt-to-equity, current ratio
5. **Dividends**: Dividend yield, payout ratio (if available)

**Scoring Approach**:
- Multi-factor model: Weight each metric
- Sector-relative scoring (compare within sector)
- Combine with technical signals for final recommendation

---

## 6. Recommendation Engine Design

### Decision: **Rule-based system with weighted scoring**

**Technical Signal Weights**:
- Trend indicators: 30%
- Momentum indicators: 25%
- Volatility indicators: 15%
- Volume indicators: 10%

**Fundamental Signal Weights**:
- Valuation: 30%
- Growth: 25%
- Profitability: 20%
- Financial health: 15%
- Dividends: 10%

**Confidence Calculation**:
- **High**: Technical and fundamental agree (both buy or both sell) - score > 75%
- **Medium**: Signals mostly aligned - score 50-75%
- **Low**: Signals conflict or weak - score < 50%

**Recommendation Thresholds**:
- **Buy**: Combined score > 70 and confidence >= Medium
- **Sell**: Combined score < 30 and confidence >= Medium
- **Hold**: All other cases

**Alternatives Considered**:
- **Machine Learning**: Too complex for MVP, needs training data
- **Pure technical**: Ignores fundamentals (violates clarifications)
- **Pure fundamental**: Ignores market trends (violates clarifications)

---

## 7. Daily Batch Processing

### Decision: **Async Python script + cron/scheduler**

**Architecture**:
- Async/await for concurrent API calls
- Process portfolio holdings in parallel (respecting rate limits)
- Update prices → Calculate indicators → Generate recommendations
- Store results with timestamp

**Scheduling**:
- Run after market close (6 PM EST / 11 PM UTC)
- Retry logic: 3 attempts with exponential backoff
- Email/log on failure

**Libraries**:
- `asyncio` for concurrency
- `aiohttp` for async HTTP
- `apscheduler` for scheduling (alternative to cron)

---

## 8. Currency Conversion

### Decision: **Exchange rates API + daily caching**

**Strategy**:
- Fetch exchange rates once daily
- Cache rates in SQLite
- Historical rates: Store transaction-time rate for accurate gain/loss
- Base currency: User-selectable, default USD

**API**: ExchangeRate-API or similar free service

---

## 9. Portfolio Diversification Analysis

### Decision: **Sector/Geography allocation + concentration metrics**

**Calculations**:
1. **Sector allocation**: % of portfolio in each sector
2. **Geographic allocation**: % in US, EU, Asia, etc.
3. **Concentration risk**: Top 5 holdings as % of total
4. **Diversification gaps**: Underrepresented sectors/regions (< 10% threshold)

**Suggestion Logic**:
- Identify gaps (sectors/regions < 10%)
- Find high-scoring stocks in gap areas
- Filter by market cap and liquidity

---

## 10. Similar Stock Discovery

### Decision: **Feature-based similarity matching**

**Similarity Factors**:
1. Same sector (required)
2. Similar market cap (±50%)
3. Similar performance profile (correlation > 0.6)
4. Geographic region

**Algorithm**:
- Identify top 3 performing stocks in portfolio
- Find stocks matching similarity criteria
- Rank by combined technical + fundamental score
- Filter out already-owned stocks

---

## 11. User Interface

### Decision: **CLI + Web Dashboard (Phase 1: CLI only)**

**MVP (Phase 1)**:
- **CLI tool** for portfolio management (add/remove stocks, view reports)
- **Static HTML reports** generated from data (charts via matplotlib/plotly)

**Future (Phase 2)**:
- **Web dashboard** (FastAPI + React/Vue)
- Real-time updates via WebSockets

**Rationale**:
- CLI faster to build for personal use
- Static reports sufficient for daily review
- Web UI deferred to avoid scope creep

**Libraries**:
- `click` for CLI framework
- `rich` for formatted terminal output
- `plotly` for charts (exports to HTML)

---

## 12. Testing Strategy

### Decision: **Contract tests + Integration tests + Unit tests**

**Test Layers**:
1. **Contract tests**: API response schemas (Alpha Vantage, Yahoo Finance)
2. **Integration tests**: End-to-end portfolio scenarios (add stock → view recommendations)
3. **Unit tests**: Calculation logic (indicators, scoring, currency conversion)

**Framework**: `pytest` (standard for Python)

**Coverage target**: > 80% for business logic

---

## 13. Performance Goals

### Decision: **Personal-scale performance**

**Targets**:
- Daily batch: Complete in < 5 minutes for 50 stocks
- CLI commands: Respond in < 2 seconds
- Report generation: < 10 seconds for full portfolio

**Optimization Strategy**:
- Async API calls (parallel fetching)
- Cache all API responses
- Lazy-load data in CLI
- Batch database operations

---

## Technology Stack Summary

| Category | Choice | Version |
|----------|--------|---------|
| **Language** | Python | 3.11+ |
| **Data APIs** | Alpha Vantage + Yahoo Finance | Latest |
| **Database** | SQLite | 3.40+ |
| **Technical Analysis** | TA-Lib + pandas-ta | Latest |
| **Data Processing** | Pandas + NumPy | Latest |
| **CLI Framework** | Click | 8.x |
| **Terminal UI** | Rich | 13.x |
| **Async** | asyncio + aiohttp | stdlib + 3.x |
| **Charts** | Plotly | 5.x |
| **Testing** | pytest | 7.x |
| **Scheduling** | APScheduler | 3.x |

---

## Open Questions Resolved

| Question | Resolution |
|----------|------------|
| Trend time periods (FR-009) | Daily, weekly, monthly, yearly - all available |
| Risk metrics (FR-010) | Volatility, Sharpe ratio, sector beta |
| Benchmarks (FR-011) | S&P 500 (US), MSCI World (international) |
| Corporate actions (FR-022) | Stock splits supported, dividends best-effort |
| Recommendation tracking (FR-024) | Yes - store historical recommendations for accuracy tracking |
| Visualizations (FR-025) | Line charts (performance), pie charts (allocation), bar charts (recommendations) |

---

## Constitutional Compliance

✅ **Simplicity First**: CLI tool, SQLite, rule-based engine (no ML complexity)
✅ **Proven Technology**: Python ecosystem, established libraries
✅ **Quality Over Speed**: TDD approach, contract tests first
✅ **Fail Fast**: Explicit error handling for API failures, rate limits
✅ **Evidence-Based**: Free API choice based on capabilities, not assumptions

---

**Phase 0 Complete**: All technical unknowns resolved. Ready for Phase 1 design.
