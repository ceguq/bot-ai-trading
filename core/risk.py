"""Risk plan builder for demo order execution."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def _symbol_point_and_digits(symbol_info: Any) -> Tuple[float, int, Optional[str]]:
    if symbol_info is not None:
        point = getattr(symbol_info, "point", None)
        digits = getattr(symbol_info, "digits", None)
        if point:
            return float(point), int(digits if digits is not None else 2), None

    return 0.01, 2, "WARNING: symbol_info unavailable; fallback XAUUSD point 0.01 is used."


def _round_price(price: float, digits: int) -> float:
    return round(float(price), int(digits))


def build_risk_plan(
    action: str,
    price: Optional[float],
    config: Dict[str, Any],
    symbol_info: Any = None,
    structure_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build SL/TP plan using symbol point when available."""
    risk = config.get("risk", {}) or {}
    strategy = config.get("strategy", {}) or {}
    trade = config.get("trade", {}) or {}
    action = str(action or "SKIP").upper()
    lot = float(risk.get("lot", 0.01))
    sl_pips = int(risk.get("sl_pips", 300))
    tp_pips = int(risk.get("tp_pips", 600))
    risk_profile = "default"
    risk_notes = []
    zone_source = str((structure_result or {}).get("zone_source", ""))
    if zone_source.startswith("M15") and bool(strategy.get("use_m15_scalp_target", True)):
        tp_pips = int(strategy.get("m15_zone_tp_pips", tp_pips))
        if strategy.get("m15_zone_sl_pips") is not None:
            sl_pips = int(strategy.get("m15_zone_sl_pips", sl_pips))
        risk_profile = "m15_scalp"
        risk_notes.append(f"M15 zone scalp profile active from {zone_source}.")
    max_layer = int(risk.get("max_layer", 1))
    if not bool(trade.get("allow_layering", False)):
        max_layer = 1
    move_to_be_after_pips = int(risk.get("move_to_be_after_pips", 250))
    point, digits, warning = _symbol_point_and_digits(symbol_info)

    estimated_sl_price = None
    estimated_tp_price = None
    entry_price = float(price) if price is not None else None

    if action in {"BUY", "SELL"}:
        if entry_price is None:
            raise ValueError("Price is required to build risk plan for BUY/SELL.")
        sl_distance = sl_pips * point
        tp_distance = tp_pips * point

        if action == "BUY":
            estimated_sl_price = _round_price(entry_price - sl_distance, digits)
            estimated_tp_price = _round_price(entry_price + tp_distance, digits)
        else:
            estimated_sl_price = _round_price(entry_price + sl_distance, digits)
            estimated_tp_price = _round_price(entry_price - tp_distance, digits)

    return {
        "action": action,
        "lot": lot,
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "max_layer": max_layer,
        "move_to_be_after_pips": move_to_be_after_pips,
        "entry_price": entry_price,
        "estimated_sl_price": estimated_sl_price,
        "estimated_tp_price": estimated_tp_price,
        "point": point,
        "digits": digits,
        "warning": warning,
        "risk_profile": risk_profile,
        "risk_notes": risk_notes,
    }
