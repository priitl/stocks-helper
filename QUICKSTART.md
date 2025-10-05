# Stocks Helper - Quick Start Guide

## 🚀 Setup

```bash
# 1. Set your API keys (optional but recommended)
export ALPHA_VANTAGE_API_KEY="your-key-here"
export EXCHANGE_RATE_API_KEY="your-key-here"  # Optional

# 2. Install yfinance for fallback (optional)
pip install yfinance

# 3. Initialize database
stocks-helper init
```

## 📊 Basic Workflow

### Step 1: Create Portfolio

```bash
# Create your portfolio
stocks-helper portfolio create --name "My Portfolio" --currency USD

# List all portfolios to get ID
stocks-helper portfolio list

# Set portfolio ID for convenience
export PID="your-portfolio-id-here"
```

### Step 2: Add Holdings

```bash
# Add stock purchases
stocks-helper holding add $PID \
  --ticker AAPL \
  --quantity 10 \
  --price 150.00 \
  --date 2024-01-15

stocks-helper holding add $PID \
  --ticker MSFT \
  --quantity 5 \
  --price 350.00 \
  --date 2024-02-01

# View your holdings
stocks-helper holding list $PID
```

### Step 3: Get Recommendations

```bash
# Generate fresh recommendations
stocks-helper recommendation refresh $PID

# View all recommendations
stocks-helper recommendation list $PID

# View detailed analysis for specific stock
stocks-helper recommendation show $PID --ticker AAPL
```

### Step 4: View Insights

```bash
# Generate portfolio insights
stocks-helper insight generate $PID

# View comprehensive analytics dashboard
stocks-helper insight show $PID
```

## 🛠️ Advanced Features

### Stock Management

```bash
# Add stocks to database (required for suggestions)
stocks-helper stock add-batch --tickers "NVDA,AMD,INTC,TSM"

# List all stocks in database
stocks-helper stock list

# Remove stock
stocks-helper stock remove --ticker NVDA
```

### Suggestions for New Stocks

```bash
# Generate suggestions for candidate stocks
stocks-helper suggestion generate $PID --tickers "JPM,JNJ,XOM,DIS"

# View suggestions
stocks-helper suggestion list $PID

# Filter by type
stocks-helper suggestion list $PID --type DIVERSIFICATION
stocks-helper suggestion list $PID --type SIMILAR_TO_WINNERS
stocks-helper suggestion list $PID --type MARKET_OPPORTUNITY

# Show detailed suggestion
stocks-helper suggestion show $PID --ticker JPM
```

### Portfolio Management

```bash
# Show portfolio details
stocks-helper portfolio show $PID

# Change base currency
stocks-helper portfolio set-currency $PID --currency EUR

# Sell stocks
stocks-helper holding sell $PID \
  --ticker AAPL \
  --quantity 3 \
  --price 175.00 \
  --date 2024-10-01

# View transaction history
stocks-helper holding show $PID --ticker AAPL
```

## 📈 Understanding Recommendations

### Recommendation Types

- **BUY** (score > 70) - Strong technical + fundamental signals
- **SELL** (score < 30) - Weak signals, consider selling
- **HOLD** (30-70) - Mixed or neutral signals

### Confidence Levels

- **HIGH** - Technical & fundamental signals agree
- **MEDIUM** - Signals mostly aligned
- **LOW** - Conflicting signals

### Scores Breakdown

Each recommendation shows:
- **Technical Score** (0-100) - Based on RSI, MACD, SMA, Bollinger Bands, etc.
- **Fundamental Score** (0-100) - Based on P/E, growth, profitability, margins
- **Combined Score** - Average of both (determines BUY/SELL/HOLD)

## 🎯 Insights Explained

### Sector Allocation
Shows percentage allocated to each sector
- ⚠️ Warns if >40% in one sector (concentration risk)

### Geographic Distribution  
Shows percentage by country/region

### Diversification Gaps
Identifies sectors/regions with <10% allocation

### Top Performers
Ranks holdings by gain/loss percentage

### Risk Assessment
Portfolio value and risk metrics (requires historical data)

## 🐛 Troubleshooting

### "No market data"
- Set `ALPHA_VANTAGE_API_KEY` environment variable
- Install yfinance: `pip install yfinance`
- Check API rate limits (Alpha Vantage: 25 req/day)

### "No suggestions generated"
- Ensure stocks are in database: `stocks-helper stock add-batch --tickers "..."`
- Stocks must have sector/country metadata

### Yahoo Finance connection errors
- Normal if behind firewall/VPN
- Alpha Vantage is used as primary source

### Recommendations show 50/50 scores
- No market data fetched yet
- Run `stocks-helper recommendation refresh $PID`
- Wait for API rate limits if exceeded

## 📚 All Commands

```bash
# Help
stocks-helper --help
stocks-helper [command] --help

# Portfolio
stocks-helper portfolio create --name NAME --currency CURR
stocks-helper portfolio list
stocks-helper portfolio show [ID]
stocks-helper portfolio set-currency ID --currency CURR

# Holdings
stocks-helper holding add ID --ticker X --quantity N --price P --date D
stocks-helper holding sell ID --ticker X --quantity N --price P --date D
stocks-helper holding list ID
stocks-helper holding show ID --ticker X

# Stocks
stocks-helper stock add-batch --tickers "X,Y,Z"
stocks-helper stock list
stocks-helper stock remove --ticker X

# Recommendations
stocks-helper recommendation list ID [--action BUY|SELL|HOLD]
stocks-helper recommendation show ID --ticker X
stocks-helper recommendation refresh ID [--ticker X]

# Suggestions
stocks-helper suggestion generate ID --tickers "X,Y,Z"
stocks-helper suggestion list ID [--type TYPE] [--limit N]
stocks-helper suggestion show ID --ticker X

# Insights
stocks-helper insight generate ID
stocks-helper insight show ID
```

## 🎉 Demo Script

Run `./demo.sh` to see all features in action!
