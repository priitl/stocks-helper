"""Recommendation engine for buy/sell/hold decisions."""

import logging
from datetime import datetime
from typing import Optional

from src.lib.config import (
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    DIVIDEND_SCORE_GOOD,
    DIVIDEND_SCORE_PAYING,
    DIVIDEND_YIELD_GOOD,
    FUNDAMENTAL_WEIGHT_FINANCIAL_HEALTH,
    FUNDAMENTAL_WEIGHT_GROWTH,
    FUNDAMENTAL_WEIGHT_PROFITABILITY,
    FUNDAMENTAL_WEIGHT_VALUATION,
    RECOMMENDATION_BUY_THRESHOLD,
    RECOMMENDATION_SELL_THRESHOLD,
    RSI_NEUTRAL_MAX,
    RSI_NEUTRAL_MIN,
    RSI_OVERBOUGHT,
    RSI_OVERBOUGHT_APPROACHING,
    RSI_OVERSOLD,
    RSI_OVERSOLD_APPROACHING,
    TECHNICAL_SCORE_BB_ABOVE_UPPER,
    TECHNICAL_SCORE_BB_BELOW_LOWER,
    TECHNICAL_SCORE_BB_WITHIN,
    TECHNICAL_SCORE_GOLDEN_CROSS,
    TECHNICAL_SCORE_MACD_POSITIVE,
    TECHNICAL_SCORE_POSITIVE_VOLUME,
    TECHNICAL_SCORE_PRICE_ABOVE_SMA20,
    TECHNICAL_SCORE_RSI_APPROACHING_OVERBOUGHT,
    TECHNICAL_SCORE_RSI_APPROACHING_OVERSOLD,
    TECHNICAL_SCORE_RSI_NEUTRAL,
    TECHNICAL_SCORE_RSI_OVERBOUGHT,
    TECHNICAL_SCORE_RSI_OVERSOLD,
)
from src.lib.db import db_session
from src.models.recommendation import ConfidenceLevel, RecommendationType, StockRecommendation
from src.services.fundamental_analyzer import FundamentalAnalyzer
from src.services.indicator_calculator import IndicatorCalculator

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Generates buy/sell/hold recommendations using combined analysis."""

    def __init__(self) -> None:
        """Initialize recommendation engine."""
        self.indicator_calc = IndicatorCalculator()
        self.fundamental_analyzer = FundamentalAnalyzer()

    def calculate_technical_score(self, indicators: dict[str, float]) -> tuple[int, list[str]]:
        """
        Calculate technical analysis score (0-100).

        Weighting:
        - Trend: 30%
        - Momentum: 25%
        - Volatility: 15%
        - Volume: 10%

        Args:
            indicators: Dict of technical indicators

        Returns:
            Tuple of (score, signals list)
        """
        score = 0
        signals = []

        # Trend analysis (30 points)
        if "sma_20" in indicators and "sma_50" in indicators:
            current_price = indicators.get("close", indicators.get("sma_20", 0))

            # Price above SMA20
            if current_price > indicators["sma_20"]:
                score += TECHNICAL_SCORE_PRICE_ABOVE_SMA20
                signals.append("Price above SMA20 (bullish)")
            else:
                signals.append("Price below SMA20 (bearish)")

            # SMA20 above SMA50 (golden cross region)
            if indicators["sma_20"] > indicators["sma_50"]:
                score += TECHNICAL_SCORE_GOLDEN_CROSS
                signals.append("SMA20 > SMA50 (uptrend)")
            else:
                signals.append("SMA20 < SMA50 (downtrend)")

            # MACD
            if "macd_hist" in indicators:
                if indicators["macd_hist"] > 0:
                    score += TECHNICAL_SCORE_MACD_POSITIVE
                    signals.append("MACD positive (bullish)")

        # Momentum analysis (25 points)
        if "rsi_14" in indicators:
            rsi = indicators["rsi_14"]

            if RSI_NEUTRAL_MIN < rsi < RSI_NEUTRAL_MAX:
                score += TECHNICAL_SCORE_RSI_NEUTRAL
                signals.append("RSI neutral (healthy)")
            elif RSI_OVERSOLD < rsi <= RSI_OVERSOLD_APPROACHING:
                score += TECHNICAL_SCORE_RSI_APPROACHING_OVERSOLD
                signals.append("RSI approaching oversold (buying opportunity)")
            elif rsi <= RSI_OVERSOLD:
                score += TECHNICAL_SCORE_RSI_OVERSOLD
                signals.append("RSI oversold (strong buy signal)")
            elif RSI_OVERBOUGHT_APPROACHING <= rsi < RSI_OVERBOUGHT:
                score += TECHNICAL_SCORE_RSI_APPROACHING_OVERBOUGHT
                signals.append("RSI approaching overbought")
            elif rsi >= RSI_OVERBOUGHT:
                score += TECHNICAL_SCORE_RSI_OVERBOUGHT
                signals.append("RSI overbought (sell signal)")

        # Volatility analysis (15 points)
        if "bb_upper" in indicators and "bb_lower" in indicators:
            current_price = indicators.get("close", 0)

            if current_price < indicators["bb_lower"]:
                score += TECHNICAL_SCORE_BB_BELOW_LOWER
                signals.append("Price below lower BB (oversold)")
            elif current_price > indicators["bb_upper"]:
                score += TECHNICAL_SCORE_BB_ABOVE_UPPER
                signals.append("Price above upper BB (overbought)")
            else:
                score += TECHNICAL_SCORE_BB_WITHIN
                signals.append("Price within Bollinger Bands")

        # Volume analysis (10 points)
        if "obv" in indicators:
            # Simplified: assume positive OBV trend is bullish
            if indicators["obv"] > 0:
                score += TECHNICAL_SCORE_POSITIVE_VOLUME
                signals.append("Positive volume trend")

        return min(score, 100), signals

    def calculate_fundamental_score(self, ticker: str) -> tuple[int, list[str]]:
        """
        Calculate fundamental analysis score (0-100).

        Weighting:
        - Valuation: 30%
        - Growth: 25%
        - Profitability: 20%
        - Financial health: 15%
        - Dividends: 10%

        Args:
            ticker: Stock ticker

        Returns:
            Tuple of (score, signals list)
        """
        fundamentals = self.fundamental_analyzer.get_latest_fundamentals(ticker)
        if not fundamentals:
            return 50, ["No fundamental data available"]

        total_score = 0
        all_signals = []

        # Valuation (30%)
        valuation = self.fundamental_analyzer.analyze_valuation(fundamentals)
        total_score += valuation["score"] * FUNDAMENTAL_WEIGHT_VALUATION
        all_signals.extend(valuation["signals"])

        # Growth (25%)
        growth = self.fundamental_analyzer.analyze_growth(fundamentals)
        total_score += growth["score"] * FUNDAMENTAL_WEIGHT_GROWTH
        all_signals.extend(growth["signals"])

        # Profitability (20%)
        profitability = self.fundamental_analyzer.analyze_profitability(fundamentals)
        total_score += profitability["score"] * FUNDAMENTAL_WEIGHT_PROFITABILITY
        all_signals.extend(profitability["signals"])

        # Financial health (15%)
        health = self.fundamental_analyzer.analyze_financial_health(fundamentals)
        total_score += health["score"] * FUNDAMENTAL_WEIGHT_FINANCIAL_HEALTH
        all_signals.extend(health["signals"])

        # Dividends (10%)
        if (
            fundamentals.dividend_yield is not None
            and fundamentals.dividend_yield > DIVIDEND_YIELD_GOOD
        ):
            total_score += DIVIDEND_SCORE_GOOD
            all_signals.append(f"Good dividend yield ({fundamentals.dividend_yield:.1%})")
        elif fundamentals.dividend_yield is not None and fundamentals.dividend_yield > 0:
            total_score += DIVIDEND_SCORE_PAYING
            all_signals.append(f"Dividend paying ({fundamentals.dividend_yield:.1%})")

        return int(total_score), all_signals

    def determine_recommendation(
        self, technical_score: int, fundamental_score: int
    ) -> tuple[RecommendationType, ConfidenceLevel]:
        """
        Determine buy/sell/hold recommendation and confidence level.

        Args:
            technical_score: Technical analysis score (0-100)
            fundamental_score: Fundamental analysis score (0-100)

        Returns:
            Tuple of (recommendation, confidence)
        """
        combined_score = (technical_score + fundamental_score) / 2

        # Determine recommendation
        if combined_score > RECOMMENDATION_BUY_THRESHOLD:
            recommendation = RecommendationType.BUY
        elif combined_score < RECOMMENDATION_SELL_THRESHOLD:
            recommendation = RecommendationType.SELL
        else:
            recommendation = RecommendationType.HOLD

        # Determine confidence based on signal alignment
        score_diff = abs(technical_score - fundamental_score)

        if score_diff < CONFIDENCE_HIGH_THRESHOLD:  # Both agree strongly
            confidence = ConfidenceLevel.HIGH
        elif score_diff < CONFIDENCE_MEDIUM_THRESHOLD:  # Mostly aligned
            confidence = ConfidenceLevel.MEDIUM
        else:  # Conflicting signals
            confidence = ConfidenceLevel.LOW

        return recommendation, confidence

    def generate_rationale(
        self,
        recommendation: RecommendationType,
        technical_score: int,
        fundamental_score: int,
        technical_signals: list[str],
        fundamental_signals: list[str],
    ) -> str:
        """Generate human-readable rationale for recommendation."""
        combined_score = (technical_score + fundamental_score) / 2

        rationale_parts = [
            f"Recommendation: {recommendation.value}",
            f"Combined Score: {combined_score:.0f}/100 "
            f"(Technical: {technical_score}, Fundamental: {fundamental_score})",
            "",
            "Technical Analysis:",
        ]

        rationale_parts.extend([f"  • {signal}" for signal in technical_signals[:5]])

        rationale_parts.extend(["", "Fundamental Analysis:"])
        rationale_parts.extend([f"  • {signal}" for signal in fundamental_signals[:5]])

        return "\n".join(rationale_parts)

    async def generate_recommendation(
        self, ticker: str, portfolio_id: str
    ) -> Optional[StockRecommendation]:
        """
        Generate comprehensive stock recommendation.

        Args:
            ticker: Stock ticker
            portfolio_id: Portfolio ID

        Returns:
            StockRecommendation object or None
        """
        # Calculate technical score
        indicators: Optional[dict[str, float]] = self.indicator_calc.calculate_all_indicators(
            ticker
        )
        technical_score: int
        technical_signals: list[str]
        if indicators:
            technical_score, technical_signals = self.calculate_technical_score(indicators)
        else:
            technical_score, technical_signals = 50, ["No technical data available"]

        # Calculate fundamental score
        fundamental_score: int
        fundamental_signals: list[str]
        fundamental_score, fundamental_signals = self.calculate_fundamental_score(ticker)

        # Determine recommendation and confidence
        recommendation: RecommendationType
        confidence: ConfidenceLevel
        recommendation, confidence = self.determine_recommendation(
            technical_score, fundamental_score
        )

        # Generate rationale
        rationale: str = self.generate_rationale(
            recommendation,
            technical_score,
            fundamental_score,
            technical_signals,
            fundamental_signals,
        )

        # Combined score
        combined_score: int = int((technical_score + fundamental_score) / 2)

        # Store in database
        try:
            from src.models import Security

            with db_session() as session:
                # Get or create Security
                security = session.query(Security).filter(Security.ticker == ticker).first()
                if not security:
                    # Create a basic Security entry if it doesn't exist
                    security = Security(ticker=ticker, name=ticker)
                    session.add(security)
                    session.flush()

                stock_rec = StockRecommendation(
                    security_id=security.id,
                    portfolio_id=portfolio_id,
                    timestamp=datetime.now(),
                    recommendation=recommendation,
                    confidence=confidence,
                    technical_score=technical_score,
                    fundamental_score=fundamental_score,
                    combined_score=combined_score,
                    technical_signals=technical_signals,
                    fundamental_signals=fundamental_signals,
                    rationale=rationale,
                )

                session.add(stock_rec)
                session.flush()
                session.refresh(stock_rec)
                return stock_rec

        except Exception as e:
            logger.error(f"Failed to store recommendation: {e}")
            return None

    def get_latest_recommendation(
        self, ticker: str, portfolio_id: str
    ) -> Optional[StockRecommendation]:
        """
        Get latest recommendation for a ticker in a portfolio.

        Args:
            ticker: Stock ticker
            portfolio_id: Portfolio ID

        Returns:
            StockRecommendation or None
        """
        from src.models import Security

        with db_session() as session:
            rec = (
                session.query(StockRecommendation)
                .join(Security, StockRecommendation.security_id == Security.id)
                .filter(
                    Security.ticker == ticker,
                    StockRecommendation.portfolio_id == portfolio_id,
                )
                .order_by(StockRecommendation.timestamp.desc())
                .first()
            )

            return rec
