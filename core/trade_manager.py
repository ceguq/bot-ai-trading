"""Demo position monitor and break-even helper."""

from __future__ import annotations

from typing import Any, Dict, List

from core.safety import validate_trading_safety


def get_bot_positions(mt5_client: Any, config: Dict[str, Any]) -> List[Any]:
    symbol = str(config.get("symbol", "XAUUSD"))
    magic_number = int((config.get("trade", {}) or {}).get("magic_number", 20260604))
    return mt5_client.get_open_positions(symbol, magic_number=magic_number)


def print_open_positions(positions: List[Any]) -> None:
    if not positions:
        print("Open demo positions: 0")
        return

    print(f"Open demo positions: {len(positions)}")
    for position in positions:
        print(
            "  "
            f"ticket={getattr(position, 'ticket', '-')}, "
            f"type={getattr(position, 'type', '-')}, "
            f"lot={getattr(position, 'volume', '-')}, "
            f"price_open={getattr(position, 'price_open', '-')}, "
            f"sl={getattr(position, 'sl', '-')}, "
            f"tp={getattr(position, 'tp', '-')}"
        )


def move_to_break_even(mt5_client: Any, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Move SL to entry price for bot positions only, on verified demo accounts only."""
    validation = validate_trading_safety(mt5_client, config)
    if not validation.get("can_execute", False):
        return []

    trade_config = config.get("trade", {}) or {}
    if not bool(trade_config.get("allow_move_to_be", True)):
        return []

    symbol = str(config.get("symbol", "XAUUSD"))
    magic_number = int(trade_config.get("magic_number", 20260604))
    threshold_pips = int((config.get("risk", {}) or {}).get("move_to_be_after_pips", 250))

    mt5 = mt5_client.mt5
    symbol_info = mt5_client.get_symbol_info(symbol)
    point = float(getattr(symbol_info, "point", 0.01) or 0.01)
    digits = int(getattr(symbol_info, "digits", 2) or 2)
    tick = mt5_client.get_latest_tick(symbol)
    threshold = threshold_pips * point

    updates: List[Dict[str, Any]] = []
    positions = get_bot_positions(mt5_client, config)

    for position in positions:
        position_magic = int(getattr(position, "magic", -1))
        if position_magic != magic_number:
            continue

        ticket = getattr(position, "ticket", None)
        position_type = int(getattr(position, "type", -1))
        entry_price = float(getattr(position, "price_open", 0.0))
        current_sl = float(getattr(position, "sl", 0.0) or 0.0)
        current_tp = float(getattr(position, "tp", 0.0) or 0.0)

        is_buy = position_type == getattr(mt5, "POSITION_TYPE_BUY", 0)
        is_sell = position_type == getattr(mt5, "POSITION_TYPE_SELL", 1)

        should_modify = False
        if is_buy:
            current_price = float(tick.bid)
            should_modify = (current_price - entry_price) >= threshold and (current_sl == 0.0 or current_sl < entry_price)
        elif is_sell:
            current_price = float(tick.ask)
            should_modify = (entry_price - current_price) >= threshold and (current_sl == 0.0 or current_sl > entry_price)

        if not should_modify:
            continue

        new_sl = round(entry_price, digits)
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": new_sl,
            "tp": current_tp,
            "magic": magic_number,
            "comment": f"{trade_config.get('comment', 'AI_DEMO_BOT')}_BE",
        }
        result = mt5.order_send(request)
        result_dict = result._asdict() if hasattr(result, "_asdict") else {"result": str(result)}
        updates.append({"ticket": ticket, "new_sl": new_sl, "result": result_dict})

    return updates


def manage_demo_positions(mt5_client: Any, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    validation = validate_trading_safety(mt5_client, config)
    if not validation.get("can_execute", False):
        return []

    positions = get_bot_positions(mt5_client, config)
    print_open_positions(positions)

    if bool((config.get("trade", {}) or {}).get("allow_move_to_be", True)):
        updates = move_to_break_even(mt5_client, config)
        for update in updates:
            print(f"Move SL to BE requested for ticket {update['ticket']} -> SL {update['new_sl']}")
        return updates

    return []
