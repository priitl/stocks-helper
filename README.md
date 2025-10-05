# Stocks Helper

**Personal Stocks Tracker & Analyzer** - A comprehensive CLI tool for tracking your stock portfolio, analyzing performance, and receiving AI-powered investment recommendations.

## Features

### Portfolio Management
- 📊 **Multi-portfolio support** - Track multiple investment portfolios
- 💱 **Multi-currency** - Support for different base currencies with automatic conversion
- 📈 **Holdings tracking** - Buy/sell transactions with cost basis calculation
- 💰 **Real-time valuations** - Current portfolio value and gain/loss tracking

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

For best experience, set up API keys (all optional but recommended):

```bash
# Alpha Vantage (market data) - Get free key at https://www.alphavantage.co/support/#api-key
export ALPHA_VANTAGE_API_KEY="your-key-here"

# ExchangeRate-API (currency conversion) - Get free key at https://www.exchangerate-api.com/
export EXCHANGE_RATE_API_KEY="your-key-here"
```

---

## Usage Example

```bash
# Create a portfolio
stocks-helper portfolio create --name "My Portfolio" --currency USD
export PID="<portfolio-id-from-output>"

# Add stocks
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
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic
│   ├── cli/              # CLI commands
│   └── lib/              # Utilities (DB, API, cache, errors)
├── specs/                # Feature specifications
├── reports/              # Generated HTML reports
└── tests/                # Test suite
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

### Recommendations show 50/50 scores
- No market data fetched yet
- Run: `stocks-helper recommendation refresh <portfolio-id>`
- Wait for API rate limits to reset if exceeded

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

# Run tests
pytest

# Run linters
black src/ tests/
ruff check src/ tests/

# Generate coverage report
pytest --cov=src --cov-report=html
```

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
