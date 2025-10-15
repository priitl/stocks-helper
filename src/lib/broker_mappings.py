"""
Broker-specific transaction type mappings.

Maps broker transaction codes to standardized TransactionType enum.
"""

from src.models.transaction import TransactionType

# Swedbank transaction type mapping
# Format: (Tehingu tüüp, Deebet/Kreedit) -> TransactionType or None (skip)
SWEDBANK_TYPE_MAPPING: dict[tuple[str, str], TransactionType | None] = {
    # Stock transactions (M) - determined by pattern matching
    ("M", "D"): None,  # BUY, SELL, or FEE - check description pattern
    ("M", "K"): None,  # SELL or DIVIDEND - check description pattern
    # Account transfers
    ("MK", "K"): TransactionType.DEPOSIT,  # Money in
    ("MK", "D"): TransactionType.WITHDRAWAL,  # Money out
    # Interest
    ("I", "K"): TransactionType.INTEREST,  # Deposit interest
    # Currency conversions
    ("X", "D"): TransactionType.CONVERSION,  # Debit from source currency
    ("X", "K"): TransactionType.CONVERSION,  # Credit to target currency
    # VAT on custody fees
    ("KM", "D"): TransactionType.TAX,  # Käibemaks (VAT)
    # Skip these (summaries/balances)
    ("AS", "K"): None,  # Algsaldo (opening balance)
    ("LS", "K"): None,  # Lõppsaldo (closing balance)
    ("K2", "D"): None,  # Käive (turnover summary)
    ("K2", "K"): None,  # Käive (turnover summary)
}

# Lightyear transaction type mapping
# Direct mapping from Lightyear's "Type" column
LIGHTYEAR_TYPE_MAPPING: dict[str, TransactionType] = {
    "Buy": TransactionType.BUY,
    "Sell": TransactionType.SELL,
    "Dividend": TransactionType.DIVIDEND,
    "Distribution": TransactionType.DISTRIBUTION,
    "Conversion": TransactionType.CONVERSION,
    "Deposit": TransactionType.DEPOSIT,
    "Withdrawal": TransactionType.WITHDRAWAL,
    "Interest": TransactionType.INTEREST,
    "Reward": TransactionType.REWARD,
    "Fee": TransactionType.FEE,
}
