from src.lib.db import get_session
from src.models.stock import Stock

session = get_session()

# Add missing stock metadata
stocks_to_add = {
    "AAPL": {"name": "Apple Inc", "sector": "Technology", "market_cap": 3000000000000},
    "MSFT": {"name": "Microsoft Corp", "sector": "Technology", "market_cap": 2800000000000},
}

for ticker, data in stocks_to_add.items():
    existing = session.query(Stock).filter(Stock.ticker == ticker).first()
    if not existing:
        stock = Stock(
            ticker=ticker,
            exchange="NASDAQ",
            name=data["name"],
            currency="USD",
            sector=data["sector"],
            country="US",
            market_cap=data["market_cap"],
        )
        session.add(stock)
        print(f"✓ Added {ticker}")
    else:
        # Update sector if missing
        if not existing.sector or existing.sector == "Unknown":
            existing.sector = data["sector"]
            existing.name = data["name"]
            existing.market_cap = data["market_cap"]
            print(f"✓ Updated {ticker}")

session.commit()
print("Done!")
session.close()
