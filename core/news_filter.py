"""News filter placeholder for MT5-based news/calendar data.

The installed MetaTrader5 Python package on this machine does not expose
calendar_* functions, so this module is intentionally non-blocking by default.
When a reliable MT5 news/calendar source is available, wire it here and keep
the return contract stable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


def analyze_news_context(mt5_client: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    news_config = config.get("news", {}) or {}
    enabled = bool(news_config.get("enabled", False))

    context = {
        "enabled": enabled,
        "source": news_config.get("source", "mt5"),
        "blocked": False,
        "events": [],
        "notes": [],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }

    if not enabled:
        context["notes"].append("News filter disabled in config.")
        return context

    mt5_module = getattr(mt5_client, "mt5", None)
    calendar_history = getattr(mt5_module, "calendar_value_history", None) if mt5_module is not None else None
    if calendar_history is None:
        context["notes"].append("MT5 Python package does not expose calendar news functions.")
        return context

    # Future implementation point:
    # - fetch events around now for USD / XAU related currencies
    # - mark blocked=True for high-impact events inside the configured window
    # - populate events with time, currency, title, impact, and source
    context["notes"].append("MT5 calendar function detected but event parsing is not implemented yet.")
    return context


def news_reasons(news_context: Dict[str, Any]) -> List[str]:
    if not news_context.get("enabled"):
        return []
    reasons: List[str] = []
    if news_context.get("blocked"):
        reasons.append("MT5 news filter blocked entry.")
    for note in news_context.get("notes", []):
        reasons.append(str(note))
    return reasons
