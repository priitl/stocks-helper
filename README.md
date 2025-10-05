# Stocks Helper - Personal Investment Tracker

A command-line tool for tracking your stock portfolio, managing holdings, and analyzing performance across multiple currencies.

## Current Status: MVP (Minimum Viable Product)

**Working Features:**
- ✅ Multi-currency portfolio management
- ✅ Stock holdings tracking with transaction history
- ✅ Weighted average price calculation
- ✅ Gain/loss tracking on sales
- ✅ SQLite database for local storage
- ✅ Rich CLI with formatted tables

**Coming Soon:**
- ⏳ Live market data integration
- ⏳ Stock recommendations (buy/sell/hold)
- ⏳ Portfolio insights and risk analysis
- ⏳ Automated daily updates
- ⏳ HTML reports with charts

## Installation

### Prerequisites

- Python 3.11 or higher
- pip package manager

### Quick Start

```bash
# Clone the repository
cd /Users/priitlaht/Repository/stocks-helper

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# OR: venv\Scripts\activate  # On Windows

# Install the package
pip install -e .

# Initialize the database
stocks-helper init
```

### Optional: Technical Analysis Libraries

For future features (recommendations, technical indicators), install optional dependencies:

```bash
# Note: TA-Lib requires system libraries
# macOS: brew install ta-lib
# Ubuntu: sudo apt-get install libta-lib-dev
# Then:
pip install -e ".[analysis]"
```

## Usage

### Initialize Database

```bash
stocks-helper init
```

This creates `~/.stocks-helper/data.db` and `~/.stocks-helper/cache/`

### Portfolio Management

```bash
# Create a portfolio
stocks-helper portfolio create --name "Main Portfolio" --currency USD

# List all portfolios
stocks-helper portfolio list

# Show portfolio details (uses first portfolio if no ID provided)
stocks-helper portfolio show
stocks-helper portfolio show <PORTFOLIO_ID>

# Change base currency
stocks-helper portfolio set-currency <PORTFOLIO_ID> --currency EUR
```

### Managing Holdings

```bash
# Add a stock purchase
stocks-helper holding add <PORTFOLIO_ID> \
  --ticker AAPL \
  --quantity 10 \
  --price 150.00 \
  --date 2024-01-15 \
  --currency USD \
  --fees 5.00

# Sell stocks
stocks-helper holding sell <PORTFOLIO_ID> \
  --ticker AAPL \
  --quantity 5 \
  --price 175.00 \
  --date 2024-03-15

# List all holdings in a portfolio
stocks-helper holding list <PORTFOLIO_ID>

# Show detailed holding information
stocks-helper holding show <PORTFOLIO_ID> --ticker AAPL
```

### Example Workflow

```bash
# 1. Initialize
stocks-helper init

# 2. Create portfolio
stocks-helper portfolio create --name "Tech Investments" --currency USD

# 3. Note the portfolio ID from output, then add stocks
PORTFOLIO_ID="<your-portfolio-id>"

stocks-helper holding add $PORTFOLIO_ID --ticker AAPL --quantity 10 --price 150 --date 2024-01-15
stocks-helper holding add $PORTFOLIO_ID --ticker MSFT --quantity 5 --price 350 --date 2024-02-01
stocks-helper holding add $PORTFOLIO_ID --ticker GOOGL --quantity 8 --price 140 --date 2024-02-15

# 4. View your portfolio
stocks-helper portfolio show $PORTFOLIO_ID
stocks-helper holding list $PORTFOLIO_ID

# 5. Record a sale
stocks-helper holding sell $PORTFOLIO_ID --ticker AAPL --quantity 3 --price 175 --date 2024-10-01

# 6. Check updated holdings
stocks-helper holding show $PORTFOLIO_ID --ticker AAPL
```

## Features

### Multi-Currency Support

- Track stocks in their native currencies (USD, EUR, GBP, etc.)
- Set a base currency for your portfolio
- Automatic currency conversion (exchange rates to be implemented)

### Transaction History

- Complete buy/sell transaction log
- Tracks purchase price, quantity, fees
- Calculates gains/losses on sales
- Maintains historical records

### Portfolio Analytics (Current MVP)

- Weighted average purchase price
- Total cost basis
- Holdings count and summary
- Gain/loss per transaction

### Rich CLI Experience

- Color-coded output (green for gains, red for losses)
- Formatted tables for easy reading
- Helpful error messages
- Input validation

## Project Structure

```
stocks-helper/
├── src/
│   ├── models/          # SQLAlchemy database models
│   ├── services/        # Business logic (future)
│   ├── cli/             # Command-line interface
│   └── lib/             # Utilities (db, api client)
├── tests/               # Test suite
├── specs/               # Feature specifications
├── docs/                # Documentation
└── pyproject.toml       # Project configuration
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/
```

## Database

- **Location**: `~/.stocks-helper/data.db`
- **Type**: SQLite 3
- **Backup**: Simply copy the `.stocks-helper` directory

### Reset Database

```bash
stocks-helper init --reset
```

⚠️ **Warning**: This deletes all data!

## Troubleshooting

### "ModuleNotFoundError: No module named 'click'"

Install the package first:
```bash
pip install -e .
```

### "Database already exists"

Use `--reset` flag to recreate (deletes all data):
```bash
stocks-helper init --reset
```

### TA-Lib installation fails

TA-Lib requires system libraries. Install them first:
- **macOS**: `brew install ta-lib`
- **Ubuntu/Debian**: `sudo apt-get install libta-lib-dev`
- **Windows**: Download from https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib

## Contributing

This is a personal project following TDD principles. See `specs/001-stocks-tracker-analyzer/` for feature specifications and implementation plan.

## License

Personal use project.

## Roadmap

### Phase 1: MVP ✅ (Current)
- Basic portfolio and holdings management
- Transaction tracking
- Local database

### Phase 2: Market Data (Next)
- Integration with Alpha Vantage / Yahoo Finance
- Live price updates
- Historical data fetching

### Phase 3: Analysis
- Technical indicators (RSI, MACD, Moving Averages)
- Fundamental analysis (P/E, ROE, etc.)
- Buy/sell/hold recommendations

### Phase 4: Insights
- Portfolio allocation analysis
- Diversification suggestions
- Risk metrics
- Performance benchmarking

### Phase 5: Automation
- Daily batch updates
- Automated recommendations refresh
- HTML report generation

## Questions or Issues?

See `specs/001-stocks-tracker-analyzer/quickstart.md` for detailed usage scenarios.
