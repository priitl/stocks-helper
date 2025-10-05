# Stocks Helper Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-05

## Active Technologies

- Python 3.11+ (001-stocks-tracker-analyzer)
  - CLI Framework: Click 8.x
  - Data Processing: Pandas, NumPy
  - Technical Analysis: TA-Lib, pandas-ta
  - Database: SQLite 3.40+
  - Async: asyncio, aiohttp
  - Testing: pytest 7.x

## Project Structure

```
stocks-helper/
├── src/
│   ├── models/          # SQLite ORM models (Portfolio, Stock, Holding, etc.)
│   ├── services/        # Business logic (RecommendationEngine, MarketDataFetcher)
│   ├── cli/             # Click commands (portfolio, holding, recommendation, etc.)
│   └── lib/             # Utilities (currency conversion, indicators)
│
├── tests/
│   ├── contract/        # API contract tests (Alpha Vantage, Yahoo Finance schemas)
│   ├── integration/     # End-to-end CLI tests (quickstart scenarios)
│   └── unit/            # Business logic tests (scoring, calculations)
│
├── specs/
│   └── 001-stocks-tracker-analyzer/
│       ├── spec.md
│       ├── plan.md
│       ├── research.md
│       ├── data-model.md
│       ├── quickstart.md
│       └── contracts/
│
└── reports/             # Generated HTML reports
```

## Commands

### Development Setup

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run specific test
pytest tests/contract/test_alpha_vantage_api.py

# Run with coverage
pytest --cov=src --cov-report=html
```

### Daily Batch Job

```bash
# Manual trigger
stocks-helper recommendation refresh <PORTFOLIO_ID>

# Schedule with cron (add to crontab -e)
0 18 * * * /path/to/venv/bin/stocks-helper recommendation refresh <PORTFOLIO_ID>
```

### Database Management

```bash
# Initialize database
stocks-helper init

# Backup database
cp ~/.stocks-helper/data.db ~/.stocks-helper/backup_$(date +%Y%m%d).db

# View schema
sqlite3 ~/.stocks-helper/data.db ".schema"
```

## Code Style

### Python (PEP 8 + Project Conventions)

**Naming**:
- Classes: `PascalCase` (e.g., `PortfolioService`, `StockRecommendation`)
- Functions/methods: `snake_case` (e.g., `calculate_gain_loss`, `fetch_market_data`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `API_RATE_LIMIT`, `DEFAULT_CURRENCY`)
- Private methods: `_leading_underscore` (e.g., `_calculate_score`)

**Type Hints** (required):
```python
from decimal import Decimal
from datetime import date

def add_transaction(
    holding_id: str,
    quantity: Decimal,
    price: Decimal,
    date: date
) -> Transaction:
    ...
```

**Error Handling**:
```python
# Explicit error types
class APIRateLimitError(Exception):
    """Raised when API rate limit is exceeded"""
    pass

# Fail fast with context
if response.status_code == 429:
    raise APIRateLimitError(
        f"Rate limit exceeded for {api_name}. "
        f"Retry after {retry_after} seconds."
    )
```

**Async Patterns**:
```python
async def fetch_all_stocks(tickers: list[str]) -> list[MarketData]:
    """Fetch market data for multiple stocks concurrently"""
    tasks = [fetch_stock_data(ticker) for ticker in tickers]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

**Testing**:
```python
# Contract test example
def test_alpha_vantage_daily_response_schema():
    """Verify Alpha Vantage API returns expected fields"""
    response = fetch_daily_data("AAPL")
    assert "Meta Data" in response
    assert "Time Series (Daily)" in response
    time_series = response["Time Series (Daily)"]
    latest = next(iter(time_series.values()))
    assert all(key in latest for key in ["1. open", "2. high", "3. low", "4. close", "5. volume"])
```

## Recent Changes

- **001-stocks-tracker-analyzer**: Added Python 3.11 + CLI framework + stock market APIs + recommendation engine

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
