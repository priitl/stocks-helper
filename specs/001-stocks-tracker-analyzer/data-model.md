# Data Model - Stocks Tracker & Analyzer

**Feature**: 001-stocks-tracker-analyzer
**Date**: 2025-10-05
**Source**: Extracted from spec.md Key Entities section

---

## Entity Relationship Overview

```
User (implicit)
  └─ Portfolio (1:N)
       ├─ Holdings (1:N) ─── Stock (N:1)
       │     └─ Transactions (1:N)
       │
       └─ Configuration
             ├─ base_currency
             └─ preferences

Stock
  ├─ MarketData (1:N, time-series)
  ├─ StockRecommendation (1:N, time-series)
  └─ StockSuggestion (1:N, for non-owned stocks)

Insight (portfolio-level analysis)
```

---

## Core Entities

### 1. Portfolio

**Purpose**: Represents the user's complete investment holdings

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique portfolio identifier |
| `name` | String | NOT NULL, max 100 chars | Portfolio name (e.g., "Main Portfolio") |
| `base_currency` | String | NOT NULL, ISO 4217 code | Base currency for calculations (USD, EUR, GBP, etc.) |
| `created_at` | Timestamp | NOT NULL | Portfolio creation date |
| `updated_at` | Timestamp | NOT NULL | Last modification timestamp |

**Relationships**:
- Has many `Holdings`
- Has many `Transactions` (via holdings)
- Has many `Insights`

**Validation Rules**:
- `base_currency` must be valid ISO 4217 code
- At least one portfolio required per user

---

### 2. Stock

**Purpose**: Master data for a stock/security

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `ticker` | String | PRIMARY KEY, max 10 chars | Stock ticker symbol (e.g., AAPL, TSLA) |
| `exchange` | String | NOT NULL, max 20 chars | Exchange code (NYSE, NASDAQ, LSE, etc.) |
| `name` | String | NOT NULL, max 200 chars | Company name |
| `sector` | String | NULL, max 50 chars | Sector classification (Technology, Healthcare, etc.) |
| `market_cap` | Decimal | NULL | Market capitalization in USD |
| `currency` | String | NOT NULL, ISO 4217 code | Trading currency |
| `country` | String | NULL, ISO 3166 code | Country/region (US, GB, DE, etc.) |
| `last_updated` | Timestamp | NOT NULL | Last data refresh |

**Relationships**:
- Has many `Holdings`
- Has many `MarketData` (time-series)
- Has many `StockRecommendations`

**Validation Rules**:
- `ticker` must be unique per exchange
- `currency` must be valid ISO 4217 code

---

### 3. Holding

**Purpose**: Represents a stock position in a portfolio

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique holding identifier |
| `portfolio_id` | UUID | FOREIGN KEY, NOT NULL | Parent portfolio |
| `ticker` | String | FOREIGN KEY, NOT NULL | Stock ticker |
| `quantity` | Decimal | NOT NULL, > 0 | Number of shares owned |
| `avg_purchase_price` | Decimal | NOT NULL, > 0 | Average purchase price per share |
| `original_currency` | String | NOT NULL, ISO 4217 | Currency of original purchase |
| `first_purchase_date` | Date | NOT NULL | Date of first purchase |
| `created_at` | Timestamp | NOT NULL | Holding creation timestamp |
| `updated_at` | Timestamp | NOT NULL | Last modification timestamp |

**Computed Fields** (not stored, calculated on-demand):
- `current_value`: `quantity * current_price` (in original currency)
- `current_value_base`: Current value in portfolio base currency
- `total_cost`: Sum of all purchase transactions
- `gain_loss`: `current_value_base - total_cost`
- `gain_loss_pct`: `(gain_loss / total_cost) * 100`

**Relationships**:
- Belongs to one `Portfolio`
- References one `Stock`
- Has many `Transactions`

**Validation Rules**:
- `quantity` must be positive
- Cannot have duplicate ticker per portfolio (consolidate holdings)
- `avg_purchase_price` updated automatically from transactions

---

### 4. Transaction

**Purpose**: Records buy/sell actions for a stock

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique transaction identifier |
| `holding_id` | UUID | FOREIGN KEY, NOT NULL | Parent holding |
| `type` | Enum | NOT NULL (BUY, SELL) | Transaction type |
| `date` | Date | NOT NULL | Transaction date |
| `quantity` | Decimal | NOT NULL, > 0 | Number of shares |
| `price` | Decimal | NOT NULL, > 0 | Price per share |
| `currency` | String | NOT NULL, ISO 4217 | Transaction currency |
| `exchange_rate` | Decimal | NOT NULL, > 0 | Exchange rate to base currency at transaction time |
| `fees` | Decimal | DEFAULT 0, >= 0 | Transaction fees/commissions |
| `notes` | String | NULL, max 500 chars | Optional user notes |
| `created_at` | Timestamp | NOT NULL | Record creation timestamp |

**Relationships**:
- Belongs to one `Holding`

**Validation Rules**:
- SELL transactions: `quantity` cannot exceed current holding quantity
- `exchange_rate` must be > 0
- `fees` must be non-negative

**State Transitions**:
- BUY → increases holding quantity, recalculates avg_purchase_price
- SELL → decreases holding quantity, holding deleted if quantity reaches 0

---

### 5. MarketData

**Purpose**: Current and historical stock market information

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `ticker` | String | FOREIGN KEY, NOT NULL | Stock ticker |
| `timestamp` | Timestamp | NOT NULL | Data timestamp |
| `price` | Decimal | NOT NULL, > 0 | Stock price |
| `volume` | BigInt | NULL, >= 0 | Trading volume |
| `open` | Decimal | NULL, > 0 | Opening price |
| `high` | Decimal | NULL, > 0 | Day high |
| `low` | Decimal | NULL, > 0 | Day low |
| `close` | Decimal | NULL, > 0 | Closing price |
| `data_source` | String | NOT NULL, max 50 chars | API source (alpha_vantage, yahoo_finance) |
| `is_latest` | Boolean | DEFAULT false | Flag for current price |

**Composite Primary Key**: (`ticker`, `timestamp`)

**Relationships**:
- Belongs to one `Stock`

**Validation Rules**:
- Only one `is_latest=true` per ticker
- `high >= low`, `high >= open`, `high >= close`, `low <= open`, `low <= close`

**Lifecycle**:
- Historical data: Immutable
- Latest data: Updated by daily batch, previous latest set to `is_latest=false`

---

### 6. FundamentalData

**Purpose**: Fundamental analysis metrics for stocks

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `ticker` | String | FOREIGN KEY, NOT NULL | Stock ticker |
| `timestamp` | Timestamp | NOT NULL | Data timestamp |
| `pe_ratio` | Decimal | NULL | Price-to-Earnings ratio |
| `pb_ratio` | Decimal | NULL | Price-to-Book ratio |
| `peg_ratio` | Decimal | NULL | PEG ratio |
| `roe` | Decimal | NULL | Return on Equity (%) |
| `roa` | Decimal | NULL | Return on Assets (%) |
| `profit_margin` | Decimal | NULL | Net profit margin (%) |
| `revenue_growth_yoy` | Decimal | NULL | Revenue growth YoY (%) |
| `earnings_growth_yoy` | Decimal | NULL | Earnings growth YoY (%) |
| `debt_to_equity` | Decimal | NULL | Debt-to-Equity ratio |
| `current_ratio` | Decimal | NULL | Current ratio |
| `dividend_yield` | Decimal | NULL | Dividend yield (%) |
| `data_source` | String | NOT NULL | API source |

**Composite Primary Key**: (`ticker`, `timestamp`)

**Relationships**:
- Belongs to one `Stock`

**Validation Rules**:
- Ratios and percentages must be reasonable (e.g., pe_ratio < 1000)
- `dividend_yield` must be >= 0

---

### 7. StockRecommendation

**Purpose**: Buy/sell/hold suggestions for portfolio stocks

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique recommendation ID |
| `ticker` | String | FOREIGN KEY, NOT NULL | Stock ticker |
| `portfolio_id` | UUID | FOREIGN KEY, NOT NULL | Portfolio this applies to |
| `timestamp` | Timestamp | NOT NULL | Recommendation generation time |
| `recommendation` | Enum | NOT NULL (BUY, SELL, HOLD) | Recommendation type |
| `confidence` | Enum | NOT NULL (HIGH, MEDIUM, LOW) | Confidence level |
| `technical_score` | Decimal | NOT NULL, 0-100 | Technical analysis score |
| `fundamental_score` | Decimal | NOT NULL, 0-100 | Fundamental analysis score |
| `combined_score` | Decimal | NOT NULL, 0-100 | Weighted combined score |
| `technical_signals` | JSON | NOT NULL | Technical indicators breakdown |
| `fundamental_signals` | JSON | NOT NULL | Fundamental metrics breakdown |
| `rationale` | String | NOT NULL, max 1000 chars | Human-readable explanation |

**Relationships**:
- Belongs to one `Stock`
- Belongs to one `Portfolio`

**Validation Rules**:
- Scores must be 0-100
- `combined_score` = weighted average of technical + fundamental
- BUY: `combined_score > 70`
- SELL: `combined_score < 30`
- HOLD: `30 <= combined_score <= 70`

**JSON Schema for `technical_signals`**:
```json
{
  "trend": {"sma_20": 150.5, "sma_50": 145.2, "macd": 2.3},
  "momentum": {"rsi": 65, "stochastic": 70},
  "volatility": {"bollinger_upper": 160, "bollinger_lower": 140},
  "volume": {"obv": 1000000}
}
```

**JSON Schema for `fundamental_signals`**:
```json
{
  "valuation": {"pe_ratio": 25, "pb_ratio": 3.5},
  "growth": {"revenue_growth": 15, "earnings_growth": 20},
  "profitability": {"roe": 18, "profit_margin": 12},
  "health": {"debt_to_equity": 0.5, "current_ratio": 2.0}
}
```

---

### 8. StockSuggestion

**Purpose**: Recommendations for new stocks to purchase

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique suggestion ID |
| `ticker` | String | FOREIGN KEY, NOT NULL | Suggested stock ticker |
| `portfolio_id` | UUID | FOREIGN KEY, NOT NULL | Portfolio this applies to |
| `timestamp` | Timestamp | NOT NULL | Suggestion generation time |
| `suggestion_type` | Enum | NOT NULL | DIVERSIFICATION, SIMILAR_TO_WINNERS, MARKET_OPPORTUNITY |
| `technical_score` | Decimal | NOT NULL, 0-100 | Technical analysis score |
| `fundamental_score` | Decimal | NOT NULL, 0-100 | Fundamental analysis score |
| `overall_score` | Decimal | NOT NULL, 0-100 | Combined score |
| `technical_summary` | String | NOT NULL, max 500 chars | Technical analysis summary |
| `fundamental_summary` | String | NOT NULL, max 500 chars | Fundamental analysis summary |
| `portfolio_fit` | String | NOT NULL, max 500 chars | How it addresses gaps or relates to holdings |
| `related_holding_ticker` | String | NULL | For SIMILAR_TO_WINNERS type |

**Relationships**:
- Belongs to one `Stock`
- Belongs to one `Portfolio`

**Validation Rules**:
- Cannot suggest stocks already in portfolio
- SIMILAR_TO_WINNERS type must have `related_holding_ticker`
- Scores must be 0-100

---

### 9. Insight

**Purpose**: Portfolio-level analytical observations

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique insight ID |
| `portfolio_id` | UUID | FOREIGN KEY, NOT NULL | Parent portfolio |
| `timestamp` | Timestamp | NOT NULL | Insight generation time |
| `insight_type` | Enum | NOT NULL | SECTOR_ALLOCATION, GEO_ALLOCATION, DIVERSIFICATION_GAP, HIGH_PERFORMERS, RISK_ASSESSMENT, PERFORMANCE_TREND |
| `data` | JSON | NOT NULL | Type-specific insight data |
| `summary` | String | NOT NULL, max 500 chars | Human-readable summary |

**Relationships**:
- Belongs to one `Portfolio`

**JSON Schema Examples**:

**SECTOR_ALLOCATION**:
```json
{
  "allocations": {
    "Technology": 45.5,
    "Healthcare": 20.0,
    "Finance": 15.0,
    "Energy": 10.0,
    "Consumer": 9.5
  },
  "concentration_risk": "HIGH"  // > 40% in one sector
}
```

**DIVERSIFICATION_GAP**:
```json
{
  "underrepresented": [
    {"sector": "Real Estate", "current": 0, "recommended": 10},
    {"region": "Asia", "current": 5, "recommended": 15}
  ]
}
```

**HIGH_PERFORMERS**:
```json
{
  "top_performers": [
    {"ticker": "AAPL", "gain_pct": 35.5},
    {"ticker": "MSFT", "gain_pct": 28.2},
    {"ticker": "NVDA", "gain_pct": 22.1}
  ]
}
```

---

### 10. ExchangeRate

**Purpose**: Currency conversion rates (cached)

**Fields**:
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `from_currency` | String | NOT NULL, ISO 4217 | Source currency |
| `to_currency` | String | NOT NULL, ISO 4217 | Target currency |
| `rate` | Decimal | NOT NULL, > 0 | Exchange rate |
| `date` | Date | NOT NULL | Rate validity date |

**Composite Primary Key**: (`from_currency`, `to_currency`, `date`)

**Validation Rules**:
- Self-conversion rate (USD → USD) must be 1.0
- Rates updated daily
- Keep 2 years of historical rates

---

## Database Schema Notes

### Indexes

**Performance-Critical Indexes**:
- `Portfolio.id` (PRIMARY KEY)
- `Stock.ticker` (PRIMARY KEY)
- `Holding.portfolio_id` (FOREIGN KEY, frequent joins)
- `Transaction.holding_id` (FOREIGN KEY)
- `MarketData(ticker, is_latest)` (fast current price lookups)
- `StockRecommendation(portfolio_id, timestamp)` (latest recommendations)
- `ExchangeRate(from_currency, to_currency, date)` (frequent conversions)

### Data Retention

- **Transactions**: Keep forever (historical record)
- **MarketData**: Keep 2 years daily data, older data can be aggregated/archived
- **Recommendations**: Keep 6 months (for accuracy tracking)
- **Suggestions**: Keep 1 month
- **Insights**: Keep 1 year
- **ExchangeRates**: Keep 2 years

### Constraints Summary

1. **Referential Integrity**: All foreign keys with CASCADE DELETE where appropriate
2. **Check Constraints**: Positive quantities, valid score ranges, valid enum values
3. **Unique Constraints**: No duplicate holdings per portfolio, unique latest market data
4. **Null Constraints**: All required fields enforced

---

## Entity Lifecycle Examples

### Adding a Stock Purchase

1. Check if `Stock` exists → create if not
2. Check if `Holding` exists for ticker in portfolio
   - **New**: Create `Holding` with initial quantity and price
   - **Existing**: Create `Transaction`, update `Holding.quantity` and `avg_purchase_price`
3. Create `Transaction` record
4. Fetch latest `MarketData` for valuation
5. Trigger recommendation recalculation (async)

### Daily Batch Update

1. For each `Stock` in any `Holding`:
   - Fetch market data from APIs
   - Store in `MarketData`, set `is_latest=true`
   - Fetch fundamental data
   - Store in `FundamentalData`
2. For each `Portfolio`:
   - Calculate technical indicators
   - Calculate fundamental scores
   - Generate `StockRecommendation` for each holding
   - Generate `StockSuggestion` for non-owned stocks
   - Generate `Insight` records
3. Update exchange rates

---

**Data Model Complete**: Ready for contract generation.
