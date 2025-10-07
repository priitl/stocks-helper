# Stocks Helper

**Personal Stocks Tracker & Analyzer** - A comprehensive CLI tool for tracking your stock portfolio, analyzing performance, and receiving AI-powered investment recommendations.

> 🎉 **Production Ready**: 300 tests passing, full accounting system, CSV import, tax reporting, and AI recommendations.

## Features

### Portfolio Management
- 📊 **Multi-portfolio support** - Track multiple investment portfolios
- 💱 **Multi-currency** - Support for different base currencies with automatic conversion
- 📈 **Holdings tracking** - Buy/sell transactions with cost basis calculation
- 💰 **Real-time valuations** - Current portfolio value and gain/loss tracking
- 📥 **CSV Import** - Bulk transaction import from broker statements (Swedbank, Lightyear)

### Full Accounting System
- 📚 **Double-entry bookkeeping** - Professional accounting with journal entries
- 🔄 **Reconciliation** - Match broker transactions to journal entries
- 📊 **Financial Reports** - Balance sheet, income statement, trial balance, general ledger
- 🧾 **Tax Reporting** - Capital gains (FIFO/LIFO/Average), dividend income, annual summaries
- 📑 **Chart of Accounts** - Standard account structure for all transaction types

### Market Data & Analysis
- 🔄 **Automated data fetching** - Alpha Vantage (primary) + Yahoo Finance (fallback)
- 📉 **Technical analysis** - RSI, MACD, SMA, EMA, Bollinger Bands, ATR, OBV
- 📊 **Fundamental analysis** - P/E, P/B, PEG, ROE, ROA, profit margins, growth rates
- 🤖 **AI recommendations** - Buy/Sell/Hold recommendations with confidence levels

### Intelligence & Insights
- 🎯 **Stock suggestions** - Discover new investment opportunities
  - Diversification candidates
  - Similar to top performers
  - Market opportunities
- 💡 **Portfolio insights** - Comprehensive analytics
  - Sector allocation
  - Geographic distribution
  - Top performers
  - Diversification gaps
  - Risk assessment

### Reporting & Automation
- 📄 **HTML reports** - Interactive charts with Plotly
- ⏰ **Scheduled updates** - Automated daily batch processing
- 🎨 **Rich CLI** - Beautiful terminal output with color-coded information

---

## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/stocks-helper.git
cd stocks-helper

# Create virtual environment (Python 3.11-3.12)
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package
pip install -e .

# Optional: Install yfinance for fallback market data
pip install yfinance

# Initialize database
stocks-helper init
```

### API Keys Setup

**Important for Technical Analysis**: Alpha Vantage API key is **required** for technical indicators (RSI, MACD, etc.). Without it, you'll only get fundamental analysis.

```bash
# Alpha Vantage (market data) - REQUIRED for technical analysis
# Get free key at https://www.alphavantage.co/support/#api-key
export ALPHA_VANTAGE_API_KEY="your-key-here"

# ExchangeRate-API (currency conversion) - Optional
# Get free key at https://www.exchangerate-api.com/
export EXCHANGE_RATE_API_KEY="your-key-here"
```

**First-time setup** (after setting API key):
```bash
# Fetch historical data for technical analysis (one-time)
python fetch_historical_data.py <portfolio-id>
```

This downloads 100 days of historical data needed for technical indicators.

---

## Usage Example

```bash
# Create a portfolio
stocks-helper portfolio create --name "My Portfolio" --currency EUR
export PID="<portfolio-id-from-output>"

# Option 1: Import from CSV (recommended for bulk transactions)
stocks-helper import csv -f transactions.csv -b lightyear

# Option 2: Add stocks manually
stocks-helper holding add $PID --ticker AAPL --quantity 10 --price 150.00 --date 2024-01-15
stocks-helper holding add $PID --ticker MSFT --quantity 5 --price 350.00 --date 2024-02-01

# View portfolio
stocks-helper portfolio show $PID

# Get recommendations
stocks-helper recommendation refresh $PID
stocks-helper recommendation list $PID

# Generate insights
stocks-helper insight generate $PID
stocks-helper insight show $PID

# Create HTML report
stocks-helper report portfolio $PID --open

# Set up automated daily updates (6 PM daily)
stocks-helper batch start
```

---

## Core Commands

### Portfolio Management
```bash
stocks-helper portfolio create --name NAME --currency CURR
stocks-helper portfolio list
stocks-helper portfolio show <ID>
stocks-helper portfolio set-currency <ID> --currency CURR
```

### Holdings & Transactions
```bash
stocks-helper holding add <ID> --ticker X --quantity N --price P --date YYYY-MM-DD
stocks-helper holding sell <ID> --ticker X --quantity N --price P --date YYYY-MM-DD
stocks-helper holding list <ID>
stocks-helper holding show <ID> --ticker X
```

### CSV Import & Metadata
```bash
stocks-helper import csv -f FILE -b BROKER [--dry-run]
stocks-helper import history [-n LIMIT]
stocks-helper import review-metadata
stocks-helper import update-metadata TICKER [YAHOO-TICKER]
stocks-helper import review-tickers BATCH-ID
stocks-helper import correct-ticker BATCH-ID ROW TICKER
stocks-helper import ignore-tickers BATCH-ID ROW...
```

### Stock Management
```bash
stocks-helper stock add-batch --tickers "NVDA,AMD,INTC,TSM"
stocks-helper stock list
stocks-helper stock remove --ticker X
```

### Recommendations & Suggestions
```bash
stocks-helper recommendation list <ID> [--action BUY|SELL|HOLD]
stocks-helper recommendation show <ID> --ticker X
stocks-helper recommendation refresh <ID> [--ticker X]

stocks-helper suggestion generate <ID> --tickers "JPM,JNJ,XOM,DIS"
stocks-helper suggestion list <ID> [--type TYPE]
stocks-helper suggestion show <ID> --ticker X
```

### Insights & Reports
```bash
stocks-helper insight generate <ID>
stocks-helper insight show <ID>

stocks-helper report portfolio <ID> [--output FILE] [--open]
stocks-helper report performance <ID> [--period 30d|90d|1y|all]
stocks-helper report allocation <ID>
```

### Batch Processing
```bash
stocks-helper batch run-once              # Run batch update now
stocks-helper batch start [--time HH:MM]  # Start daily scheduler
stocks-helper batch status                # Show scheduler status
stocks-helper batch stop                  # Stop scheduler
```

---

## Architecture

### Tech Stack
- **Language**: Python 3.11-3.12
- **CLI Framework**: Click
- **Database**: SQLite + SQLAlchemy ORM
- **Market Data**: Alpha Vantage, Yahoo Finance (yfinance)
- **Technical Analysis**: TA-Lib, pandas-ta
- **Visualization**: Plotly
- **Scheduling**: APScheduler
- **Terminal UI**: Rich

### Project Structure
```
stocks-helper/
├── src/
│   ├── models/                    # SQLAlchemy models (20+ models)
│   │   ├── portfolio.py           # Portfolio management
│   │   ├── security.py            # Stocks, bonds, ETFs
│   │   ├── transaction.py         # Broker transactions
│   │   ├── journal.py             # Journal entries & lines
│   │   ├── chart_of_accounts.py   # Accounting structure
│   │   ├── reconciliation.py      # Transaction reconciliation
│   │   └── ...                    # Holdings, market data, etc.
│   ├── services/                  # Business logic
│   │   ├── import_service.py      # CSV import (Swedbank, Lightyear)
│   │   ├── accounting_service.py  # Double-entry bookkeeping
│   │   ├── reconciliation_service.py  # Transaction reconciliation
│   │   ├── tax_reporting.py       # Tax calculations & reports
│   │   ├── analytics/             # Financial reports
│   │   │   ├── ledger_reports.py  # General ledger, trial balance
│   │   │   └── ...                # Income statement, balance sheet
│   │   └── ...                    # Market data, recommendations
│   ├── cli/                       # CLI commands
│   └── lib/                       # Utilities (DB, API, cache, validators)
├── specs/                         # Feature specifications
├── research/                      # Sample CSV files for testing
├── reports/                       # Generated HTML reports
└── tests/                         # Test suite (300 tests)
    ├── unit/                      # Unit tests (203)
    ├── integration/               # Integration tests (32)
    └── contract/                  # Contract tests (65)
```

---

## How It Works

### Recommendation Engine

Recommendations combine **technical** and **fundamental** analysis:

**Technical Score (0-100)**
- Trend indicators: SMA, EMA (30% weight)
- Momentum: RSI, MACD (25% weight)
- Volatility: Bollinger Bands, ATR (15% weight)
- Volume: OBV (10% weight)

**Fundamental Score (0-100)**
- Valuation: P/E, P/B, PEG (30% weight)
- Growth: Revenue, earnings YoY (25% weight)
- Profitability: ROE, margins (20% weight)
- Financial health: Debt/equity, liquidity (15% weight)

**Combined Score** = (Technical + Fundamental) / 2
- **BUY**: Combined score > 70
- **SELL**: Combined score < 30
- **HOLD**: Combined score 30-70

**Confidence Level**:
- **HIGH**: Technical and fundamental scores agree (diff < 15)
- **MEDIUM**: Scores mostly aligned (diff < 30)
- **LOW**: Conflicting signals (diff >= 30)

### Suggestion Engine

Discovers new investment opportunities:

1. **Diversification**: Finds stocks in underrepresented sectors/regions (<10% allocation)
2. **Similar to Winners**: Matches top performers by sector, market cap, and correlation
3. **Market Opportunities**: Identifies high-scoring stocks not in portfolio

### Batch Processing

Daily automated workflow:
1. Fetch latest market data for all holdings
2. Update fundamental data
3. Calculate technical indicators
4. Generate recommendations with fresh signals
5. Create portfolio insights
6. Update exchange rates

Rate limiting: 1 request per 15 seconds (Alpha Vantage free tier: 25/day)

### CSV Import & Metadata Enrichment

Bulk import transactions from broker statements with automatic metadata enrichment:

**Supported Brokers:**
- **Swedbank** - Estonian broker CSV format
- **Lightyear** - European broker CSV format

#### Import Commands

```bash
# Import transactions from CSV
stocks-helper import csv -f transactions.csv -b lightyear

# Dry run (validation only)
stocks-helper import csv -f test.csv -b swedbank --dry-run

# View import history
stocks-helper import history

# Review securities needing metadata enrichment
stocks-helper import review-metadata

# Update security with correct Yahoo Finance ticker
stocks-helper import update-metadata IWDA-NA IWDA.AS
```

#### Metadata Enrichment

After import, enrich security metadata with correct company names and exchange info:

```bash
# 1. Review securities with missing/incorrect data
stocks-helper import review-metadata

# 2. Update with correct Yahoo Finance tickers
stocks-helper import update-metadata IWDA-NA IWDA.AS
stocks-helper import update-metadata BRK.B BRK-B
stocks-helper import update-metadata EFT1T EFT1T.TL
```

**Common Yahoo Ticker Corrections:**
- `IWDA-NA` → `IWDA.AS` (Amsterdam Euronext)
- `BRK.B` → `BRK-B` (NYSE)
- `EFT1T` → `EFT1T.TL` (Tallinn Stock Exchange)
- `LHV1T` → `LHV1T.TL` (Tallinn Stock Exchange)

**Exchange Suffixes:**
- `.TL` - Tallinn (Estonia)
- `.HE` - Helsinki (Finland)
- `.OL` - Oslo (Norway)
- `.AS` - Amsterdam (Netherlands)
- `.DE` - XETRA (Germany)

#### Handling Unknown Tickers

If import detects unknown tickers:

```bash
# 1. Review unknown tickers from batch
stocks-helper import review-tickers <batch-id>

# 2. Correct typos
stocks-helper import correct-ticker <batch-id> <row> AAPL

# 3. Ignore invalid entries
stocks-helper import ignore-tickers <batch-id> <row1> <row2>
```

**Features:**
- Automatic transaction type detection (BUY, SELL, DIVIDEND, FEE, etc.)
- Multi-currency support with automatic conversion
- Duplicate detection (composite key: reference_id + type + currency)
- Metadata enrichment from Yahoo Finance (company name, exchange, sector, country)
- Error handling with detailed validation messages
- Unknown ticker detection and correction workflow

**Tested Import:**
- ✓ 549 rows imported from 4 CSV files
- ✓ 533 transactions successfully processed
- ✓ 32 securities created with full metadata
- ✓ 11 transaction types handled

### Accounting System

Professional double-entry bookkeeping with full audit trail:

**Chart of Accounts:**
- Assets: Cash, Bank, Investments
- Liabilities: Accounts Payable
- Equity: Owner's Capital, Retained Earnings
- Revenue: Dividend Income, Interest Income, Capital Gains
- Expenses: Fees & Commissions, Tax Expense, Capital Losses

**Reconciliation:**
- Automatic matching of broker transactions to journal entries
- Manual reconciliation for discrepancies
- Reconciliation status tracking (RECONCILED, PENDING, DISCREPANCY)

**Tax Reporting:**
- Capital gains calculation (FIFO, LIFO, Average cost basis)
- Short-term vs long-term gains (365-day threshold)
- Dividend income tracking with tax withholding
- Annual tax summaries

**Financial Reports:**
- General Ledger - Transaction history by account
- Trial Balance - Account balances verification
- Income Statement - Revenue and expenses for period
- Balance Sheet - Assets, liabilities, and equity snapshot

---

## Troubleshooting

### "No market data" errors
- Set `ALPHA_VANTAGE_API_KEY` environment variable
- Install yfinance: `pip install yfinance`
- Check API rate limits (Alpha Vantage: 25 requests/day)

### Yahoo Finance connection errors
- Normal if behind firewall/VPN
- Alpha Vantage is used as primary source
- Cached data used as fallback

### Recommendations show 50/50 scores or "No technical data available"

**Root cause**: Technical indicators need ≥50 historical data points. Only latest price stored.

**Fix**:
1. Set Alpha Vantage API key (see "API Keys Setup" above)
2. Run: `python fetch_historical_data.py <portfolio-id>` (one-time setup)
3. Run: `stocks-helper recommendation refresh <portfolio-id>`

**Why**: Technical indicators (RSI, MACD, SMA50, etc.) calculate trends over time. Without historical data, only fundamental analysis works.

### No suggestions generated
- Ensure stocks are in database: `stocks-helper stock add-batch --tickers "..."`
- Stocks must have sector/country metadata

---

## Development

### Requirements
- Python 3.11-3.12
- SQLite 3.35+
- TA-Lib library (technical analysis)

### Setup Development Environment
```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (300 tests total)
pytest                      # All tests
pytest tests/unit/          # Unit tests only (203)
pytest tests/integration/   # Integration tests (32)
pytest tests/contract/      # Contract tests (65)

# Run pre-commit checks
pre-commit run --all-files

# Run linters
black src/ tests/
ruff check src/ tests/
mypy src/

# Generate coverage report
pytest --cov=src --cov-report=html
```

### Test Coverage
- **Total Tests**: 300 (all passing ✓)
- **Overall Coverage**: 41%
- **Core Services**: 93-98% coverage
  - Accounting Service: 96.77%
  - Ledger Reports: 98.58%
  - Tax Reporting: 93.21%
  - Reconciliation: 93.44%
  - Market Data: 78%
  - Recommendations: 87%

### Contributing
See [QUICKSTART.md](QUICKSTART.md) for detailed usage guide.

---

## License

This project is for personal use. No license granted for commercial use.

---

## Acknowledgments

- [Alpha Vantage](https://www.alphavantage.co/) - Market data API
- [Yahoo Finance](https://finance.yahoo.com/) - Fallback market data
- [TA-Lib](https://ta-lib.org/) - Technical analysis library
- [Plotly](https://plotly.com/) - Interactive charts

---

## Support

For issues or questions:
1. Check [QUICKSTART.md](QUICKSTART.md) for detailed examples
2. Review troubleshooting section above
3. Open an issue on GitHub

---

**Built with ❤️ for investors who want data-driven insights**
