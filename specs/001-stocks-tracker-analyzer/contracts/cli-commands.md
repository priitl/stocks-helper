# CLI Command Contracts - Stocks Tracker

**Type**: Command-Line Interface
**Framework**: Click (Python)
**Date**: 2025-10-05

---

## Command Structure

```
stocks-helper
├── portfolio
│   ├── create
│   ├── list
│   ├── show
│   └── set-currency
├── holding
│   ├── add
│   ├── sell
│   ├── list
│   └── show
├── recommendation
│   ├── list
│   ├── show
│   └── refresh
├── suggestion
│   ├── list
│   └── show
├── insight
│   └── show
└── report
    ├── portfolio
    ├── performance
    └── allocation
```

---

## Portfolio Commands

### `portfolio create`

**Purpose**: Create a new portfolio

**Contract**:
```bash
stocks-helper portfolio create --name NAME --currency CURRENCY
```

**Arguments**:
| Argument | Type | Required | Validation | Description |
|----------|------|----------|------------|-------------|
| `--name` | String | Yes | Max 100 chars | Portfolio name |
| `--currency` | String | Yes | ISO 4217 code | Base currency (USD, EUR, GBP, etc.) |

**Success Output**:
```
Portfolio created successfully!
ID: 550e8400-e29b-41d4-a716-446655440000
Name: Main Portfolio
Base Currency: USD
```

**Error Cases**:
- Invalid currency code → `Error: Invalid currency 'XYZ'. Must be valid ISO 4217 code.`
- Duplicate name → `Warning: Portfolio 'Main Portfolio' already exists.` (continue anyway)

---

### `portfolio list`

**Purpose**: List all portfolios

**Contract**:
```bash
stocks-helper portfolio list
```

**Success Output**:
```
Portfolios:
┌──────────────────────────────────────┬─────────────────┬──────────┬─────────────────┐
│ ID                                   │ Name            │ Currency │ Total Value     │
├──────────────────────────────────────┼─────────────────┼──────────┼─────────────────┤
│ 550e8400-e29b-41d4-a716-446655440000 │ Main Portfolio  │ USD      │ $125,432.50     │
│ 660e8400-e29b-41d4-a716-446655440001 │ Retirement      │ EUR      │ €89,200.00      │
└──────────────────────────────────────┴─────────────────┴──────────┴─────────────────┘
```

**Error Cases**:
- No portfolios → `No portfolios found. Create one with 'portfolio create'.`

---

### `portfolio show`

**Purpose**: Show detailed portfolio view

**Contract**:
```bash
stocks-helper portfolio show [PORTFOLIO_ID]
```

**Arguments**:
| Argument | Type | Required | Validation | Description |
|----------|------|----------|------------|-------------|
| `PORTFOLIO_ID` | UUID | No (default to first) | Valid UUID | Portfolio identifier |

**Success Output**:
```
Portfolio: Main Portfolio
ID: 550e8400-e29b-41d4-a716-446655440000
Base Currency: USD
Created: 2025-01-15

Summary:
├─ Total Value: $125,432.50
├─ Total Cost: $100,000.00
├─ Gain/Loss: +$25,432.50 (+25.43%)
├─ Holdings: 15 stocks
└─ Last Updated: 2025-10-05 18:30:00

Top Holdings:
┌────────┬─────────────────┬──────────┬──────────────┬────────────┐
│ Ticker │ Name            │ Quantity │ Value        │ Gain/Loss  │
├────────┼─────────────────┼──────────┼──────────────┼────────────┤
│ AAPL   │ Apple Inc.      │ 100      │ $17,850.00   │ +15.2%     │
│ MSFT   │ Microsoft Corp. │ 50       │ $16,750.00   │ +22.5%     │
│ NVDA   │ NVIDIA Corp.    │ 30       │ $13,200.00   │ +35.7%     │
└────────┴─────────────────┴──────────┴──────────────┴────────────┘
```

**Error Cases**:
- Invalid portfolio ID → `Error: Portfolio not found.`

---

### `portfolio set-currency`

**Purpose**: Change portfolio base currency

**Contract**:
```bash
stocks-helper portfolio set-currency PORTFOLIO_ID --currency CURRENCY
```

**Arguments**:
| Argument | Type | Required | Validation | Description |
|----------|------|----------|------------|-------------|
| `PORTFOLIO_ID` | UUID | Yes | Valid UUID | Portfolio identifier |
| `--currency` | String | Yes | ISO 4217 code | New base currency |

**Success Output**:
```
Portfolio currency updated to EUR.
Historical values recalculated using exchange rates.
```

**Error Cases**:
- Invalid currency → `Error: Invalid currency 'XYZ'.`

---

## Holding Commands

### `holding add`

**Purpose**: Add a stock purchase to portfolio

**Contract**:
```bash
stocks-helper holding add PORTFOLIO_ID \
  --ticker TICKER \
  --quantity QUANTITY \
  --price PRICE \
  --date DATE \
  [--currency CURRENCY] \
  [--fees FEES] \
  [--notes NOTES]
```

**Arguments**:
| Argument | Type | Required | Validation | Description |
|----------|------|----------|------------|-------------|
| `PORTFOLIO_ID` | UUID | Yes | Valid UUID | Portfolio identifier |
| `--ticker` | String | Yes | Valid ticker | Stock ticker symbol |
| `--quantity` | Decimal | Yes | > 0 | Number of shares |
| `--price` | Decimal | Yes | > 0 | Purchase price per share |
| `--date` | Date | Yes | YYYY-MM-DD | Purchase date |
| `--currency` | String | No (default to portfolio currency) | ISO 4217 | Transaction currency |
| `--fees` | Decimal | No (default 0) | >= 0 | Transaction fees |
| `--notes` | String | No | Max 500 chars | Optional notes |

**Success Output**:
```
Stock purchase recorded!
Ticker: AAPL
Quantity: 100 shares
Price: $150.00 per share
Total Cost: $15,000.00 + $5.00 fees = $15,005.00

Holding updated:
├─ Total Quantity: 100 shares
├─ Average Price: $150.05
└─ Current Value: $17,850.00 (+18.9%)
```

**Error Cases**:
- Invalid ticker → `Error: Stock 'INVALID' not found. Check ticker symbol.`
- Invalid date → `Error: Invalid date format. Use YYYY-MM-DD.`
- Quantity <= 0 → `Error: Quantity must be positive.`

---

### `holding sell`

**Purpose**: Record a stock sale

**Contract**:
```bash
stocks-helper holding sell PORTFOLIO_ID \
  --ticker TICKER \
  --quantity QUANTITY \
  --price PRICE \
  --date DATE \
  [--currency CURRENCY] \
  [--fees FEES] \
  [--notes NOTES]
```

**Arguments**: Same as `holding add` but for sell transaction

**Success Output**:
```
Stock sale recorded!
Ticker: AAPL
Quantity: 50 shares sold
Sale Price: $175.00 per share
Total Proceeds: $8,750.00 - $5.00 fees = $8,745.00

Gain/Loss on this sale: +$1,247.50 (+16.6%)

Remaining holding:
├─ Quantity: 50 shares
├─ Average Price: $150.05
└─ Current Value: $8,925.00
```

**Error Cases**:
- Insufficient quantity → `Error: Cannot sell 100 shares. Only 50 shares available.`
- Stock not in portfolio → `Error: Stock 'TSLA' not found in portfolio.`

---

### `holding list`

**Purpose**: List all holdings in a portfolio

**Contract**:
```bash
stocks-helper holding list PORTFOLIO_ID [--sort-by FIELD] [--order ASC|DESC]
```

**Arguments**:
| Argument | Type | Required | Validation | Description |
|----------|------|----------|------------|-------------|
| `PORTFOLIO_ID` | UUID | Yes | Valid UUID | Portfolio identifier |
| `--sort-by` | String | No (default: value) | ticker, value, gain_pct | Sort field |
| `--order` | String | No (default: DESC) | ASC, DESC | Sort order |

**Success Output**:
```
Holdings in Main Portfolio (15 stocks):
┌────────┬──────────────────┬──────────┬────────────┬────────────┬─────────────┬─────────────┐
│ Ticker │ Name             │ Quantity │ Avg Price  │ Current    │ Value       │ Gain/Loss   │
├────────┼──────────────────┼──────────┼────────────┼────────────┼─────────────┼─────────────┤
│ AAPL   │ Apple Inc.       │ 100      │ $150.05    │ $178.50    │ $17,850.00  │ +18.9%      │
│ MSFT   │ Microsoft Corp.  │ 50       │ $275.00    │ $335.00    │ $16,750.00  │ +21.8%      │
│ NVDA   │ NVIDIA Corp.     │ 30       │ $325.00    │ $440.00    │ $13,200.00  │ +35.4%      │
│ ...    │ ...              │ ...      │ ...        │ ...        │ ...         │ ...         │
└────────┴──────────────────┴──────────┴────────────┴────────────┴─────────────┴─────────────┘

Total Value: $125,432.50 | Total Cost: $100,000.00 | Gain/Loss: +$25,432.50 (+25.43%)
```

---

### `holding show`

**Purpose**: Show detailed holding information

**Contract**:
```bash
stocks-helper holding show PORTFOLIO_ID --ticker TICKER
```

**Success Output**:
```
Holding Details: AAPL (Apple Inc.)
Portfolio: Main Portfolio

Current Position:
├─ Quantity: 100 shares
├─ Average Price: $150.05
├─ Current Price: $178.50 (updated 5 minutes ago)
├─ Total Cost: $15,005.00
├─ Current Value: $17,850.00
└─ Gain/Loss: +$2,845.00 (+18.95%)

Purchase History:
┌────────────┬──────────┬───────────┬──────────┬────────────┐
│ Date       │ Quantity │ Price     │ Currency │ Total Cost │
├────────────┼──────────┼───────────┼──────────┼────────────┤
│ 2024-03-15 │ 50       │ $145.00   │ USD      │ $7,250.00  │
│ 2024-06-20 │ 50       │ $155.10   │ USD      │ $7,755.00  │
└────────────┴──────────┴───────────┴──────────┴────────────┘

Latest Recommendation:
├─ Action: HOLD
├─ Confidence: MEDIUM
├─ Score: 65/100
└─ Rationale: Mixed signals - strong fundamentals but overbought technical indicators
```

---

## Recommendation Commands

### `recommendation list`

**Purpose**: List recommendations for portfolio stocks

**Contract**:
```bash
stocks-helper recommendation list PORTFOLIO_ID [--action BUY|SELL|HOLD]
```

**Arguments**:
| Argument | Type | Required | Validation | Description |
|----------|------|----------|------------|-------------|
| `PORTFOLIO_ID` | UUID | Yes | Valid UUID | Portfolio identifier |
| `--action` | String | No (all) | BUY, SELL, HOLD | Filter by recommendation type |

**Success Output**:
```
Recommendations for Main Portfolio (updated 2 hours ago):

BUY Recommendations (2):
┌────────┬──────────────────┬────────────┬───────┬─────────────────────────────────────┐
│ Ticker │ Name             │ Confidence │ Score │ Rationale                           │
├────────┼──────────────────┼────────────┼───────┼─────────────────────────────────────┤
│ MSFT   │ Microsoft Corp.  │ HIGH       │ 82/100│ Strong technical + fundamental      │
│ GOOGL  │ Alphabet Inc.    │ MEDIUM     │ 72/100│ Positive earnings, bullish trend    │
└────────┴──────────────────┴────────────┴───────┴─────────────────────────────────────┘

SELL Recommendations (1):
┌────────┬──────────────────┬────────────┬───────┬─────────────────────────────────────┐
│ Ticker │ Name             │ Confidence │ Score │ Rationale                           │
├────────┼──────────────────┼────────────┼───────┼─────────────────────────────────────┤
│ XYZ    │ Example Corp.    │ HIGH       │ 25/100│ Declining fundamentals, bearish     │
└────────┴──────────────────┴────────────┴───────┴─────────────────────────────────────┘

HOLD Recommendations (12): [use --action HOLD to see all]
```

---

### `recommendation show`

**Purpose**: Show detailed recommendation for a stock

**Contract**:
```bash
stocks-helper recommendation show PORTFOLIO_ID --ticker TICKER
```

**Success Output**:
```
Recommendation: AAPL (Apple Inc.)
Portfolio: Main Portfolio
Generated: 2025-10-05 06:00:00 (3 hours ago)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommendation: HOLD
Confidence: MEDIUM
Combined Score: 65/100
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Technical Analysis (Score: 58/100):
├─ Trend Indicators:
│  ├─ SMA 20: $175.50 (current above - bullish)
│  ├─ SMA 50: $170.25 (current above - bullish)
│  └─ MACD: 1.2 (positive but weakening)
├─ Momentum Indicators:
│  ├─ RSI: 72 (overbought - bearish)
│  └─ Stochastic: 78 (overbought - bearish)
├─ Volatility:
│  └─ Bollinger Bands: Near upper band (caution)
└─ Volume: Above average (confirmation)

Fundamental Analysis (Score: 72/100):
├─ Valuation:
│  ├─ P/E Ratio: 28.5 (slightly high for sector)
│  └─ P/B Ratio: 4.2 (premium valuation)
├─ Growth:
│  ├─ Revenue Growth: +12% YoY (strong)
│  └─ Earnings Growth: +18% YoY (excellent)
├─ Profitability:
│  ├─ ROE: 45% (exceptional)
│  └─ Profit Margin: 26% (excellent)
└─ Financial Health:
   ├─ Debt/Equity: 0.35 (low, healthy)
   └─ Current Ratio: 1.8 (good)

Rationale:
Strong fundamentals with excellent profitability and growth, but technical
indicators show overbought conditions suggesting a potential short-term
pullback. Current holders should HOLD and wait for a better entry point
for additional purchases.

Next Update: Tomorrow at 06:00 AM
```

---

### `recommendation refresh`

**Purpose**: Manually trigger recommendation refresh (outside daily batch)

**Contract**:
```bash
stocks-helper recommendation refresh PORTFOLIO_ID [--ticker TICKER]
```

**Success Output**:
```
Refreshing recommendations...
├─ Fetching market data for 15 stocks...
├─ Calculating technical indicators...
├─ Analyzing fundamentals...
└─ Generating recommendations...

Recommendations updated successfully!
Updated: 15 stocks
Changes: 3 recommendations changed
- AAPL: HOLD → BUY
- MSFT: BUY → HOLD
- XYZ: HOLD → SELL

Run 'recommendation list' to see updates.
```

---

## Suggestion Commands

### `suggestion list`

**Purpose**: List suggested stocks to buy (not currently owned)

**Contract**:
```bash
stocks-helper suggestion list PORTFOLIO_ID [--type TYPE] [--limit N]
```

**Arguments**:
| Argument | Type | Required | Validation | Description |
|----------|------|----------|------------|-------------|
| `PORTFOLIO_ID` | UUID | Yes | Valid UUID | Portfolio identifier |
| `--type` | String | No (all) | DIVERSIFICATION, SIMILAR_TO_WINNERS, MARKET_OPPORTUNITY | Filter by type |
| `--limit` | Integer | No (default 10) | > 0 | Max suggestions to show |

**Success Output**:
```
Stock Suggestions for Main Portfolio (updated 2 hours ago):

Diversification Opportunities (5):
┌────────┬──────────────────┬────────┬───────┬─────────────────────────────────────┐
│ Ticker │ Name             │ Sector │ Score │ Portfolio Fit                       │
├────────┼──────────────────┼────────┼───────┼─────────────────────────────────────┤
│ JNJ    │ Johnson & Johnson│ Health │ 78/100│ Fill healthcare gap (0% → 10%)      │
│ XOM    │ Exxon Mobil      │ Energy │ 75/100│ Fill energy gap (0% → 8%)           │
└────────┴──────────────────┴────────┴───────┴─────────────────────────────────────┘

Similar to Your Winners (3):
┌────────┬──────────────────┬────────┬───────┬─────────────────────────────────────┐
│ Ticker │ Name             │ Sector │ Score │ Portfolio Fit                       │
├────────┼──────────────────┼────────┼───────┼─────────────────────────────────────┤
│ AMD    │ AMD Inc.         │ Tech   │ 80/100│ Similar to NVDA (+35.7%)            │
│ CRM    │ Salesforce       │ Tech   │ 76/100│ Similar to MSFT (+22.5%)            │
└────────┴──────────────────┴────────┴───────┴─────────────────────────────────────┘

Market Opportunities (2):
┌────────┬──────────────────┬────────┬───────┬─────────────────────────────────────┐
│ Ticker │ Name             │ Sector │ Score │ Portfolio Fit                       │
├────────┼──────────────────┼────────┼───────┼─────────────────────────────────────┤
│ PLTR   │ Palantir         │ Tech   │ 85/100│ Strong technical + fundamental      │
│ ABNB   │ Airbnb           │ Consumer│75/100│ Undervalued with growth potential   │
└────────┴──────────────────┴────────┴───────┴─────────────────────────────────────┘

Use 'suggestion show TICKER' for detailed analysis.
```

---

### `suggestion show`

**Purpose**: Show detailed suggestion analysis

**Contract**:
```bash
stocks-helper suggestion show PORTFOLIO_ID --ticker TICKER
```

**Success Output**: Similar format to `recommendation show` but includes portfolio fit explanation

---

## Insight Commands

### `insight show`

**Purpose**: Show portfolio-level insights

**Contract**:
```bash
stocks-helper insight show PORTFOLIO_ID
```

**Success Output**:
```
Portfolio Insights: Main Portfolio
Generated: 2025-10-05 06:00:00 (3 hours ago)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sector Allocation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┌─────────────┬────────────┬──────────────┐
│ Sector      │ Allocation │ Concentration│
├─────────────┼────────────┼──────────────┤
│ Technology  │ 45.5%      │ ⚠️  HIGH     │
│ Healthcare  │ 20.0%      │ ✓ Balanced   │
│ Finance     │ 15.0%      │ ✓ Balanced   │
│ Energy      │ 10.0%      │ ✓ Balanced   │
│ Consumer    │  9.5%      │ ✓ Balanced   │
└─────────────┴────────────┴──────────────┘

⚠️  Warning: High concentration in Technology (45.5%)
Consider diversifying into underrepresented sectors.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Geographic Distribution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
├─ United States: 70%
├─ Europe: 20%
├─ Asia: 10%
└─ Other: 0%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Top Performers (Last 30 Days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. NVDA +35.7%
2. MSFT +22.5%
3. AAPL +18.9%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Diversification Gaps
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Underrepresented Sectors:
├─ Real Estate: 0% (recommend 5-10%)
├─ Utilities: 0% (recommend 3-5%)
└─ Materials: 0% (recommend 3-5%)

💡 Tip: Check 'suggestion list --type DIVERSIFICATION' for recommendations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Risk Assessment
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
├─ Portfolio Volatility: Medium
├─ Sharpe Ratio: 1.45 (Good risk-adjusted returns)
└─ Beta vs S&P 500: 1.15 (Slightly more volatile than market)
```

---

## Report Commands

### `report portfolio`

**Purpose**: Generate comprehensive portfolio report (HTML)

**Contract**:
```bash
stocks-helper report portfolio PORTFOLIO_ID [--output FILE]
```

**Success Output**:
```
Generating portfolio report...
├─ Performance charts: ✓
├─ Allocation pie charts: ✓
├─ Holdings table: ✓
├─ Recommendations: ✓
└─ Insights: ✓

Report saved to: reports/portfolio_2025-10-05.html
Open in browser: file:///path/to/reports/portfolio_2025-10-05.html
```

---

### `report performance`

**Purpose**: Performance analysis report

**Contract**:
```bash
stocks-helper report performance PORTFOLIO_ID [--period 30d|90d|1y|all]
```

**Success Output**:
```
Performance Report: Main Portfolio (Last 30 days)

Summary:
├─ Starting Value: $110,000.00 (2025-09-05)
├─ Ending Value: $125,432.50 (2025-10-05)
├─ Gain: +$15,432.50 (+14.03%)
├─ Benchmark (S&P 500): +8.5%
└─ Outperformance: +5.53%

[ASCII chart or save to HTML with Plotly chart]
```

---

### `report allocation`

**Purpose**: Allocation breakdown report

**Contract**:
```bash
stocks-helper report allocation PORTFOLIO_ID
```

**Success Output**: Similar to insight show but with exportable charts

---

## Error Handling Standards

All commands must handle:

1. **Network Errors**: API unavailable
   ```
   ⚠️  Warning: Unable to fetch latest prices (API unavailable).
   Showing cached data from 2 hours ago.
   ```

2. **Rate Limits**:
   ```
   ⚠️  API rate limit reached. Using cached data.
   Next update available in 45 minutes.
   ```

3. **Invalid Input**:
   ```
   Error: Invalid argument '--quantity abc'. Must be a positive number.
   ```

4. **Not Found**:
   ```
   Error: Portfolio '123' not found.
   Run 'portfolio list' to see available portfolios.
   ```

---

## Output Formatting

- **Tables**: Use `rich` library for formatted tables
- **Colors**:
  - Green: Positive gains
  - Red: Losses
  - Yellow: Warnings
  - Blue: Info
- **Symbols**:
  - ✓ Success
  - ⚠️  Warning
  - ❌ Error
  - 💡 Tip

---

**CLI Contracts Complete**: Ready for test generation.
