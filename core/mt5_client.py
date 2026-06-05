"""MetaTrader 5 client wrapper.

This module intentionally does not store credentials and does not perform
password-based login. It only uses the MT5 terminal session that is already
logged in by the user.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover - handled at runtime on machines without MT5
    mt5 = None


class MT5Client:
    """Small safety-oriented wrapper around the MetaTrader5 package."""

    def __init__(self) -> None:
        if mt5 is None:
            self.mt5 = None
            self.TIMEFRAME_MAP: Dict[str, int] = {}
        else:
            self.mt5 = mt5
            self.TIMEFRAME_MAP = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4,
                "D1": mt5.TIMEFRAME_D1,
            }
        self.initialized = False

    def initialize(self) -> bool:
        """Initialize MT5 using the already logged-in terminal session."""
        if self.mt5 is None:
            raise ImportError("MetaTrader5 package is not installed. Run: pip install -r requirements.txt")

        if not self.mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {self.mt5.last_error()}")

        self.initialized = True
        return True

    def shutdown(self) -> None:
        if self.mt5 is not None and self.initialized:
            self.mt5.shutdown()
        self.initialized = False

    def get_terminal_info(self) -> Any:
        return self.mt5.terminal_info()

    def get_account_info(self) -> Any:
        return self.mt5.account_info()

    @staticmethod
    def namedtuple_to_dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if hasattr(value, "_asdict"):
            return dict(value._asdict())
        return {
            key: getattr(value, key)
            for key in dir(value)
            if not key.startswith("_") and not callable(getattr(value, key))
        }

    def get_account_type(self) -> str:
        """Return DEMO, REAL, CONTEST, or UNKNOWN.

        If trade_mode cannot be read, the account is treated as UNKNOWN.
        UNKNOWN is not safe for order execution.
        """
        info = self.get_account_info()
        if info is None:
            return "UNKNOWN"

        trade_mode = getattr(info, "trade_mode", None)
        if trade_mode is None:
            return "UNKNOWN"

        constant_map: Dict[int, str] = {}
        for constant_name, label in (
            ("ACCOUNT_TRADE_MODE_DEMO", "DEMO"),
            ("ACCOUNT_TRADE_MODE_CONTEST", "CONTEST"),
            ("ACCOUNT_TRADE_MODE_REAL", "REAL"),
        ):
            constant_value = getattr(self.mt5, constant_name, None)
            if constant_value is not None:
                constant_map[int(constant_value)] = label

        if int(trade_mode) in constant_map:
            return constant_map[int(trade_mode)]

        # MQL5 enum values are stable, but any unrecognized value stays unsafe.
        fallback_map = {0: "DEMO", 1: "CONTEST", 2: "REAL"}
        return fallback_map.get(int(trade_mode), "UNKNOWN")

    def is_demo_account(self) -> bool:
        return self.get_account_type() == "DEMO"

    def get_timeframe_value(self, timeframe: str) -> int:
        key = str(timeframe).upper()
        if key not in self.TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        return self.TIMEFRAME_MAP[key]

    def ensure_symbol(self, symbol: str) -> Any:
        """Ensure a symbol exists and is visible in Market Watch."""
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Symbol not found in MT5: {symbol}")

        if not getattr(info, "visible", False):
            if not self.mt5.symbol_select(symbol, True):
                raise RuntimeError(f"Failed to activate symbol in Market Watch: {symbol}")
            info = self.mt5.symbol_info(symbol)

        return info

    def get_symbol_info(self, symbol: str) -> Any:
        return self.ensure_symbol(symbol)

    def get_candles(self, symbol: str, timeframe: str, start_pos: int = 0, count: int = 300) -> pd.DataFrame:
        """Fetch candles using copy_rates_from_pos and return a pandas DataFrame."""
        self.ensure_symbol(symbol)
        timeframe_value = self.get_timeframe_value(timeframe)
        rates = self.mt5.copy_rates_from_pos(symbol, timeframe_value, start_pos, count)

        if rates is None or len(rates) == 0:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"])

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def get_latest_tick(self, symbol: str) -> Any:
        self.ensure_symbol(symbol)
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"Latest tick is not available for symbol: {symbol}")
        return tick

    def get_open_positions(self, symbol: str, magic_number: Optional[int] = None) -> List[Any]:
        positions = self.mt5.positions_get(symbol=symbol)
        if positions is None:
            return []

        result = list(positions)
        if magic_number is not None:
            result = [position for position in result if int(getattr(position, "magic", -1)) == int(magic_number)]
        return result

    def get_history_deals(
        self,
        date_from: datetime,
        date_to: datetime,
        symbol: Optional[str] = None,
        magic_number: Optional[int] = None,
    ) -> List[Any]:
        deals = self.mt5.history_deals_get(date_from, date_to)
        if deals is None:
            return []

        result = list(deals)
        if symbol is not None:
            result = [deal for deal in result if str(getattr(deal, "symbol", "")) == symbol]
        if magic_number is not None:
            result = [deal for deal in result if int(getattr(deal, "magic", -1)) == int(magic_number)]
        return result
