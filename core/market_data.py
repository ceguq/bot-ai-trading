"""Market data collection helpers."""

from __future__ import annotations

from typing import Any, Dict


def get_multi_timeframe_data(mt5_client: Any, symbol: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Return candles for entry, confirm_1, and confirm_2 timeframes."""
    timeframes = config.get("timeframes", {}) or {}
    entry_tf = timeframes.get("entry", "M15")
    confirm_1_tf = timeframes.get("confirm_1", "H1")
    confirm_2_tf = timeframes.get("confirm_2", "H4")

    return {
        "symbol": symbol,
        "timeframes": {
            "entry": entry_tf,
            "confirm_1": confirm_1_tf,
            "confirm_2": confirm_2_tf,
        },
        "entry": mt5_client.get_candles(symbol, entry_tf, count=300),
        "confirm_1": mt5_client.get_candles(symbol, confirm_1_tf, count=300),
        "confirm_2": mt5_client.get_candles(symbol, confirm_2_tf, count=300),
    }
