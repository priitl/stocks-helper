#!/bin/bash
# Demo script for Stocks Helper

PID="55662f1a-aad2-49a9-bf0e-c2156c0e4d10"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         Stocks Helper - Feature Demonstration              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

echo "📊 1. PORTFOLIO OVERVIEW"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
stocks-helper portfolio show $PID
echo ""

echo "📈 2. CURRENT HOLDINGS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
stocks-helper holding list $PID
echo ""

echo "🗄️  3. AVAILABLE STOCKS IN DATABASE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
stocks-helper stock list
echo ""

echo "🎯 4. STOCK RECOMMENDATIONS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
stocks-helper recommendation list $PID
echo ""

echo "🔍 5. DETAILED RECOMMENDATION - AAPL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
stocks-helper recommendation show $PID --ticker AAPL
echo ""

echo "💡 6. PORTFOLIO INSIGHTS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
stocks-helper insight show $PID
echo ""

echo "✅ Demo Complete!"
echo ""
echo "Try these commands yourself:"
echo "  stocks-helper --help"
echo "  stocks-helper recommendation refresh $PID"
echo "  stocks-helper stock add-batch --tickers \"TSLA,AMZN,WMT\""
