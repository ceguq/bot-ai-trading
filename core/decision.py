"""Final decision rules after signal scoring."""

from __future__ import annotations

from typing import Any, Dict


def make_decision(signal: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Return final action BUY, SELL, or SKIP."""
    result = dict(signal)
    reasons = list(signal.get("reasons", []))
    candidate = str(signal.get("candidate_action", "SKIP")).upper()
    score = int(signal.get("score", 0))
    min_score = int((config.get("ai", {}) or {}).get("min_score_entry", 70))
    trade_config = config.get("trade", {}) or {}

    action = "SKIP"
    if candidate == "BUY":
        if not bool(trade_config.get("allow_buy", True)):
            reasons.append("BUY disabled in config.")
        elif score >= min_score:
            action = "BUY"
        else:
            reasons.append(f"BUY score below minimum entry score ({score} < {min_score}).")
    elif candidate == "SELL":
        if not bool(trade_config.get("allow_sell", True)):
            reasons.append("SELL disabled in config.")
        elif score >= min_score:
            action = "SELL"
        else:
            reasons.append(f"SELL score below minimum entry score ({score} < {min_score}).")
    else:
        reasons.append("Candidate action is SKIP.")

    result["action"] = action
    result["reasons"] = reasons
    return result
