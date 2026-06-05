"""Demo-only order executor.

There is intentionally no live order function in this project.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from core.safety import validate_trading_safety


_LAST_EXECUTED_CANDLES: Dict[Tuple[str, int], str] = {}


def _result_to_dict(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}
    if hasattr(result, "_asdict"):
        return dict(result._asdict())
    return {
        key: getattr(result, key)
        for key in dir(result)
        if not key.startswith("_") and not callable(getattr(result, key))
    }


def _success_codes(mt5_module: Any) -> set:
    codes = {0}
    for name in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED", "TRADE_RETCODE_DONE_PARTIAL"):
        value = getattr(mt5_module, name, None)
        if value is not None:
            codes.add(int(value))
    return codes


def _is_check_passed(mt5_module: Any, check_result: Any) -> bool:
    if check_result is None:
        return False
    retcode = getattr(check_result, "retcode", None)
    if retcode is None:
        return False
    return int(retcode) in _success_codes(mt5_module)


def _filling_candidates(mt5_module: Any, symbol_info: Any) -> list[Optional[int]]:
    """Return filling modes to test with order_check.

    MT5 exposes symbol filling support as broker-specific flags. Some brokers
    report filling_mode=1 for FOK support while ORDER_FILLING_FOK itself is 0.
    Testing candidates with order_check is the safest practical path.
    """
    candidates: list[Optional[int]] = []
    filling_mode = getattr(symbol_info, "filling_mode", None)

    if filling_mode == 1:
        candidates.append(getattr(mt5_module, "ORDER_FILLING_FOK", None))
    elif filling_mode == 2:
        candidates.append(getattr(mt5_module, "ORDER_FILLING_IOC", None))
    elif filling_mode == 4:
        candidates.append(getattr(mt5_module, "ORDER_FILLING_RETURN", None))

    candidates.extend(
        [
            getattr(mt5_module, "ORDER_FILLING_FOK", None),
            getattr(mt5_module, "ORDER_FILLING_IOC", None),
            getattr(mt5_module, "ORDER_FILLING_RETURN", None),
            None,
        ]
    )

    unique_candidates: list[Optional[int]] = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates


def _check_with_supported_filling(mt5_module: Any, request: Dict[str, Any], symbol_info: Any) -> tuple[Any, Dict[str, Any]]:
    last_check_result = None
    last_request = dict(request)

    for filling_mode in _filling_candidates(mt5_module, symbol_info):
        check_request = dict(request)
        if filling_mode is None:
            check_request.pop("type_filling", None)
        else:
            check_request["type_filling"] = filling_mode

        check_result = mt5_module.order_check(check_request)
        last_check_result = check_result
        last_request = check_request
        if _is_check_passed(mt5_module, check_result):
            return check_result, check_request

    return last_check_result, last_request


def _base_trade_result(action: str, comment: str = "") -> Dict[str, Any]:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "order_ticket": None,
        "retcode": None,
        "price": None,
        "sl": None,
        "tp": None,
        "lot": None,
        "comment": comment,
        "message": "",
        "check_passed": False,
        "sent": False,
    }


def execute_demo_order(mt5_client: Any, risk_plan: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a demo order after safety validation and order_check."""
    validation = validate_trading_safety(mt5_client, config)
    action = str(risk_plan.get("action", "SKIP")).upper()
    trade_config = config.get("trade", {}) or {}
    symbol = str(config.get("symbol", "XAUUSD"))
    magic_number = int(trade_config.get("magic_number", 20260604))
    comment = str(trade_config.get("comment", "AI_DEMO_BOT"))

    result = _base_trade_result(action, comment)

    if not validation.get("can_execute", False):
        result["message"] = validation.get("message", "Execution disabled.")
        return result

    if action not in {"BUY", "SELL"}:
        result["message"] = "Action is SKIP. No demo order sent."
        return result

    if risk_plan.get("estimated_sl_price") is None or risk_plan.get("estimated_tp_price") is None:
        raise RuntimeError("SL and TP are required for demo_trade execution.")

    max_layer = int(risk_plan.get("max_layer", 1))
    open_positions = mt5_client.get_open_positions(symbol, magic_number=magic_number)
    if len(open_positions) >= max_layer:
        result["message"] = f"Max layer reached ({len(open_positions)}/{max_layer}). No demo order sent."
        return result

    signal_time = str(risk_plan.get("signal_time", ""))
    execution_key = (symbol, magic_number)
    if signal_time and _LAST_EXECUTED_CANDLES.get(execution_key) == signal_time:
        result["message"] = "This candle was already executed. No repeated demo order sent."
        return result

    mt5 = mt5_client.mt5
    symbol_info = mt5_client.ensure_symbol(symbol)
    tick = mt5_client.get_latest_tick(symbol)

    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
    price = float(tick.ask if action == "BUY" else tick.bid)
    sl = float(risk_plan["estimated_sl_price"])
    tp = float(risk_plan["estimated_tp_price"])
    lot = float(risk_plan["lot"])

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": int(trade_config.get("deviation", 30)),
        "magic": magic_number,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    check_result, request = _check_with_supported_filling(mt5, request, symbol_info)
    check_dict = _result_to_dict(check_result)
    result.update(
        {
            "retcode": check_dict.get("retcode"),
            "price": price,
            "sl": sl,
            "tp": tp,
            "lot": lot,
            "message": check_dict.get("comment", "Order check failed."),
        }
    )

    if not _is_check_passed(mt5, check_result):
        result["message"] = f"DEMO ORDER CHECK FAILED: {result['message']}"
        return result

    result["check_passed"] = True
    print("DEMO ORDER CHECK: PASSED")

    send_result = mt5.order_send(request)
    send_dict = _result_to_dict(send_result)
    result["retcode"] = send_dict.get("retcode")
    result["order_ticket"] = send_dict.get("order") or send_dict.get("deal")
    result["message"] = send_dict.get("comment", "Order send finished.")

    if result["retcode"] is not None and int(result["retcode"]) in _success_codes(mt5):
        result["sent"] = True
        if signal_time:
            _LAST_EXECUTED_CANDLES[execution_key] = signal_time
        print(f"DEMO ORDER SENT: ticket {result['order_ticket']}")
    else:
        result["message"] = f"DEMO ORDER SEND FAILED: {result['message']}"

    return result
