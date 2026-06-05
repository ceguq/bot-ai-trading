"""Rule-based scoring filter that mimics an AI decision layer."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd


def _trend(df: pd.DataFrame) -> str:
    if df is None or df.empty or len(df) < 50:
        return "UNKNOWN"
    close = df["close"].astype(float)
    ma50 = close.rolling(50).mean().iloc[-1]
    last_close = close.iloc[-1]
    if last_close > ma50:
        return "BULLISH"
    if last_close < ma50:
        return "BEARISH"
    return "FLAT"


def _last_candle_direction(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "UNKNOWN"
    last = df.iloc[-1]
    if float(last["close"]) > float(last["open"]):
        return "BULLISH"
    if float(last["close"]) < float(last["open"]):
        return "BEARISH"
    return "FLAT"


def _momentum(df: pd.DataFrame) -> str:
    if df is None or df.empty or len(df) < 6:
        return "UNKNOWN"
    closes = df["close"].astype(float)
    recent_change = closes.iloc[-1] - closes.iloc[-6]
    if recent_change > 0:
        return "BULLISH"
    if recent_change < 0:
        return "BEARISH"
    return "FLAT"


def _risk_reward_valid(config: Dict[str, Any], structure_result: Dict[str, Any] | None = None) -> bool:
    risk = config.get("risk", {}) or {}
    strategy = config.get("strategy", {}) or {}
    sl_pips = float(risk.get("sl_pips", 0))
    tp_pips = float(risk.get("tp_pips", 0))
    zone_source = str((structure_result or {}).get("zone_source", ""))
    if zone_source.startswith("M15") and bool(strategy.get("use_m15_scalp_target", True)):
        tp_pips = float(strategy.get("m15_zone_tp_pips", tp_pips))
        if strategy.get("m15_zone_sl_pips") is not None:
            sl_pips = float(strategy.get("m15_zone_sl_pips", sl_pips))
    return sl_pips > 0 and tp_pips > 0 and tp_pips >= sl_pips


def _direction_label(action: str) -> str:
    return "BULLISH" if action == "BUY" else "BEARISH"


def _score_action(
    action: str,
    h4_trend: str,
    h1_trend: str,
    m15_candle: str,
    momentum: str,
    zone_type: str,
    rr_valid: bool,
) -> Tuple[int, List[str]]:
    desired = _direction_label(action)
    opposite = "BEARISH" if desired == "BULLISH" else "BULLISH"
    score = 0
    reasons: List[str] = []

    if h4_trend == desired:
        score += 20
        reasons.append(f"H4 {desired.lower()}")
    elif h4_trend == opposite:
        score -= 30
        reasons.append(f"H4 {opposite.lower()} against {action} (-30)")

    if h1_trend == desired:
        score += 20
        reasons.append(f"H1 {desired.lower()}")

    buy_zones = {"RBS", "SNR_SUPPORT"}
    sell_zones = {"SBR", "SNR_RESISTANCE"}
    if action == "BUY" and zone_type in buy_zones:
        score += 20
        reasons.append(f"Price near {zone_type} zone")
    if action == "SELL" and zone_type in sell_zones:
        score += 20
        reasons.append(f"Price near {zone_type} zone")

    if m15_candle == desired:
        score += 15
        reasons.append(f"M15 {desired.lower()} candle")

    if momentum == desired:
        score += 15
        reasons.append(f"Momentum {desired.lower()}")

    if rr_valid:
        score += 10
        reasons.append("Risk reward valid")

    return score, reasons


def _zone_favors_action(zone_type: str, action: str) -> bool:
    if action == "BUY":
        return zone_type in {"RBS", "SNR_SUPPORT"}
    if action == "SELL":
        return zone_type in {"SBR", "SNR_RESISTANCE"}
    return False


def analyze_signal(
    data: Dict[str, Any],
    structure_result: Dict[str, Any],
    config: Dict[str, Any],
    news_context: Dict[str, Any] | None = None,
    learning_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return candidate action, score, reasons, and last price."""
    entry_df = data.get("entry")
    if entry_df is None or entry_df.empty:
        return {
            "candidate_action": "SKIP",
            "score": 0,
            "reasons": ["Entry data is empty."],
            "last_price": None,
        }

    h4_trend = _trend(data.get("confirm_2"))
    h1_trend = _trend(data.get("confirm_1"))
    m15_candle = _last_candle_direction(entry_df)
    m15_momentum = _momentum(entry_df)
    zone_type = str(structure_result.get("zone_type", "NONE"))
    rr_valid = _risk_reward_valid(config, structure_result)
    strategy_config = config.get("strategy", {}) or {}
    require_zone = bool(strategy_config.get("require_zone_for_entry", False))
    zone_direction = str(structure_result.get("zone_direction", "NEUTRAL"))
    news_context = news_context or {}
    learning_context = learning_context or {}

    buy_score, buy_reasons = _score_action("BUY", h4_trend, h1_trend, m15_candle, m15_momentum, zone_type, rr_valid)
    sell_score, sell_reasons = _score_action("SELL", h4_trend, h1_trend, m15_candle, m15_momentum, zone_type, rr_valid)
    zone_source = str(structure_result.get("zone_source", "M15"))
    zone_confluence = bool(structure_result.get("zone_confluence", False))
    htf_bias_sources = list(structure_result.get("htf_bias_sources", []) or [])
    htf_conflict_sources = list(structure_result.get("htf_conflict_sources", []) or [])
    zone_validation = str(structure_result.get("zone_validation", ""))
    zone_quality_score = int(structure_result.get("zone_quality_score", 0) or 0)
    zone_quality_grade = str(structure_result.get("zone_quality_grade", "F"))
    fvg = structure_result.get("fvg") or {}
    for action, score_ref, reasons_ref in (
        ("BUY", "buy", buy_reasons),
        ("SELL", "sell", sell_reasons),
    ):
        if _zone_favors_action(zone_type, action):
            if zone_validation:
                fvg_type = fvg.get("type", "FVG") if isinstance(fvg, dict) else "FVG"
                reasons_ref.append(f"{zone_type} validated by body break and {fvg_type}")
            if zone_source.startswith("M15"):
                if score_ref == "buy":
                    buy_score += 5
                else:
                    sell_score += 5
                reasons_ref.append("M15 execution zone respected")
                if htf_bias_sources:
                    bias_points = 5 * len(htf_bias_sources)
                    if score_ref == "buy":
                        buy_score += bias_points
                    else:
                        sell_score += bias_points
                    reasons_ref.append(f"HTF bias supports M15 zone: {', '.join(htf_bias_sources)}")
                if htf_conflict_sources:
                    conflict_points = 5 * len(htf_conflict_sources)
                    if score_ref == "buy":
                        buy_score -= conflict_points
                    else:
                        sell_score -= conflict_points
                    reasons_ref.append(f"HTF zone conflict: {', '.join(htf_conflict_sources)} (-{conflict_points})")
            elif zone_source == "H4":
                if score_ref == "buy":
                    buy_score += 10
                else:
                    sell_score += 10
                reasons_ref.append("H4 major zone supports setup")
            elif zone_source.startswith("H1"):
                if score_ref == "buy":
                    buy_score += 5
                else:
                    sell_score += 5
                if zone_source == "H1_REJECTION":
                    reasons_ref.append("H1 rejection zone supports setup")
                else:
                    reasons_ref.append("H1 refined zone supports setup")
            elif zone_source == "H1+H4" or zone_confluence:
                if score_ref == "buy":
                    buy_score += 15
                else:
                    sell_score += 15
                reasons_ref.append("H4 major zone and H1 refined zone confluence")
            if zone_quality_score >= 80:
                if score_ref == "buy":
                    buy_score += 10
                else:
                    sell_score += 10
                reasons_ref.append(f"Zone quality {zone_quality_grade} ({zone_quality_score}) +10")
            elif zone_quality_score >= 65:
                if score_ref == "buy":
                    buy_score += 5
                else:
                    sell_score += 5
                reasons_ref.append(f"Zone quality {zone_quality_grade} ({zone_quality_score}) +5")

    h1_rejection = structure_result.get("h1_rejection", {}) or {}
    h1_rejection_direction = str(h1_rejection.get("direction", "NEUTRAL"))
    if h1_rejection_direction in {"BUY", "SELL"}:
        rejection_points = int(strategy_config.get("h1_rejection_score", 15))
        relief_points = int(strategy_config.get("h1_rejection_countertrend_relief", 0))
        rejection_state = str(h1_rejection.get("state", "closed"))
        rejection_type = str(h1_rejection.get("type", "REJECTION")).replace("_", " ").lower()
        reason = f"H1 {rejection_type} on {rejection_state} candle"
        if h1_rejection_direction == "BUY":
            buy_score += rejection_points
            buy_reasons.append(reason)
            if h4_trend == "BEARISH" and relief_points > 0:
                buy_score += relief_points
                buy_reasons.append(f"H1 rejection reduces H4 countertrend penalty (+{relief_points})")
        else:
            sell_score += rejection_points
            sell_reasons.append(reason)
            if h4_trend == "BULLISH" and relief_points > 0:
                sell_score += relief_points
                sell_reasons.append(f"H1 rejection reduces H4 countertrend penalty (+{relief_points})")

    for action, score_ref, reasons_ref in (
        ("BUY", "buy", buy_reasons),
        ("SELL", "sell", sell_reasons),
    ):
        if not _zone_favors_action(zone_type, action):
            continue
        bias = learning_context.get(action, {}) or {}
        points = int(bias.get("points", 0) or 0)
        reason = bias.get("reason")
        if points:
            if score_ref == "buy":
                buy_score += points
            else:
                sell_score += points
            reasons_ref.append(f"Learned zone bias {points:+d}: {reason}")

    if buy_score <= 0 and sell_score <= 0:
        candidate_action = "SKIP"
        score = 0
        reasons = ["No clear BUY or SELL candidate."]
    elif buy_score > sell_score:
        candidate_action = "BUY"
        score = max(0, min(100, buy_score))
        reasons = buy_reasons
    elif sell_score > buy_score:
        candidate_action = "SELL"
        score = max(0, min(100, sell_score))
        reasons = sell_reasons
    else:
        candidate_action = "SKIP"
        score = max(0, min(100, buy_score))
        reasons = ["BUY and SELL scores are tied; skipping to avoid ambiguous entry."]

    if not reasons:
        reasons = ["Signal conditions are not strong enough."]

    if require_zone and zone_type == "NONE":
        candidate_action = "SKIP"
        score = 0
        reasons.append("Zone confirmation required, but price is not near SBR/RBS/SNR zone.")

    if bool(strategy_config.get("use_zone_quality_filter", True)) and candidate_action in {"BUY", "SELL"}:
        min_quality = int(strategy_config.get("min_zone_quality_for_entry", 65))
        if zone_source.startswith("M15"):
            min_quality = int(strategy_config.get("min_m15_zone_quality_for_entry", min_quality))
        elif zone_source == "H1_REJECTION":
            min_quality = int(strategy_config.get("min_h1_rejection_zone_quality_for_entry", min_quality))
        if zone_quality_score < min_quality:
            blocked_action = candidate_action
            candidate_action = "SKIP"
            score = 0
            reasons.append(
                f"Zone quality {zone_quality_grade} ({zone_quality_score}) below minimum {min_quality}; "
                f"skipping {blocked_action} setup."
            )

    learning_config = config.get("learning", {}) or {}
    if bool(learning_config.get("hard_block_bad_zones", True)) and candidate_action in {"BUY", "SELL"}:
        learned = learning_context.get(candidate_action, {}) or {}
        stats = learned.get("stats", {}) or {}
        samples = int(stats.get("samples", 0) or 0)
        win_rate = float(stats.get("win_rate", 0.0) or 0.0)
        avg_pips = float(stats.get("avg_pips", 0.0) or 0.0)
        min_samples = int(learning_config.get("hard_block_min_samples", 50))
        max_win_rate = float(learning_config.get("hard_block_max_win_rate", 30))
        require_negative_avg = bool(learning_config.get("hard_block_require_negative_avg_pips", True))
        negative_avg_ok = avg_pips < 0 if require_negative_avg else True
        if samples >= min_samples and win_rate <= max_win_rate and negative_avg_ok:
            blocked_action = candidate_action
            candidate_action = "SKIP"
            score = 0
            reasons.append(
                f"Learned hard block: {zone_type}/{blocked_action} has "
                f"samples={samples}, win_rate={win_rate}%, avg_pips={avg_pips}."
            )

    if candidate_action in {"BUY", "SELL"} and zone_direction in {"BUY", "SELL"} and zone_direction != candidate_action:
        blocked_action = candidate_action
        candidate_action = "SKIP"
        score = 0
        reasons.append(f"Zone direction is {zone_direction}; skipping opposite {blocked_action} setup.")

    if (
        bool(strategy_config.get("h1_rejection_blocks_opposite_entry", True))
        and h1_rejection_direction in {"BUY", "SELL"}
        and candidate_action in {"BUY", "SELL"}
        and h1_rejection_direction != candidate_action
    ):
        blocked_action = candidate_action
        candidate_action = "SKIP"
        score = 0
        reasons.append(f"H1 rejection bias is {h1_rejection_direction}; skipping opposite {blocked_action} setup.")

    if news_context.get("blocked"):
        candidate_action = "SKIP"
        score = 0
        reasons.append("MT5 news filter blocked entry.")
    elif news_context.get("enabled"):
        for note in news_context.get("notes", []):
            reasons.append(str(note))

    return {
        "candidate_action": candidate_action,
        "score": int(score),
        "reasons": reasons,
        "last_price": float(entry_df["close"].iloc[-1]),
    }
