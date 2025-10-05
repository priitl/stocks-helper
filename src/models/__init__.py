"""
SQLAlchemy models for the stocks-helper application.

All models inherit from the Base declarative class defined in src.lib.db.
"""

from src.models.exchange_rate import ExchangeRate
from src.models.fundamental_data import FundamentalData
from src.models.holding import Holding
from src.models.insight import Insight, InsightType
from src.models.market_data import MarketData
from src.models.portfolio import Portfolio
from src.models.recommendation import (
    ConfidenceLevel,
    RecommendationType,
    StockRecommendation,
)
from src.models.stock import Stock
from src.models.suggestion import StockSuggestion, SuggestionType
from src.models.transaction import Transaction, TransactionType

__all__ = [
    # Core models
    "Portfolio",
    "Stock",
    "Holding",
    "Transaction",
    # Market data
    "MarketData",
    "FundamentalData",
    # Analysis
    "StockRecommendation",
    "StockSuggestion",
    "Insight",
    # Currency
    "ExchangeRate",
    # Enums
    "TransactionType",
    "RecommendationType",
    "ConfidenceLevel",
    "SuggestionType",
    "InsightType",
]
