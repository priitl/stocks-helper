"""
SQLAlchemy models for the stocks-helper application.

All models inherit from the Base declarative class defined in src.lib.db.
"""

from src.models.account import Account
from src.models.bond import Bond, PaymentFrequency
from src.models.cashflow import Cashflow, CashflowStatus, CashflowType
from src.models.chart_of_accounts import AccountCategory, AccountType, ChartAccount
from src.models.exchange_rate import ExchangeRate
from src.models.fundamental_data import FundamentalData
from src.models.holding import Holding
from src.models.import_batch import ImportBatch, ImportStatus
from src.models.import_error import ImportError, ImportErrorType
from src.models.insight import Insight, InsightType
from src.models.journal import JournalEntry, JournalEntryStatus, JournalEntryType, JournalLine
from src.models.market_data import MarketData
from src.models.portfolio import Portfolio
from src.models.recommendation import (
    ConfidenceLevel,
    RecommendationType,
    StockRecommendation,
)
from src.models.reconciliation import Reconciliation, ReconciliationStatus
from src.models.security import Security, SecurityType
from src.models.stock_details import Stock
from src.models.stock_split import StockSplit
from src.models.suggestion import StockSuggestion, SuggestionType
from src.models.transaction import Transaction, TransactionType

__all__ = [
    # Core models
    "Portfolio",
    "Account",
    "Security",
    "Stock",
    "StockSplit",
    "Bond",
    "Holding",
    "Transaction",
    "Cashflow",
    # Import models
    "ImportBatch",
    "ImportError",
    # Market data
    "MarketData",
    "FundamentalData",
    # Analysis
    "StockRecommendation",
    "StockSuggestion",
    "Insight",
    # Currency
    "ExchangeRate",
    # Accounting
    "ChartAccount",
    "JournalEntry",
    "JournalLine",
    "Reconciliation",
    # Enums
    "SecurityType",
    "TransactionType",
    "CashflowType",
    "CashflowStatus",
    "PaymentFrequency",
    "ImportStatus",
    "ImportErrorType",
    "RecommendationType",
    "ConfidenceLevel",
    "SuggestionType",
    "InsightType",
    "AccountType",
    "AccountCategory",
    "JournalEntryType",
    "JournalEntryStatus",
    "ReconciliationStatus",
]
