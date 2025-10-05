"""Unit tests for RecommendationEngine."""

from unittest.mock import MagicMock, patch

import pytest

from src.models.recommendation import ConfidenceLevel, RecommendationType
from src.services.recommendation_engine import RecommendationEngine


@pytest.fixture
def recommendation_engine():
    """Provide RecommendationEngine instance."""
    return RecommendationEngine()


@pytest.fixture
def mock_indicators():
    """Provide mock technical indicators."""
    return {
        "sma_20": 150.0,
        "sma_50": 145.0,
        "close": 155.0,
        "rsi": 55.0,
        "macd": 2.5,
        "bb_upper": 160.0,
        "bb_lower": 140.0,
        "obv": 1000000,
    }


@pytest.mark.unit
class TestRecommendationEngine:
    """Test suite for RecommendationEngine."""

    def test_calculate_technical_score_bullish(self, recommendation_engine, mock_indicators):
        """Technical score correctly identifies bullish signals."""
        score, signals = recommendation_engine.calculate_technical_score(mock_indicators)

        # Should have positive score (price above SMA20, SMA20 > SMA50, neutral RSI)
        assert score > 50
        assert isinstance(signals, list)
        assert len(signals) > 0
        assert any("bullish" in s.lower() or "uptrend" in s.lower() for s in signals)

    def test_calculate_technical_score_bearish(self, recommendation_engine):
        """Technical score correctly identifies bearish signals."""
        bearish_indicators = {
            "sma_20": 145.0,
            "sma_50": 150.0,
            "close": 140.0,
            "rsi": 75.0,  # Overbought
            "macd": -2.5,
            "bb_upper": 160.0,
            "bb_lower": 135.0,
            "obv": -1000000,
        }

        score, signals = recommendation_engine.calculate_technical_score(bearish_indicators)

        # Should have low score (price below SMA20, death cross, overbought RSI)
        assert score < 50
        assert any("bearish" in s.lower() or "overbought" in s.lower() for s in signals)

    def test_calculate_technical_score_edge_case_all_none(self, recommendation_engine):
        """Technical score handles case when all indicators are None."""
        # Empty indicators dict
        score, signals = recommendation_engine.calculate_technical_score({})

        # Should return some default score
        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert isinstance(signals, list)

    def test_calculate_technical_score_partial_indicators(self, recommendation_engine):
        """Technical score handles partial indicator data."""
        partial_indicators = {
            "sma_20": 150.0,
            "close": 155.0,
            # Missing sma_50, rsi, macd, etc.
        }

        score, signals = recommendation_engine.calculate_technical_score(partial_indicators)

        # Should still calculate a score
        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert isinstance(signals, list)

    def test_calculate_technical_score_rsi_oversold(self, recommendation_engine):
        """Technical score identifies oversold RSI correctly."""
        oversold_indicators = {
            "sma_20": 150.0,
            "sma_50": 148.0,
            "close": 152.0,
            "rsi": 25.0,  # Oversold
            "macd": 1.0,
            "bb_upper": 160.0,
            "bb_lower": 140.0,
            "obv": 500000,
        }

        score, signals = recommendation_engine.calculate_technical_score(oversold_indicators)

        # Should have signals about oversold condition
        assert any("oversold" in s.lower() for s in signals)

    def test_calculate_technical_score_rsi_overbought(self, recommendation_engine):
        """Technical score identifies overbought RSI correctly."""
        overbought_indicators = {
            "sma_20": 150.0,
            "sma_50": 148.0,
            "close": 152.0,
            "rsi": 75.0,  # Overbought
            "macd": 1.0,
            "bb_upper": 160.0,
            "bb_lower": 140.0,
            "obv": 500000,
        }

        score, signals = recommendation_engine.calculate_technical_score(overbought_indicators)

        # Should have signals about overbought condition
        assert any("overbought" in s.lower() for s in signals)

    @patch("src.services.recommendation_engine.FundamentalAnalyzer")
    def test_calculate_fundamental_score_no_data(self, mock_analyzer, recommendation_engine):
        """Fundamental score handles missing fundamental data."""
        # Mock analyzer to return None
        recommendation_engine.fundamental_analyzer.get_latest_fundamentals = MagicMock(
            return_value=None
        )

        score, signals = recommendation_engine.calculate_fundamental_score("AAPL")

        # Should return neutral score with appropriate message
        assert score == 50
        assert any("no fundamental data" in s.lower() for s in signals)

    @patch("src.services.recommendation_engine.FundamentalAnalyzer")
    def test_calculate_fundamental_score_with_data(self, mock_analyzer, recommendation_engine):
        """Fundamental score calculates correctly with valid data."""
        # Mock fundamental data
        mock_fundamentals = MagicMock()
        mock_fundamentals.dividend_yield = 0.04  # 4% dividend

        recommendation_engine.fundamental_analyzer.get_latest_fundamentals = MagicMock(
            return_value=mock_fundamentals
        )
        recommendation_engine.fundamental_analyzer.analyze_valuation = MagicMock(
            return_value={"score": 70, "signals": ["Undervalued"]}
        )
        recommendation_engine.fundamental_analyzer.analyze_growth = MagicMock(
            return_value={"score": 60, "signals": ["Good growth"]}
        )
        recommendation_engine.fundamental_analyzer.analyze_profitability = MagicMock(
            return_value={"score": 80, "signals": ["Highly profitable"]}
        )
        recommendation_engine.fundamental_analyzer.analyze_financial_health = MagicMock(
            return_value={"score": 75, "signals": ["Strong balance sheet"]}
        )

        score, signals = recommendation_engine.calculate_fundamental_score("AAPL")

        # Should calculate weighted score
        assert isinstance(score, int)
        assert score > 50  # Should be above neutral with good fundamentals
        assert len(signals) > 0

    def test_determine_recommendation_buy_threshold(self, recommendation_engine):
        """Recommendation is BUY when combined score exceeds threshold."""
        technical_score = 75
        fundamental_score = 75

        recommendation, confidence = recommendation_engine.determine_recommendation(
            technical_score, fundamental_score
        )

        assert recommendation == RecommendationType.BUY
        assert confidence == ConfidenceLevel.HIGH  # Scores aligned

    def test_determine_recommendation_sell_threshold(self, recommendation_engine):
        """Recommendation is SELL when combined score below threshold."""
        technical_score = 25
        fundamental_score = 25

        recommendation, confidence = recommendation_engine.determine_recommendation(
            technical_score, fundamental_score
        )

        assert recommendation == RecommendationType.SELL
        assert confidence == ConfidenceLevel.HIGH  # Scores aligned

    def test_determine_recommendation_hold_neutral(self, recommendation_engine):
        """Recommendation is HOLD for neutral scores."""
        technical_score = 50
        fundamental_score = 50

        recommendation, confidence = recommendation_engine.determine_recommendation(
            technical_score, fundamental_score
        )

        assert recommendation == RecommendationType.HOLD
        assert confidence == ConfidenceLevel.HIGH  # Perfect agreement

    def test_determine_recommendation_boundary_buy(self, recommendation_engine):
        """Test boundary at BUY threshold (70)."""
        # Just above threshold
        recommendation, confidence = recommendation_engine.determine_recommendation(71, 71)
        assert recommendation == RecommendationType.BUY

        # Just below threshold
        recommendation, confidence = recommendation_engine.determine_recommendation(69, 69)
        assert recommendation == RecommendationType.HOLD

    def test_determine_recommendation_boundary_sell(self, recommendation_engine):
        """Test boundary at SELL threshold (30)."""
        # Just below threshold
        recommendation, confidence = recommendation_engine.determine_recommendation(29, 29)
        assert recommendation == RecommendationType.SELL

        # Just above threshold
        recommendation, confidence = recommendation_engine.determine_recommendation(31, 31)
        assert recommendation == RecommendationType.HOLD

    def test_determine_recommendation_conflicting_signals_low_confidence(
        self, recommendation_engine
    ):
        """Conflicting signals result in LOW confidence."""
        # High technical score, low fundamental score
        technical_score = 80
        fundamental_score = 20

        recommendation, confidence = recommendation_engine.determine_recommendation(
            technical_score, fundamental_score
        )

        # Should result in low confidence due to conflicting signals
        assert confidence == ConfidenceLevel.LOW

    def test_determine_recommendation_medium_confidence(self, recommendation_engine):
        """Moderately aligned signals result in MEDIUM confidence."""
        technical_score = 70
        fundamental_score = 55

        recommendation, confidence = recommendation_engine.determine_recommendation(
            technical_score, fundamental_score
        )

        # 15 point difference = medium confidence
        assert confidence == ConfidenceLevel.MEDIUM

    def test_generate_rationale_includes_all_elements(self, recommendation_engine):
        """Rationale includes recommendation, scores, and signals."""
        rationale = recommendation_engine.generate_rationale(
            RecommendationType.BUY,
            75,
            70,
            ["Technical signal 1", "Technical signal 2"],
            ["Fundamental signal 1", "Fundamental signal 2"],
        )

        assert "BUY" in rationale
        assert "75" in rationale  # Technical score
        assert "70" in rationale  # Fundamental score
        assert "Technical signal 1" in rationale
        assert "Fundamental signal 1" in rationale

    def test_generate_rationale_limits_signals(self, recommendation_engine):
        """Rationale limits to 5 signals per category."""
        many_signals = [f"Signal {i}" for i in range(10)]

        rationale = recommendation_engine.generate_rationale(
            RecommendationType.HOLD, 50, 50, many_signals, many_signals
        )

        # Should only include first 5 signals
        assert "Signal 0" in rationale
        assert "Signal 4" in rationale
        # Should not include later signals
        assert "Signal 9" not in rationale

    @pytest.mark.asyncio
    @patch("src.services.recommendation_engine.db_session")
    @patch("src.services.recommendation_engine.IndicatorCalculator")
    @patch("src.services.recommendation_engine.FundamentalAnalyzer")
    async def test_generate_recommendation_full_workflow(
        self, mock_fund_analyzer, mock_indicator_calc, mock_db, recommendation_engine
    ):
        """Full recommendation generation workflow."""
        # Mock indicator calculator
        mock_indicators = {
            "sma_20": 150.0,
            "sma_50": 145.0,
            "close": 155.0,
            "rsi": 55.0,
        }
        recommendation_engine.indicator_calc.calculate_all_indicators = MagicMock(
            return_value=mock_indicators
        )

        # Mock fundamental analyzer
        recommendation_engine.fundamental_analyzer.get_latest_fundamentals = MagicMock(
            return_value=MagicMock(dividend_yield=0.03)
        )
        recommendation_engine.fundamental_analyzer.analyze_valuation = MagicMock(
            return_value={"score": 70, "signals": ["Good value"]}
        )
        recommendation_engine.fundamental_analyzer.analyze_growth = MagicMock(
            return_value={"score": 60, "signals": ["Growing"]}
        )
        recommendation_engine.fundamental_analyzer.analyze_profitability = MagicMock(
            return_value={"score": 75, "signals": ["Profitable"]}
        )
        recommendation_engine.fundamental_analyzer.analyze_financial_health = MagicMock(
            return_value={"score": 70, "signals": ["Healthy"]}
        )

        # Mock database session
        mock_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_session

        result = await recommendation_engine.generate_recommendation("AAPL", "portfolio-123")

        # Should return a recommendation
        assert result is not None
        assert hasattr(result, "recommendation_type")
        assert hasattr(result, "confidence")

    @pytest.mark.asyncio
    @patch("src.services.recommendation_engine.IndicatorCalculator")
    async def test_generate_recommendation_no_technical_data(
        self, mock_indicator_calc, recommendation_engine
    ):
        """Recommendation handles missing technical data gracefully."""
        # Mock indicator calculator to return None
        recommendation_engine.indicator_calc.calculate_all_indicators = MagicMock(return_value=None)

        # Mock fundamental analyzer
        recommendation_engine.fundamental_analyzer.get_latest_fundamentals = MagicMock(
            return_value=None
        )

        # Mock database session
        with patch("src.services.recommendation_engine.db_session") as mock_db:
            mock_session = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_session

            result = await recommendation_engine.generate_recommendation("INVALID", "portfolio-123")

            # Should still generate a recommendation (neutral)
            assert result is not None
