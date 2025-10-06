"""Technical indicator calculator using TA-Lib and pandas-ta."""

from typing import Any, Optional

import pandas as pd

from src.lib.db import db_session
from src.models.market_data import MarketData


class IndicatorCalculator:
    """Calculates technical indicators for stock analysis."""

    def __init__(self) -> None:
        """Initialize indicator calculator."""
        self.talib_available = False
        self.pandas_ta_available = False

        try:
            import talib

            self.talib_available = True
            self.talib = talib
        except ImportError:
            pass

        try:
            import pandas_ta as ta

            self.pandas_ta_available = True
            self.pandas_ta = ta
        except ImportError:
            pass

    def get_historical_data(self, ticker: str, period_days: int = 200) -> Optional[pd.DataFrame]:
        """
        Get historical market data for a ticker.

        Args:
            ticker: Stock ticker
            period_days: Number of days of history (default: 200)

        Returns:
            DataFrame with OHLCV data or None
        """
        with db_session() as session:
            data = (
                session.query(MarketData)
                .filter(MarketData.ticker == ticker)
                .order_by(MarketData.timestamp.desc())
                .limit(period_days)
                .all()
            )

            if not data:
                return None

            # Convert to DataFrame
            df = pd.DataFrame(
                [
                    {
                        "timestamp": d.timestamp,
                        "open": d.open,
                        "high": d.high,
                        "low": d.low,
                        "close": d.close,
                        "volume": d.volume,
                    }
                    for d in reversed(data)
                ]
            )

            df.set_index("timestamp", inplace=True)
            return df

    def calculate_trend_indicators(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate trend indicators: SMA, EMA, MACD.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dict with indicator values
        """
        result: dict[str, Any] = {}

        if len(df) < 50:
            return result

        close = df["close"].values

        # Simple Moving Averages
        if self.talib_available:
            result["sma_20"] = self.talib.SMA(close, timeperiod=20)[-1]
            result["sma_50"] = self.talib.SMA(close, timeperiod=50)[-1]
            result["ema_20"] = self.talib.EMA(close, timeperiod=20)[-1]

            # MACD
            macd, signal, hist = self.talib.MACD(
                close, fastperiod=12, slowperiod=26, signalperiod=9
            )
            result["macd"] = macd[-1]
            result["macd_signal"] = signal[-1]
            result["macd_hist"] = hist[-1]

        elif self.pandas_ta_available:
            result["sma_20"] = df.ta.sma(length=20).iloc[-1]
            result["sma_50"] = df.ta.sma(length=50).iloc[-1]
            result["ema_20"] = df.ta.ema(length=20).iloc[-1]

            macd_df = df.ta.macd()
            result["macd"] = macd_df["MACD_12_26_9"].iloc[-1]
            result["macd_signal"] = macd_df["MACDs_12_26_9"].iloc[-1]
            result["macd_hist"] = macd_df["MACDh_12_26_9"].iloc[-1]

        else:
            # Fallback: manual calculation
            result["sma_20"] = df["close"].rolling(window=20).mean().iloc[-1]
            result["sma_50"] = df["close"].rolling(window=50).mean().iloc[-1]
            result["ema_20"] = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]

        return result

    def calculate_momentum_indicators(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate momentum indicators: RSI, Stochastic.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dict with indicator values
        """
        result: dict[str, Any] = {}

        if len(df) < 14:
            return result

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        if self.talib_available:
            # RSI (14-day)
            result["rsi_14"] = self.talib.RSI(close, timeperiod=14)[-1]

            # Stochastic Oscillator
            slowk, slowd = self.talib.STOCH(high, low, close)
            result["stoch_k"] = slowk[-1]
            result["stoch_d"] = slowd[-1]

        elif self.pandas_ta_available:
            result["rsi_14"] = df.ta.rsi(length=14).iloc[-1]

            stoch_df = df.ta.stoch()
            result["stoch_k"] = stoch_df["STOCHk_14_3_3"].iloc[-1]
            result["stoch_d"] = stoch_df["STOCHd_14_3_3"].iloc[-1]

        else:
            # Manual RSI calculation
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            result["rsi_14"] = (100 - (100 / (1 + rs))).iloc[-1]

        return result

    def calculate_volatility_indicators(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate volatility indicators: Bollinger Bands, ATR.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dict with indicator values
        """
        result: dict[str, Any] = {}

        if len(df) < 20:
            return result

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        if self.talib_available:
            # Bollinger Bands
            upper, middle, lower = self.talib.BBANDS(close, timeperiod=20)
            result["bb_upper"] = upper[-1]
            result["bb_middle"] = middle[-1]
            result["bb_lower"] = lower[-1]

            # Average True Range
            result["atr_14"] = self.talib.ATR(high, low, close, timeperiod=14)[-1]

        elif self.pandas_ta_available:
            bb_df = df.ta.bbands(length=20)
            result["bb_upper"] = bb_df["BBU_20_2.0"].iloc[-1]
            result["bb_middle"] = bb_df["BBM_20_2.0"].iloc[-1]
            result["bb_lower"] = bb_df["BBL_20_2.0"].iloc[-1]

            result["atr_14"] = df.ta.atr(length=14).iloc[-1]

        else:
            # Manual Bollinger Bands
            sma = df["close"].rolling(window=20).mean()
            std = df["close"].rolling(window=20).std()
            result["bb_upper"] = (sma + (std * 2)).iloc[-1]
            result["bb_middle"] = sma.iloc[-1]
            result["bb_lower"] = (sma - (std * 2)).iloc[-1]

        return result

    def calculate_volume_indicators(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate volume indicators: OBV.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dict with indicator values
        """
        result: dict[str, Any] = {}

        if len(df) < 10:
            return result

        close = df["close"].values
        volume = df["volume"].values

        if self.talib_available:
            result["obv"] = self.talib.OBV(close, volume)[-1]

        elif self.pandas_ta_available:
            result["obv"] = df.ta.obv().iloc[-1]

        else:
            # Manual OBV calculation
            obv = [0]
            for i in range(1, len(df)):
                if close[i] > close[i - 1]:
                    obv.append(obv[-1] + volume[i])
                elif close[i] < close[i - 1]:
                    obv.append(obv[-1] - volume[i])
                else:
                    obv.append(obv[-1])
            result["obv"] = obv[-1]

        return result

    def calculate_all_indicators(self, ticker: str) -> Optional[dict[str, Any]]:
        """
        Calculate all technical indicators for a ticker.

        Args:
            ticker: Stock ticker

        Returns:
            Dict with all indicator values or None
        """
        df = self.get_historical_data(ticker)
        if df is None or len(df) < 50:
            return None

        indicators = {}

        # Trend indicators
        indicators.update(self.calculate_trend_indicators(df))

        # Momentum indicators
        indicators.update(self.calculate_momentum_indicators(df))

        # Volatility indicators
        indicators.update(self.calculate_volatility_indicators(df))

        # Volume indicators
        indicators.update(self.calculate_volume_indicators(df))

        return indicators
