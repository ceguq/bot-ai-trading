"""Performance and position reporting for bot-owned demo trades."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List


def _position_type_label(mt5_module: Any, position_type: int) -> str:
    if position_type == getattr(mt5_module, "POSITION_TYPE_BUY", 0):
        return "BUY"
    if position_type == getattr(mt5_module, "POSITION_TYPE_SELL", 1):
        return "SELL"
    return str(position_type)


def position_snapshots(mt5_client: Any, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    symbol = str(config.get("symbol", "XAUUSD"))
    trade_config = config.get("trade", {}) or {}
    magic_number = int(trade_config.get("magic_number", 20260604))
    positions = mt5_client.get_open_positions(symbol, magic_number=magic_number)
    mt5 = mt5_client.mt5

    rows: List[Dict[str, Any]] = []
    for position in positions:
        rows.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "symbol": symbol,
                "ticket": getattr(position, "ticket", ""),
                "type": _position_type_label(mt5, int(getattr(position, "type", -1))),
                "volume": getattr(position, "volume", ""),
                "price_open": getattr(position, "price_open", ""),
                "price_current": getattr(position, "price_current", ""),
                "sl": getattr(position, "sl", ""),
                "tp": getattr(position, "tp", ""),
                "profit": getattr(position, "profit", ""),
                "swap": getattr(position, "swap", ""),
                "magic": getattr(position, "magic", ""),
                "comment": getattr(position, "comment", ""),
            }
        )
    return rows


def performance_summary(mt5_client: Any, config: Dict[str, Any], days: int = 30) -> Dict[str, Any]:
    symbol = str(config.get("symbol", "XAUUSD"))
    magic_number = int((config.get("trade", {}) or {}).get("magic_number", 20260604))
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    deals = mt5_client.get_history_deals(date_from, date_to, symbol=symbol, magic_number=magic_number)
    mt5 = mt5_client.mt5
    out_entries = {
        getattr(mt5, "DEAL_ENTRY_OUT", 1),
        getattr(mt5, "DEAL_ENTRY_INOUT", 2),
        getattr(mt5, "DEAL_ENTRY_OUT_BY", 3),
    }

    closed_deals = [deal for deal in deals if int(getattr(deal, "entry", -1)) in out_entries]
    total_profit = round(sum(float(getattr(deal, "profit", 0.0)) for deal in closed_deals), 2)
    wins = sum(1 for deal in closed_deals if float(getattr(deal, "profit", 0.0)) > 0)
    losses = sum(1 for deal in closed_deals if float(getattr(deal, "profit", 0.0)) < 0)
    breakeven = sum(1 for deal in closed_deals if float(getattr(deal, "profit", 0.0)) == 0)
    total_closed = len(closed_deals)
    win_rate = round((wins / total_closed) * 100, 2) if total_closed else 0.0
    account_info = mt5_client.get_account_info()
    open_positions = mt5_client.get_open_positions(symbol, magic_number=magic_number)
    floating_profit = round(sum(float(getattr(position, "profit", 0.0)) for position in open_positions), 2)

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "days": days,
        "closed_trades": total_closed,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate": win_rate,
        "total_profit": total_profit,
        "account_balance": getattr(account_info, "balance", ""),
        "account_equity": getattr(account_info, "equity", ""),
        "floating_profit": floating_profit,
        "margin": getattr(account_info, "margin", ""),
        "open_positions": len(open_positions),
        "magic": magic_number,
    }
