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
