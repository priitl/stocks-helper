"""Application configuration constants."""

# API Rate Limiting
API_RATE_LIMIT_DELAY = 15  # seconds between API requests
DEFAULT_CACHE_TTL = 900  # seconds (15 minutes)

# Recommendation Thresholds
RECOMMENDATION_BUY_THRESHOLD = 70  # Combined score above this = BUY
RECOMMENDATION_SELL_THRESHOLD = 30  # Combined score below this = SELL
# Scores between SELL and BUY thresholds = HOLD
