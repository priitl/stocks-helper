"""Application configuration constants."""

# API Rate Limiting
API_RATE_LIMIT_DELAY = 15  # seconds between API requests
DEFAULT_CACHE_TTL = 900  # seconds (15 minutes)

# Recommendation Thresholds
RECOMMENDATION_BUY_THRESHOLD = 70  # Combined score above this = BUY
RECOMMENDATION_SELL_THRESHOLD = 30  # Combined score below this = SELL
# Scores between SELL and BUY thresholds = HOLD

# Technical Analysis Thresholds
RSI_NEUTRAL_MIN = 40  # RSI above this = neutral/healthy
RSI_NEUTRAL_MAX = 60  # RSI below this = neutral/healthy
RSI_OVERSOLD = 30  # RSI at or below this = oversold (buy signal)
RSI_OVERSOLD_APPROACHING = 40  # RSI at or below this = approaching oversold
RSI_OVERBOUGHT = 70  # RSI at or above this = overbought (sell signal)
RSI_OVERBOUGHT_APPROACHING = 60  # RSI at or above this = approaching overbought

# Fundamental Analysis Thresholds
DIVIDEND_YIELD_GOOD = 0.03  # 3%+ = good dividend yield
DIVIDEND_YIELD_MIN = 0  # Any positive dividend

# Batch Processing
CIRCUIT_BREAKER_MAX_FAILURES = 5  # Stop processing after this many consecutive failures

# Technical Scoring Weights
# These weights are used to calculate the technical analysis score (0-100)
# The score is divided into categories with specific weight allocations:
#
# - Trend Analysis (30 points max):
#   - Price position relative to SMAs
#   - SMA crossovers (golden/death cross)
#   - MACD signals
#
# - Momentum Analysis (25 points max):
#   - RSI levels and positioning
#
# - Volatility Analysis (15 points max):
#   - Bollinger Bands positioning
#
# - Volume Analysis (10 points max):
#   - On-Balance Volume (OBV) trends

# Trend signals (30 points total)
TECHNICAL_SCORE_PRICE_ABOVE_SMA20 = 10  # Price above SMA20 (bullish)
TECHNICAL_SCORE_GOLDEN_CROSS = 15  # SMA20 > SMA50 (uptrend)
TECHNICAL_SCORE_MACD_POSITIVE = 5  # MACD > 0 (momentum)

# Momentum signals (25 points total - RSI based)
TECHNICAL_SCORE_RSI_NEUTRAL = 25  # RSI 40-60 (healthy)
TECHNICAL_SCORE_RSI_APPROACHING_OVERSOLD = 20  # RSI near 30 (buy opportunity)
TECHNICAL_SCORE_RSI_OVERSOLD = 15  # RSI ≤ 30 (strong buy signal)
TECHNICAL_SCORE_RSI_APPROACHING_OVERBOUGHT = 10  # RSI near 70 (caution)
TECHNICAL_SCORE_RSI_OVERBOUGHT = 0  # RSI ≥ 70 (sell signal)

# Volatility signals (15 points total - Bollinger Bands)
TECHNICAL_SCORE_BB_BELOW_LOWER = 15  # Price below lower band (oversold)
TECHNICAL_SCORE_BB_WITHIN = 8  # Price within bands (normal)
TECHNICAL_SCORE_BB_ABOVE_UPPER = 0  # Price above upper band (overbought)

# Volume signals (10 points total)
TECHNICAL_SCORE_POSITIVE_VOLUME = 10  # OBV trending up (accumulation)
