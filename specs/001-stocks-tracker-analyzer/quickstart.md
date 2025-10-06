# Quickstart Guide - Stocks Tracker & Analyzer

**Feature**: 001-stocks-tracker-analyzer
**Purpose**: Validate implementation against user acceptance scenarios
**Date**: 2025-10-05

---

## Prerequisites

- Python 3.11+ installed
- API keys configured:
  - Alpha Vantage API key (free tier): https://www.alphavantage.co/support/#api-key
  - (Optional) Exchange rate API key
- Environment variables set:
  ```bash
  export ALPHAVANTAGE_API_KEY=your_key_here
  ```

---

## Installation

```bash
# Clone repository
cd /Users/priitlaht/Repository/stocks-helper

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Verify installation
stocks-helper --version
```

---

## Acceptance Scenario 1: Portfolio Setup & Stock Entry

**Given** I am a new user
**When** I set up my portfolio and add stocks
**Then** I can view my holdings with current values

### Steps:

```bash
# 1. Create a portfolio
stocks-helper portfolio create --name "Main Portfolio" --currency USD

# Expected output: Portfolio created with ID

# 2. Add first stock purchase
stocks-helper holding add <PORTFOLIO_ID> \
  --ticker AAPL \
  --quantity 100 \
  --price 150.00 \
  --date 2024-03-15 \
  --currency USD

# Expected output: Purchase recorded, current value shown

# 3. Add second stock
stocks-helper holding add <PORTFOLIO_ID> \
  --ticker MSFT \
  --quantity 50 \
  --price 275.00 \
  --date 2024-03-20

# 4. View portfolio dashboard
stocks-helper portfolio show <PORTFOLIO_ID>

# Expected output:
# - Total portfolio value in USD
# - Individual holdings with current prices
# - Gain/loss for each stock
# - Overall portfolio performance
```

**Validation**:
- ✓ Portfolio created successfully
- ✓ Stocks added with correct quantities and prices
- ✓ Current values fetched from API (or cached data shown)
- ✓ Gain/loss calculated correctly

---

## Acceptance Scenario 2: Stock Recommendations

**Given** I have entered my stock holdings
**When** I request recommendations
**Then** I receive buy/sell/hold suggestions with rationale

### Steps:

```bash
# 1. Trigger recommendation generation (if not run by daily batch yet)
stocks-helper recommendation refresh <PORTFOLIO_ID>

# Expected output: Recommendations generated for all holdings

# 2. View all recommendations
stocks-helper recommendation list <PORTFOLIO_ID>

# Expected output: Table showing BUY/SELL/HOLD for each stock

# 3. View detailed recommendation for specific stock
stocks-helper recommendation show <PORTFOLIO_ID> --ticker AAPL

# Expected output:
# - Recommendation (BUY/SELL/HOLD)
# - Confidence level (HIGH/MEDIUM/LOW)
# - Technical analysis breakdown
# - Fundamental analysis breakdown
# - Combined score
# - Human-readable rationale
```

**Validation**:
- ✓ Recommendations generated for all holdings
- ✓ Each recommendation includes technical + fundamental analysis
- ✓ Confidence level based on signal alignment
- ✓ Rationale explains the recommendation clearly

---

## Acceptance Scenario 3: New Stock Suggestions

**Given** I want to diversify my portfolio
**When** I request new stock suggestions
**Then** I see diversification opportunities and similar winners

### Steps:

```bash
# 1. View portfolio insights to see gaps
stocks-helper insight show <PORTFOLIO_ID>

# Expected output: Sector allocation, diversification gaps identified

# 2. Get diversification suggestions
stocks-helper suggestion list <PORTFOLIO_ID> --type DIVERSIFICATION

# Expected output: Stocks from underrepresented sectors

# 3. Get similar-to-winners suggestions
stocks-helper suggestion list <PORTFOLIO_ID> --type SIMILAR_TO_WINNERS

# Expected output: Stocks similar to top performers (AAPL, MSFT)

# 4. View detailed suggestion
stocks-helper suggestion show <PORTFOLIO_ID> --ticker JNJ

# Expected output:
# - Technical + fundamental analysis
# - How it addresses portfolio gaps
# - Score and ranking
```

**Validation**:
- ✓ Diversification gaps correctly identified (e.g., 0% healthcare)
- ✓ Suggested stocks from gap sectors
- ✓ Similar stocks based on high performers
- ✓ Each suggestion explains portfolio fit

---

## Acceptance Scenario 3a: International Diversification

**Given** My portfolio is heavily weighted in US tech stocks
**When** The system analyzes diversification gaps
**Then** It suggests stocks from underrepresented sectors/regions

### Steps:

```bash
# 1. Add more US tech stocks to create imbalance
stocks-helper holding add <PORTFOLIO_ID> --ticker NVDA --quantity 30 --price 325.00 --date 2024-04-01
stocks-helper holding add <PORTFOLIO_ID> --ticker GOOGL --quantity 25 --price 140.00 --date 2024-04-05

# 2. View allocation
stocks-helper insight show <PORTFOLIO_ID>

# Expected output:
# - Technology sector: > 40% (HIGH concentration warning)
# - US geography: > 70%

# 3. Get diversification suggestions filtered by region
stocks-helper suggestion list <PORTFOLIO_ID> --type DIVERSIFICATION

# Expected output: Stocks from EU, Asia, non-tech sectors
# Examples: SAP (EU tech), TSM (Asia semiconductors), JNJ (US healthcare)
```

**Validation**:
- ✓ High concentration warning shown
- ✓ Suggestions include international stocks
- ✓ Suggestions include non-tech sectors

---

## Acceptance Scenario 4: Portfolio Insights

**Given** I have multiple stocks in my portfolio
**When** The system generates insights
**Then** I see meaningful analysis about composition, risk, and trends

### Steps:

```bash
# 1. View comprehensive insights
stocks-helper insight show <PORTFOLIO_ID>

# Expected output:
# - Sector allocation breakdown
# - Geographic distribution
# - Top performers (last 30 days)
# - Diversification gaps
# - Risk metrics (volatility, Sharpe ratio, beta)
# - Concentration warnings
```

**Validation**:
- ✓ Sector allocation calculated correctly (sum = 100%)
- ✓ Geographic distribution shown
- ✓ Top performers ranked by gain %
- ✓ Risk metrics calculated
- ✓ Warnings for high concentration (>40% in one sector)

---

## Acceptance Scenario 5: Transaction Update Flow

**Given** I add a new stock purchase
**When** The transaction is recorded
**Then** Portfolio metrics update immediately, recommendations refresh in daily batch

### Steps:

```bash
# 1. Check current portfolio value
stocks-helper portfolio show <PORTFOLIO_ID>
# Note: Total Value = $X

# 2. Add new purchase
stocks-helper holding add <PORTFOLIO_ID> \
  --ticker TSLA \
  --quantity 20 \
  --price 250.00 \
  --date 2025-10-05

# 3. Immediately check portfolio again
stocks-helper portfolio show <PORTFOLIO_ID>
# Note: Total Value = $X + (20 * current_TSLA_price)

# Expected: Portfolio value updated immediately

# 4. Check recommendations
stocks-helper recommendation show <PORTFOLIO_ID> --ticker TSLA

# Expected: Either recommendation exists (if batch ran) OR message:
# "Recommendation not yet generated. Next update: Tomorrow 06:00 AM"
```

**Validation**:
- ✓ Portfolio value updated immediately
- ✓ New holding appears in holdings list
- ✓ Recommendation status clearly communicated

---

## Acceptance Scenario 6: Daily Batch Update

**Given** Recommendations were last updated yesterday
**When** I view my portfolio today after the daily batch runs
**Then** I see fresh recommendations with updated timestamps

### Steps:

```bash
# Simulate: Run daily batch manually (normally runs via cron at 6 PM EST)
stocks-helper recommendation refresh <PORTFOLIO_ID>

# Expected output:
# - Fetching market data...
# - Calculating indicators...
# - Generating recommendations...
# - Updated: X stocks
# - Changes: Y recommendations changed

# View updated recommendations
stocks-helper recommendation list <PORTFOLIO_ID>

# Expected: Timestamp shows "updated X minutes ago" (recent)

# View specific recommendation
stocks-helper recommendation show <PORTFOLIO_ID> --ticker AAPL

# Expected:
# - "Generated: 2025-10-05 18:00:00 (5 minutes ago)"
# - "Next Update: Tomorrow at 06:00 PM"
```

**Validation**:
- ✓ All holdings processed
- ✓ Fresh market data fetched
- ✓ Recommendations have current timestamp
- ✓ Changed recommendations reported

---

## Edge Case Testing

### Test: API Unavailable

```bash
# Disconnect network or use invalid API key
export ALPHAVANTAGE_API_KEY=invalid

stocks-helper recommendation refresh <PORTFOLIO_ID>

# Expected output:
# ⚠️  Warning: Unable to fetch data from Alpha Vantage (API error)
# Trying fallback: Yahoo Finance...
# ✓ Data fetched from Yahoo Finance
```

**Validation**:
- ✓ Graceful fallback to Yahoo Finance
- ✓ Clear error messages
- ✓ Cached data used if all sources fail

---

### Test: API Rate Limit

```bash
# Make 26+ requests in a day (Alpha Vantage free tier limit: 25/day)
for i in {1..30}; do
  stocks-helper recommendation refresh <PORTFOLIO_ID>
done

# Expected output after 25th request:
# ⚠️  API rate limit reached (25 requests/day).
# Using cached data from X hours ago.
# Next update available in X hours.
```

**Validation**:
- ✓ Rate limit detected
- ✓ Cached data used
- ✓ Clear message about when next update is possible

---

### Test: Multi-Currency Portfolio

```bash
# Add European stock
stocks-helper holding add <PORTFOLIO_ID> \
  --ticker SAP \
  --quantity 50 \
  --price 120.00 \
  --currency EUR \
  --date 2025-10-01

# View portfolio
stocks-helper portfolio show <PORTFOLIO_ID>

# Expected output:
# - SAP: Value shown in EUR
# - SAP: Value converted to USD (base currency)
# - Total portfolio value in USD
# - Exchange rate attribution shown
```

**Validation**:
- ✓ Original currency preserved
- ✓ Automatic conversion to base currency
- ✓ Exchange rate applied correctly
- ✓ Both original and converted values shown

---

## Performance Validation

### Test: Daily Batch Performance

```bash
# Add 50 stocks to portfolio (near expected max)
# ... (bulk add commands)

# Time the batch update
time stocks-helper recommendation refresh <PORTFOLIO_ID>

# Expected: Complete in < 5 minutes
```

**Validation**:
- ✓ 50 stocks processed in < 5 minutes
- ✓ API rate limits respected (staggered calls)
- ✓ No errors or timeouts

---

### Test: CLI Responsiveness

```bash
# Test command response times
time stocks-helper portfolio list
# Expected: < 2 seconds

time stocks-helper holding list <PORTFOLIO_ID>
# Expected: < 2 seconds

time stocks-helper report portfolio <PORTFOLIO_ID>
# Expected: < 10 seconds (includes chart generation)
```

**Validation**:
- ✓ All CLI commands respond within target times
- ✓ No blocking operations in foreground

---

## Report Generation

### Test: HTML Portfolio Report

```bash
stocks-helper report portfolio <PORTFOLIO_ID> --output reports/my_portfolio.html

# Open in browser
open reports/my_portfolio.html

# Expected content:
# - Performance line chart (interactive Plotly)
# - Sector allocation pie chart
# - Holdings table with current values
# - Recommendations summary
# - Risk metrics
```

**Validation**:
- ✓ HTML file generated
- ✓ Charts render correctly in browser
- ✓ All data matches CLI output
- ✓ Responsive layout

---

## Success Criteria

All acceptance scenarios must pass:
- [x] Scenario 1: Portfolio setup and stock entry
- [x] Scenario 2: Stock recommendations with rationale
- [x] Scenario 3: New stock suggestions (diversification + similar winners)
- [x] Scenario 3a: International diversification
- [x] Scenario 4: Portfolio insights (allocation, risk, trends)
- [x] Scenario 5: Transaction update flow
- [x] Scenario 6: Daily batch update with fresh data

All edge cases handled gracefully:
- [x] API unavailable → fallback to Yahoo Finance or cached data
- [x] API rate limit → use cached data, inform user
- [x] Multi-currency → automatic conversion to base currency
- [x] Batch job failure → retry logic, user notification

Performance targets met:
- [x] Daily batch: < 5 minutes for 50 stocks
- [x] CLI commands: < 2 seconds
- [x] Report generation: < 10 seconds

---

## Troubleshooting

### Database not found
```bash
# Initialize database
stocks-helper init

# Expected: Creates ~/.stocks-helper/data.db
```

### API key not configured
```bash
# Set environment variable
export ALPHAVANTAGE_API_KEY=your_key_here

# Or create config file
echo "ALPHAVANTAGE_API_KEY=your_key_here" > ~/.stocks-helper/config
```

### Outdated data
```bash
# Force refresh
stocks-helper recommendation refresh <PORTFOLIO_ID>
```

---

**Quickstart Complete**: All user scenarios validated through CLI commands.
