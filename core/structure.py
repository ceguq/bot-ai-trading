"""Simple market structure analysis for support, resistance, and zones."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


def _find_swings(df: pd.DataFrame, column: str, mode: str, window: int = 2) -> List[float]:
    if df is None or df.empty or len(df) < (window * 2 + 1):
        return []

    values = df[column].astype(float).reset_index(drop=True)
    swings: List[float] = []
    for index in range(window, len(values) - window):
        segment = values.iloc[index - window : index + window + 1]
        current = float(values.iloc[index])
        if mode == "high" and current == float(segment.max()):
            swings.append(current)
        if mode == "low" and current == float(segment.min()):
            swings.append(current)
    return swings


def _dedupe_recent(levels: List[float], tolerance: float, limit: int = 8) -> List[float]:
    result: List[float] = []
    for level in reversed(levels):
        if all(abs(level - existing) > tolerance for existing in result):
            result.append(round(float(level), 3))
        if len(result) >= limit:
            break
    return list(reversed(result))


def _nearest_support(levels: List[float], price: float) -> Optional[float]:
    valid = [level for level in levels if level <= price]
    return max(valid) if valid else (min(levels, key=lambda level: abs(level - price)) if levels else None)


def _nearest_resistance(levels: List[float], price: float) -> Optional[float]:
    valid = [level for level in levels if level >= price]
    return min(valid) if valid else (min(levels, key=lambda level: abs(level - price)) if levels else None)


def _is_bullish_context(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    recent = df.tail(min(len(df), 50))
    return float(recent["close"].iloc[-1]) >= float(recent["close"].mean())


def _is_bearish_context(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    recent = df.tail(min(len(df), 50))
    return float(recent["close"].iloc[-1]) <= float(recent["close"].mean())


def _detect_rejection(df: pd.DataFrame, strategy_config: Dict[str, Any], label: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "label": label,
        "direction": "NEUTRAL",
        "type": "NONE",
        "state": "closed",
        "time": "",
        "body": None,
        "upper_wick": None,
        "lower_wick": None,
        "close_position": None,
        "notes": [],
    }
    if df is None or df.empty:
        result["notes"].append(f"{label}: no candle data for rejection check.")
        return result

    use_closed = bool(strategy_config.get("use_closed_rejection_candle", True))
    if use_closed and len(df) >= 2:
        candle = df.iloc[-2]
        result["state"] = "closed"
    else:
        candle = df.iloc[-1]
        result["state"] = "current"

    open_price = float(candle["open"])
    close_price = float(candle["close"])
    high_price = float(candle["high"])
    low_price = float(candle["low"])
    candle_range = max(high_price - low_price, 0.00001)
    body = max(abs(close_price - open_price), 0.00001)
    upper_wick = max(high_price - max(open_price, close_price), 0.0)
    lower_wick = max(min(open_price, close_price) - low_price, 0.0)
    close_position = (close_price - low_price) / candle_range
    min_wick_body_ratio = float(strategy_config.get("rejection_min_wick_body_ratio", 1.5))
    bullish_close_position = float(strategy_config.get("bullish_rejection_close_position", 0.55))
    bearish_close_position = float(strategy_config.get("bearish_rejection_close_position", 0.45))

    result.update(
        {
            "time": str(candle["time"]) if "time" in df.columns else "",
            "body": round(body, 3),
            "upper_wick": round(upper_wick, 3),
            "lower_wick": round(lower_wick, 3),
            "close_position": round(close_position, 3),
        }
    )

    bullish_rejection = (
        lower_wick >= body * min_wick_body_ratio
        and lower_wick > upper_wick
        and close_position >= bullish_close_position
    )
    bearish_rejection = (
        upper_wick >= body * min_wick_body_ratio
        and upper_wick > lower_wick
        and close_position <= bearish_close_position
    )

    if bullish_rejection:
        result["direction"] = "BUY"
        result["type"] = "BULLISH_REJECTION"
        result["notes"].append(f"{label}: bullish rejection candle detected.")
    elif bearish_rejection:
        result["direction"] = "SELL"
        result["type"] = "BEARISH_REJECTION"
        result["notes"].append(f"{label}: bearish rejection candle detected.")

    return result


def _quality_grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "F"


def _score_zone_quality(
    zone: Dict[str, Any],
    tolerance: float,
    strategy_config: Dict[str, Any],
) -> Dict[str, Any]:
    zone_type = str(zone.get("zone_type", "NONE"))
    zone_direction = str(zone.get("zone_direction", "NEUTRAL"))
    source = str(zone.get("zone_source") or zone.get("label") or "")
    score = 0
    reasons: List[str] = []

    if zone_type == "NONE":
        return {"zone_quality_score": 0, "zone_quality_grade": "F", "zone_quality_reasons": ["No valid zone."]}

    if zone_type in {"RBS", "SBR"}:
        score += 30
        reasons.append(f"{zone_type} setup base quality +30")
    elif zone_type in {"SNR_SUPPORT", "SNR_RESISTANCE"}:
        score += 18
        reasons.append(f"{zone_type} setup base quality +18")

    source_upper = source.upper()
    if source_upper == "H4":
        score += 20
        reasons.append("H4 major zone +20")
    elif source_upper == "H1_REJECTION":
        score += 20
        reasons.append("H1 rejection zone source +20")
    elif source_upper.startswith("H1"):
        score += 15
        reasons.append("H1 refined zone +15")
    elif source_upper.startswith("M15"):
        score += 8
        reasons.append("M15 execution zone +8")

    zone_distance = zone.get("zone_distance")
    if zone_distance is not None:
        distance_ratio = float(zone_distance) / max(float(tolerance), 0.00001)
        if distance_ratio <= 0.25:
            score += 20
            reasons.append("Price is very close to zone +20")
        elif distance_ratio <= 0.5:
            score += 15
            reasons.append("Price is close to zone +15")
        elif distance_ratio <= 1.0:
            score += 8
            reasons.append("Price is inside tolerance +8")
        else:
            score -= 20
            reasons.append("Price is outside zone tolerance -20")

    if zone.get("zone_validation"):
        score += 20
        reasons.append("Body break plus FVG validation +20")
    elif zone_type in {"RBS", "SBR"}:
        score -= 20
        reasons.append(f"{zone_type} without body break plus FVG validation -20")

    rejection = zone.get("rejection", {}) or {}
    rejection_direction = str(rejection.get("direction", "NEUTRAL"))
    if rejection_direction in {"BUY", "SELL"} and rejection_direction == zone_direction:
        score += 20
        reasons.append(f"{source or 'Zone'} rejection supports zone direction +20")
    elif rejection_direction in {"BUY", "SELL"} and zone_direction in {"BUY", "SELL"}:
        score -= 15
        reasons.append(f"{source or 'Zone'} rejection conflicts with zone direction -15")

    htf_bias_sources = list(zone.get("htf_bias_sources", []) or [])
    htf_conflict_sources = list(zone.get("htf_conflict_sources", []) or [])
    if zone.get("zone_confluence"):
        score += 10
        reasons.append("Multi-timeframe zone confluence +10")
    if htf_bias_sources:
        points = min(16, 8 * len(htf_bias_sources))
        score += points
        reasons.append(f"HTF bias sources {', '.join(htf_bias_sources)} +{points}")
    if htf_conflict_sources:
        points = min(30, 15 * len(htf_conflict_sources))
        score -= points
        reasons.append(f"HTF conflict sources {', '.join(htf_conflict_sources)} -{points}")

    if zone_type in {"SNR_SUPPORT", "SNR_RESISTANCE"} and not zone.get("zone_confluence") and rejection_direction != zone_direction:
        score -= 10
        reasons.append("SNR zone has no rejection or HTF confluence -10")

    score = max(0, min(100, int(score)))
    return {
        "zone_quality_score": score,
        "zone_quality_grade": _quality_grade(score),
        "zone_quality_reasons": reasons,
    }


def _has_recent_break_above(df: pd.DataFrame, level: float, tolerance: float, lookback: int = 80) -> bool:
    recent = df.tail(min(len(df), lookback))
    if recent.empty:
        return False
    closes = recent["close"].astype(float)
    return bool((closes > level + tolerance).any())


def _has_recent_break_below(df: pd.DataFrame, level: float, tolerance: float, lookback: int = 80) -> bool:
    recent = df.tail(min(len(df), lookback))
    if recent.empty:
        return False
    closes = recent["close"].astype(float)
    return bool((closes < level - tolerance).any())


def _break_buffer(tolerance: float) -> float:
    return max(tolerance * 0.1, 0.05)


def _average_body(df: pd.DataFrame, lookback: int = 50) -> float:
    recent = df.tail(min(len(df), lookback))
    if recent.empty:
        return 0.0
    bodies = (recent["close"].astype(float) - recent["open"].astype(float)).abs()
    return float(bodies.mean())


def _find_body_break_above(
    df: pd.DataFrame,
    level: float,
    tolerance: float,
    strategy_config: Dict[str, Any],
) -> Optional[int]:
    lookback = int(strategy_config.get("break_lookback_candles", 80))
    min_body_ratio = float(strategy_config.get("min_break_body_ratio", 1.0))
    recent = df.tail(min(len(df), lookback))
    if recent.empty:
        return None

    min_body = _average_body(recent) * min_body_ratio
    buffer = _break_buffer(tolerance)
    for index, candle in recent.iterrows():
        open_price = float(candle["open"])
        close_price = float(candle["close"])
        body = abs(close_price - open_price)
        if close_price > open_price and close_price > level + buffer and body >= min_body:
            return int(index)
    return None


def _find_body_break_below(
    df: pd.DataFrame,
    level: float,
    tolerance: float,
    strategy_config: Dict[str, Any],
) -> Optional[int]:
    lookback = int(strategy_config.get("break_lookback_candles", 80))
    min_body_ratio = float(strategy_config.get("min_break_body_ratio", 1.0))
    recent = df.tail(min(len(df), lookback))
    if recent.empty:
        return None

    min_body = _average_body(recent) * min_body_ratio
    buffer = _break_buffer(tolerance)
    for index, candle in recent.iterrows():
        open_price = float(candle["open"])
        close_price = float(candle["close"])
        body = abs(close_price - open_price)
        if close_price < open_price and close_price < level - buffer and body >= min_body:
            return int(index)
    return None


def _find_fvg_after_break(
    df: pd.DataFrame,
    break_index: Optional[int],
    direction: str,
    strategy_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if break_index is None or df is None or df.empty:
        return None

    positions = list(df.index)
    if break_index not in positions:
        return None

    break_pos = positions.index(break_index)
    lookback = int(strategy_config.get("fvg_lookback_candles", 20))
    end_pos = min(len(df) - 1, break_pos + lookback)

    for pos in range(break_pos + 2, end_pos + 1):
        first = df.iloc[pos - 2]
        third = df.iloc[pos]
        if direction == "bullish":
            gap_low = float(first["high"])
            gap_high = float(third["low"])
            if gap_low < gap_high:
                return {
                    "type": "BULLISH_FVG",
                    "time": str(third["time"]) if "time" in df.columns else "",
                    "low": round(gap_low, 3),
                    "high": round(gap_high, 3),
                }
        if direction == "bearish":
            gap_low = float(third["high"])
            gap_high = float(first["low"])
            if gap_low < gap_high:
                return {
                    "type": "BEARISH_FVG",
                    "time": str(third["time"]) if "time" in df.columns else "",
                    "low": round(gap_low, 3),
                    "high": round(gap_high, 3),
                }
    return None


def _valid_rbs_setup(
    df: pd.DataFrame,
    level: float,
    tolerance: float,
    strategy_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    require_body_break = bool(strategy_config.get("require_body_break_for_sbr_rbs", True))
    require_fvg = bool(strategy_config.get("require_fvg_for_sbr_rbs", True))
    break_index = _find_body_break_above(df, level, tolerance, strategy_config)

    if require_body_break and break_index is None:
        return None
    if break_index is None and not _has_recent_break_above(df, level, _break_buffer(tolerance)):
        return None

    fvg = _find_fvg_after_break(df, break_index, "bullish", strategy_config)
    if require_fvg and fvg is None:
        return None

    return {"break_index": break_index, "fvg": fvg, "validation": "body_break_plus_bullish_fvg"}


def _valid_sbr_setup(
    df: pd.DataFrame,
    level: float,
    tolerance: float,
    strategy_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    require_body_break = bool(strategy_config.get("require_body_break_for_sbr_rbs", True))
    require_fvg = bool(strategy_config.get("require_fvg_for_sbr_rbs", True))
    break_index = _find_body_break_below(df, level, tolerance, strategy_config)

    if require_body_break and break_index is None:
        return None
    if break_index is None and not _has_recent_break_below(df, level, _break_buffer(tolerance)):
        return None

    fvg = _find_fvg_after_break(df, break_index, "bearish", strategy_config)
    if require_fvg and fvg is None:
        return None

    return {"break_index": break_index, "fvg": fvg, "validation": "body_break_plus_bearish_fvg"}


def _select_rbs_level(
    df: pd.DataFrame,
    resistance_levels: List[float],
    price: float,
    tolerance: float,
    strategy_config: Dict[str, Any],
) -> tuple[Optional[float], Dict[str, Any]]:
    candidates = []
    for level in resistance_levels:
        if abs(price - level) > tolerance:
            continue
        setup = _valid_rbs_setup(df, level, tolerance, strategy_config)
        if setup is not None:
            candidates.append((level, setup))
    if not candidates:
        return None, {}
    return min(candidates, key=lambda item: abs(price - item[0]))


def _select_sbr_level(
    df: pd.DataFrame,
    support_levels: List[float],
    price: float,
    tolerance: float,
    strategy_config: Dict[str, Any],
) -> tuple[Optional[float], Dict[str, Any]]:
    candidates = []
    for level in support_levels:
        if abs(price - level) > tolerance:
            continue
        setup = _valid_sbr_setup(df, level, tolerance, strategy_config)
        if setup is not None:
            candidates.append((level, setup))
    if not candidates:
        return None, {}
    return min(candidates, key=lambda item: abs(price - item[0]))


def _empty_zone(label: str) -> Dict[str, Any]:
    return {
        "label": label,
        "support_levels": [],
        "resistance_levels": [],
        "nearest_support": None,
        "nearest_resistance": None,
        "zone_type": "NONE",
        "zone_direction": "NEUTRAL",
        "zone_level": None,
        "zone_distance": None,
        "rejection": {"direction": "NEUTRAL", "type": "NONE", "notes": []},
        "zone_quality_score": 0,
        "zone_quality_grade": "F",
        "zone_quality_reasons": ["No valid zone."],
        "notes": [],
    }


def _analyze_timeframe_zone(
    zone_df: pd.DataFrame,
    context_df: pd.DataFrame,
    last_price: float,
    tolerance: float,
    use_sbr_rbs: bool,
    strategy_config: Dict[str, Any],
    label: str,
) -> Dict[str, Any]:
    if zone_df is None or zone_df.empty:
        result = _empty_zone(label)
        result["notes"].append(f"{label} data is empty.")
        return result

    notes: List[str] = []
    swing_lows = _find_swings(zone_df, "low", "low")
    swing_highs = _find_swings(zone_df, "high", "high")

    if not swing_lows:
        swing_lows = [float(zone_df["low"].tail(50).min())]
        notes.append(f"{label}: no clear swing low; using recent low fallback.")

    if not swing_highs:
        swing_highs = [float(zone_df["high"].tail(50).max())]
        notes.append(f"{label}: no clear swing high; using recent high fallback.")

    support_levels = _dedupe_recent(swing_lows, tolerance=tolerance / 2)
    resistance_levels = _dedupe_recent(swing_highs, tolerance=tolerance / 2)
    nearest_support = _nearest_support(support_levels, last_price)
    nearest_resistance = _nearest_resistance(resistance_levels, last_price)
    near_support = nearest_support is not None and abs(last_price - nearest_support) <= tolerance
    near_resistance = nearest_resistance is not None and abs(last_price - nearest_resistance) <= tolerance
    bullish_context = _is_bullish_context(context_df)
    bearish_context = _is_bearish_context(context_df)
    rejection = _detect_rejection(zone_df, strategy_config, label)
    notes.extend(rejection.get("notes", []))

    zone_type = "NONE"
    zone_level = None
    zone_direction = "NEUTRAL"
    zone_validation = ""
    fvg = None

    rbs_setup = (None, {})
    sbr_setup = (None, {})
    if use_sbr_rbs:
        rbs_setup = _select_rbs_level(zone_df, resistance_levels, last_price, tolerance, strategy_config)
        sbr_setup = _select_sbr_level(zone_df, support_levels, last_price, tolerance, strategy_config)
    rbs_level, rbs_details = rbs_setup
    sbr_level, sbr_details = sbr_setup

    if rbs_level is not None and bullish_context:
        zone_type = "RBS"
        zone_level = rbs_level
        zone_direction = "BUY"
        zone_validation = str(rbs_details.get("validation", "breakout_retest"))
        fvg = rbs_details.get("fvg")
        notes.append(f"{label}: valid RBS detected from body close above resistance plus bullish FVG.")
    elif sbr_level is not None and bearish_context:
        zone_type = "SBR"
        zone_level = sbr_level
        zone_direction = "SELL"
        zone_validation = str(sbr_details.get("validation", "breakout_retest"))
        fvg = sbr_details.get("fvg")
        notes.append(f"{label}: valid SBR detected from body close below support plus bearish FVG.")
    elif near_support:
        zone_type = "SNR_SUPPORT"
        zone_level = nearest_support
        zone_direction = "BUY"
        notes.append(f"{label}: price near support zone.")
    elif near_resistance:
        zone_type = "SNR_RESISTANCE"
        zone_level = nearest_resistance
        zone_direction = "SELL"
        notes.append(f"{label}: price near resistance zone.")
    else:
        notes.append(f"{label}: price is not near support/resistance zone.")

    return {
        "label": label,
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "zone_type": zone_type,
        "zone_direction": zone_direction,
        "zone_level": zone_level,
        "zone_distance": round(abs(last_price - float(zone_level)), 3) if zone_level is not None else None,
        "zone_validation": zone_validation,
        "fvg": fvg,
        "rejection": rejection,
        "notes": notes,
    }


def _choose_primary_zone(
    h4_zone: Dict[str, Any],
    h1_zone: Dict[str, Any],
    m15_zone: Dict[str, Any],
    strategy_config: Dict[str, Any],
) -> Dict[str, Any]:
    h4_valid = h4_zone.get("zone_type") != "NONE"
    h1_valid = h1_zone.get("zone_type") != "NONE"
    m15_valid = m15_zone.get("zone_type") != "NONE"
    use_m15_execution_zone = bool(strategy_config.get("use_m15_zone_as_execution_reference", True))
    prefer_h1_rejection_zone = bool(strategy_config.get("prefer_h1_rejection_zone", True))

    h1_rejection = h1_zone.get("rejection", {}) or {}
    h1_rejection_direction = h1_rejection.get("direction")
    m15_opposes_h1_rejection = (
        m15_valid
        and m15_zone.get("zone_direction") in {"BUY", "SELL"}
        and h1_rejection_direction in {"BUY", "SELL"}
        and m15_zone.get("zone_direction") != h1_rejection_direction
    )
    require_m15_not_opposite = bool(strategy_config.get("h1_rejection_requires_m15_not_opposite", True))
    if (
        prefer_h1_rejection_zone
        and h1_valid
        and h1_rejection_direction in {"BUY", "SELL"}
        and h1_rejection_direction == h1_zone.get("zone_direction")
        and not (require_m15_not_opposite and m15_opposes_h1_rejection)
    ):
        selected = dict(h1_zone)
        selected["zone_source"] = "H1_REJECTION"
        selected["zone_confluence"] = False
        selected["htf_bias_sources"] = []
        selected["htf_conflict_sources"] = []

        for source, zone in (("H4", h4_zone), ("M15", m15_zone)):
            if zone.get("zone_type") == "NONE":
                continue
            if (
                zone.get("zone_direction") in {"BUY", "SELL"}
                and zone.get("zone_direction") == h1_zone.get("zone_direction")
            ):
                selected["htf_bias_sources"].append(source)
            elif zone.get("zone_direction") in {"BUY", "SELL"}:
                selected["htf_conflict_sources"].append(source)
        if selected["htf_bias_sources"]:
            selected["zone_confluence"] = True
        return selected

    if use_m15_execution_zone and m15_valid:
        selected = dict(m15_zone)
        selected["zone_source"] = "M15"
        selected["htf_bias_sources"] = []
        selected["htf_conflict_sources"] = []
        selected["zone_confluence"] = False

        for source, zone in (("H4", h4_zone), ("H1", h1_zone)):
            if zone.get("zone_type") == "NONE":
                continue
            if (
                zone.get("zone_direction") in {"BUY", "SELL"}
                and zone.get("zone_direction") == m15_zone.get("zone_direction")
            ):
                selected["htf_bias_sources"].append(source)
            elif zone.get("zone_direction") in {"BUY", "SELL"}:
                selected["htf_conflict_sources"].append(source)

        if selected["htf_bias_sources"]:
            selected["zone_source"] = "M15+" + "+".join(selected["htf_bias_sources"])
            selected["zone_confluence"] = True
        return selected

    if h4_valid and h1_valid:
        same_direction = (
            h4_zone.get("zone_direction") in {"BUY", "SELL"}
            and h4_zone.get("zone_direction") == h1_zone.get("zone_direction")
        )
        selected = dict(h1_zone if same_direction else h4_zone)
        selected["zone_source"] = "H1+H4" if same_direction else "H4"
        selected["zone_confluence"] = bool(same_direction)
        return selected

    if h1_valid:
        selected = dict(h1_zone)
        selected["zone_source"] = "H1"
        selected["zone_confluence"] = False
        return selected

    if h4_valid:
        selected = dict(h4_zone)
        selected["zone_source"] = "H4"
        selected["zone_confluence"] = False
        return selected

    selected = dict(m15_zone)
    selected["zone_source"] = "M15"
    selected["zone_confluence"] = False
    return selected


def analyze_structure(data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Analyze basic support/resistance and nearby SNR/SBR/RBS zone."""
    entry_df = data.get("entry")
    confirm_1_df = data.get("confirm_1")
    confirm_df = data.get("confirm_2")
    config = config or {}
    strategy_config = config.get("strategy", {}) or {}
    notes: List[str] = []

    if entry_df is None or entry_df.empty:
        return {
            "support_levels": [],
            "resistance_levels": [],
            "nearest_support": None,
            "nearest_resistance": None,
            "zone_level": None,
            "zone_type": "NONE",
            "zone_direction": "NEUTRAL",
            "zone_distance": None,
            "zone_quality_score": 0,
            "zone_quality_grade": "F",
            "zone_quality_reasons": ["No valid zone."],
            "h1_rejection": {"direction": "NEUTRAL", "type": "NONE", "notes": []},
            "notes": ["Entry candle data is empty."],
        }

    last_price = float(entry_df["close"].iloc[-1])
    tolerance_percent = float(strategy_config.get("zone_tolerance_percent", 0.2))
    tolerance = max(last_price * (tolerance_percent / 100), 0.5)
    use_sbr_rbs = bool(strategy_config.get("use_sbr_rbs", True))

    h4_zone = _analyze_timeframe_zone(confirm_df, confirm_df, last_price, tolerance, use_sbr_rbs, strategy_config, "H4")
    h1_zone = _analyze_timeframe_zone(confirm_1_df, confirm_df, last_price, tolerance, use_sbr_rbs, strategy_config, "H1")

    swing_lows = _find_swings(entry_df, "low", "low")
    swing_highs = _find_swings(entry_df, "high", "high")

    if not swing_lows:
        swing_lows = [float(entry_df["low"].tail(50).min())]
        notes.append("No clear swing low found; using recent low fallback.")

    if not swing_highs:
        swing_highs = [float(entry_df["high"].tail(50).max())]
        notes.append("No clear swing high found; using recent high fallback.")

    support_levels = _dedupe_recent(swing_lows, tolerance=tolerance / 2)
    resistance_levels = _dedupe_recent(swing_highs, tolerance=tolerance / 2)

    nearest_support = _nearest_support(support_levels, last_price)
    nearest_resistance = _nearest_resistance(resistance_levels, last_price)

    near_support = nearest_support is not None and abs(last_price - nearest_support) <= tolerance
    near_resistance = nearest_resistance is not None and abs(last_price - nearest_resistance) <= tolerance
    bullish_context = _is_bullish_context(confirm_df)
    bearish_context = _is_bearish_context(confirm_df)
    m15_rejection = _detect_rejection(entry_df, strategy_config, "M15")
    notes.extend(m15_rejection.get("notes", []))
    zone_type = "NONE"
    zone_level = None
    zone_direction = "NEUTRAL"
    rbs_setup = (None, {})
    sbr_setup = (None, {})
    if use_sbr_rbs:
        rbs_setup = _select_rbs_level(entry_df, resistance_levels, last_price, tolerance, strategy_config)
        sbr_setup = _select_sbr_level(entry_df, support_levels, last_price, tolerance, strategy_config)
    rbs_level, rbs_details = rbs_setup
    sbr_level, sbr_details = sbr_setup

    if rbs_level is not None and bullish_context:
        zone_type = "RBS"
        zone_level = rbs_level
        zone_direction = "BUY"
        notes.append("M15: valid RBS detected from body close above resistance plus bullish FVG.")
    elif sbr_level is not None and bearish_context:
        zone_type = "SBR"
        zone_level = sbr_level
        zone_direction = "SELL"
        notes.append("M15: valid SBR detected from body close below support plus bearish FVG.")

    if near_support and near_resistance:
        support_distance = abs(last_price - float(nearest_support))
        resistance_distance = abs(last_price - float(nearest_resistance))
        if zone_type != "NONE":
            pass
        elif support_distance <= resistance_distance:
            zone_type = "SNR_SUPPORT"
            zone_level = nearest_support
            zone_direction = "BUY"
        else:
            zone_type = "SNR_RESISTANCE"
            zone_level = nearest_resistance
            zone_direction = "SELL"
    elif near_support:
        if zone_type == "NONE":
            zone_type = "SNR_SUPPORT"
            zone_level = nearest_support
            zone_direction = "BUY"
    elif near_resistance:
        if zone_type == "NONE":
            zone_type = "SNR_RESISTANCE"
            zone_level = nearest_resistance
            zone_direction = "SELL"

    if zone_type == "NONE":
        notes.append("Price is not close to the nearest support or resistance zone.")
    else:
        notes.append(f"Price is close to {zone_type} zone.")
    zone_distance = round(abs(last_price - float(zone_level)), 3) if zone_level is not None else None
    m15_zone = {
        "label": "M15",
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "zone_type": zone_type,
        "zone_direction": zone_direction,
        "zone_level": zone_level,
        "zone_distance": zone_distance,
        "zone_validation": (
            str(rbs_details.get("validation", ""))
            if zone_type == "RBS"
            else str(sbr_details.get("validation", "")) if zone_type == "SBR" else ""
        ),
        "fvg": (
            rbs_details.get("fvg")
            if zone_type == "RBS"
            else sbr_details.get("fvg") if zone_type == "SBR" else None
        ),
        "rejection": m15_rejection,
        "notes": notes,
    }
    primary_zone = _choose_primary_zone(h4_zone, h1_zone, m15_zone, strategy_config)
    for zone in (h4_zone, h1_zone, m15_zone):
        zone.update(_score_zone_quality(zone, tolerance, strategy_config))
    primary_zone.update(_score_zone_quality(primary_zone, tolerance, strategy_config))
    combined_notes = []
    combined_notes.extend(h4_zone.get("notes", []))
    combined_notes.extend(h1_zone.get("notes", []))
    combined_notes.extend(notes)
    if primary_zone.get("zone_confluence"):
        combined_notes.append(f"M15 execution zone has HTF bias from {', '.join(primary_zone.get('htf_bias_sources', []))}.")
    if primary_zone.get("htf_conflict_sources"):
        combined_notes.append(f"M15 execution zone conflicts with HTF zone from {', '.join(primary_zone.get('htf_conflict_sources', []))}.")

    return {
        "support_levels": h1_zone.get("support_levels") or support_levels,
        "resistance_levels": h1_zone.get("resistance_levels") or resistance_levels,
        "nearest_support": primary_zone.get("nearest_support"),
        "nearest_resistance": primary_zone.get("nearest_resistance"),
        "zone_level": primary_zone.get("zone_level"),
        "zone_type": primary_zone.get("zone_type"),
        "zone_direction": primary_zone.get("zone_direction"),
        "zone_distance": primary_zone.get("zone_distance"),
        "zone_source": primary_zone.get("zone_source", "M15"),
        "zone_confluence": primary_zone.get("zone_confluence", False),
        "htf_bias_sources": primary_zone.get("htf_bias_sources", []),
        "htf_conflict_sources": primary_zone.get("htf_conflict_sources", []),
        "zone_validation": primary_zone.get("zone_validation", ""),
        "fvg": primary_zone.get("fvg"),
        "zone_quality_score": primary_zone.get("zone_quality_score", 0),
        "zone_quality_grade": primary_zone.get("zone_quality_grade", "F"),
        "zone_quality_reasons": primary_zone.get("zone_quality_reasons", []),
        "zone_tolerance": round(tolerance, 3),
        "h4_zone": h4_zone,
        "h1_zone": h1_zone,
        "m15_zone": m15_zone,
        "h4_rejection": h4_zone.get("rejection", {}),
        "h1_rejection": h1_zone.get("rejection", {}),
        "m15_rejection": m15_zone.get("rejection", {}),
        "notes": combined_notes,
    }
