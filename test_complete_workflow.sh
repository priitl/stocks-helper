#!/bin/bash
# Complete workflow test for stocks-helper

PID="55662f1a-aad2-49a9-bf0e-c2156c0e4d10"

echo "=== Stocks Helper - Complete Workflow Test ==="
echo ""

echo "1. Portfolio Overview"
stocks-helper portfolio show $PID
echo ""

echo "2. Holdings List"
stocks-helper holding list $PID
echo ""

echo "3. Generate Insights"
stocks-helper insight generate $PID
echo ""

echo "4. View Insights Dashboard"
stocks-helper insight show $PID
echo ""

echo "5. List Recommendations"
stocks-helper recommendation list $PID
echo ""

echo "6. Show Detailed Recommendation for AAPL"
stocks-helper recommendation show $PID --ticker AAPL
echo ""

echo "=== Test Complete ==="
