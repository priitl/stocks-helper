"""Insight generator for portfolio-level analysis."""

from datetime import datetime
from typing import Optional

from src.lib.db import get_session
from src.models.holding import Holding
from src.models.insight import Insight, InsightType
from src.models.market_data import MarketData
from src.models.stock import Stock


class InsightGenerator:
    """Generates portfolio-level insights and analytics."""

    def __init__(self):
        """Initialize insight generator."""
        pass

    def generate_sector_allocation(self, portfolio_id: str) -> Optional[Insight]:
        """
        Generate sector allocation insight.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Insight object or None
        """
        session = get_session()
        try:
            holdings = (
                session.query(Holding)
                .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
                .all()
            )

            if not holdings:
                return None

            sector_allocation = {}
            total_value = 0

            for holding in holdings:
                stock = session.query(Stock).filter(Stock.ticker == holding.ticker).first()
                if not stock:
                    continue

                # Get current price
                market_data = (
                    session.query(MarketData)
                    .filter(MarketData.ticker == holding.ticker, MarketData.is_latest == True)
                    .first()
                )

                if market_data:
                    value = holding.quantity * market_data.price
                else:
                    value = holding.quantity * holding.avg_purchase_price

                total_value += value

                sector = stock.sector or "Unknown"
                sector_allocation[sector] = sector_allocation.get(sector, 0) + value

            # Convert to percentages
            sector_pct = {}
            concentration_risk = False
            concentrated_sector = None

            for sector, value in sector_allocation.items():
                pct = (float(value) / float(total_value)) * 100 if total_value > 0 else 0
                sector_pct[sector] = round(pct, 2)

                # Check for concentration risk (> 40%)
                if pct > 40:
                    concentration_risk = True
                    concentrated_sector = sector

            # Create insight data (convert Decimal to float for JSON serialization)
            data = {
                "allocation": sector_pct,
                "concentration_risk": concentration_risk,
                "concentrated_sector": concentrated_sector,
                "total_value": float(total_value),
            }

            summary = f"Portfolio allocated across {len(sector_pct)} sectors."
            if concentration_risk:
                summary += f" ⚠️ High concentration in {concentrated_sector} ({sector_pct[concentrated_sector]:.1f}%)."

            insight = Insight(
                portfolio_id=portfolio_id,
                timestamp=datetime.now(),
                insight_type=InsightType.SECTOR_ALLOCATION,
                data=data,
                summary=summary,
            )

            session.add(insight)
            session.commit()
            session.refresh(insight)

            return insight

        except Exception as e:
            session.rollback()
            print(f"Failed to generate sector allocation insight: {e}")
            return None
        finally:
            session.close()

    def generate_geo_allocation(self, portfolio_id: str) -> Optional[Insight]:
        """
        Generate geographic allocation insight.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Insight object or None
        """
        session = get_session()
        try:
            holdings = (
                session.query(Holding)
                .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
                .all()
            )

            if not holdings:
                return None

            geo_allocation = {}
            total_value = 0

            for holding in holdings:
                stock = session.query(Stock).filter(Stock.ticker == holding.ticker).first()
                if not stock:
                    continue

                # Get current price
                market_data = (
                    session.query(MarketData)
                    .filter(MarketData.ticker == holding.ticker, MarketData.is_latest == True)
                    .first()
                )

                if market_data:
                    value = holding.quantity * market_data.price
                else:
                    value = holding.quantity * holding.avg_purchase_price

                total_value += value

                country = stock.country or "Unknown"
                geo_allocation[country] = geo_allocation.get(country, 0) + value

            # Convert to percentages
            geo_pct = {
                country: round((float(value) / float(total_value)) * 100, 2) if total_value > 0 else 0
                for country, value in geo_allocation.items()
            }

            data = {
                "allocation": geo_pct,
                "total_value": float(total_value),
            }

            summary = f"Portfolio spans {len(geo_pct)} countries/regions."

            insight = Insight(
                portfolio_id=portfolio_id,
                timestamp=datetime.now(),
                insight_type=InsightType.GEO_ALLOCATION,
                data=data,
                summary=summary,
            )

            session.add(insight)
            session.commit()
            session.refresh(insight)

            return insight

        except Exception as e:
            session.rollback()
            print(f"Failed to generate geo allocation insight: {e}")
            return None
        finally:
            session.close()

    def generate_diversification_gaps(self, portfolio_id: str) -> Optional[Insight]:
        """
        Generate diversification gap analysis.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Insight object or None
        """
        session = get_session()
        try:
            holdings = (
                session.query(Holding)
                .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
                .all()
            )

            if not holdings:
                return None

            sector_allocation = {}
            geo_allocation = {}
            total_value = 0

            for holding in holdings:
                stock = session.query(Stock).filter(Stock.ticker == holding.ticker).first()
                if not stock:
                    continue

                market_data = (
                    session.query(MarketData)
                    .filter(MarketData.ticker == holding.ticker, MarketData.is_latest == True)
                    .first()
                )

                if market_data:
                    value = holding.quantity * market_data.price
                else:
                    value = holding.quantity * holding.avg_purchase_price

                total_value += value

                sector = stock.sector or "Unknown"
                sector_allocation[sector] = sector_allocation.get(sector, 0) + value

                country = stock.country or "Unknown"
                geo_allocation[country] = geo_allocation.get(country, 0) + value

            # Find gaps (< 10%)
            sector_gaps = []
            for sector, value in sector_allocation.items():
                pct = (float(value) / float(total_value)) * 100 if total_value > 0 else 0
                if pct < 10:
                    sector_gaps.append({"sector": sector, "percentage": round(pct, 2)})

            geo_gaps = []
            for country, value in geo_allocation.items():
                pct = (float(value) / float(total_value)) * 100 if total_value > 0 else 0
                if pct < 10:
                    geo_gaps.append({"country": country, "percentage": round(pct, 2)})

            data = {
                "sector_gaps": sector_gaps,
                "geo_gaps": geo_gaps,
            }

            summary = f"Found {len(sector_gaps)} underrepresented sectors and {len(geo_gaps)} underrepresented regions."

            insight = Insight(
                portfolio_id=portfolio_id,
                timestamp=datetime.now(),
                insight_type=InsightType.DIVERSIFICATION_GAP,
                data=data,
                summary=summary,
            )

            session.add(insight)
            session.commit()
            session.refresh(insight)

            return insight

        except Exception as e:
            session.rollback()
            print(f"Failed to generate diversification gaps: {e}")
            return None
        finally:
            session.close()

    def generate_high_performers(self, portfolio_id: str) -> Optional[Insight]:
        """
        Generate high performers insight (top 3 by gain/loss %).

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Insight object or None
        """
        session = get_session()
        try:
            holdings = (
                session.query(Holding)
                .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
                .all()
            )

            if not holdings:
                return None

            performers = []

            for holding in holdings:
                market_data = (
                    session.query(MarketData)
                    .filter(MarketData.ticker == holding.ticker, MarketData.is_latest == True)
                    .first()
                )

                if market_data:
                    current_value = holding.quantity * market_data.price
                    cost_basis = holding.quantity * holding.avg_purchase_price
                    gain_loss_pct = ((current_value - cost_basis) / cost_basis) * 100 if cost_basis > 0 else 0

                    performers.append({
                        "ticker": holding.ticker,
                        "gain_loss_pct": round(gain_loss_pct, 2),
                        "current_value": current_value,
                        "cost_basis": cost_basis,
                    })

            # Sort by gain/loss % descending
            performers.sort(key=lambda x: x["gain_loss_pct"], reverse=True)

            # Top 3
            top_performers = performers[:3]

            data = {
                "top_performers": top_performers,
            }

            if top_performers:
                summary = f"Top performer: {top_performers[0]['ticker']} ({top_performers[0]['gain_loss_pct']:+.1f}%)"
            else:
                summary = "No performance data available"

            insight = Insight(
                portfolio_id=portfolio_id,
                timestamp=datetime.now(),
                insight_type=InsightType.HIGH_PERFORMERS,
                data=data,
                summary=summary,
            )

            session.add(insight)
            session.commit()
            session.refresh(insight)

            return insight

        except Exception as e:
            session.rollback()
            print(f"Failed to generate high performers: {e}")
            return None
        finally:
            session.close()

    def generate_risk_assessment(self, portfolio_id: str) -> Optional[Insight]:
        """
        Generate risk assessment insight.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Insight object or None
        """
        session = get_session()
        try:
            holdings = (
                session.query(Holding)
                .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
                .all()
            )

            if not holdings:
                return None

            # Simple risk metrics
            total_value = 0
            volatilities = []

            for holding in holdings:
                market_data = (
                    session.query(MarketData)
                    .filter(MarketData.ticker == holding.ticker, MarketData.is_latest == True)
                    .first()
                )

                if market_data:
                    total_value += holding.quantity * market_data.price

            # Placeholder risk metrics (would need historical data for real calculation)
            data = {
                "portfolio_value": float(total_value),
                "volatility": None,  # Requires historical data
                "sharpe_ratio": None,  # Requires historical data
                "beta": None,  # Requires benchmark data
            }

            summary = f"Portfolio value: ${float(total_value):,.2f}. Risk metrics require historical data."

            insight = Insight(
                portfolio_id=portfolio_id,
                timestamp=datetime.now(),
                insight_type=InsightType.RISK_ASSESSMENT,
                data=data,
                summary=summary,
            )

            session.add(insight)
            session.commit()
            session.refresh(insight)

            return insight

        except Exception as e:
            session.rollback()
            print(f"Failed to generate risk assessment: {e}")
            return None
        finally:
            session.close()

    def generate_all_insights(self, portfolio_id: str) -> list[Insight]:
        """
        Generate all insights for a portfolio.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            List of generated insights
        """
        insights = []

        # Generate each type
        sector = self.generate_sector_allocation(portfolio_id)
        if sector:
            insights.append(sector)

        geo = self.generate_geo_allocation(portfolio_id)
        if geo:
            insights.append(geo)

        gaps = self.generate_diversification_gaps(portfolio_id)
        if gaps:
            insights.append(gaps)

        performers = self.generate_high_performers(portfolio_id)
        if performers:
            insights.append(performers)

        risk = self.generate_risk_assessment(portfolio_id)
        if risk:
            insights.append(risk)

        return insights
