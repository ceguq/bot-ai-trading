"""Safety guardrails for demo-only execution."""

from __future__ import annotations

from typing import Any, Dict


class TradingSafetyError(RuntimeError):
    """Raised when trading or order modification is not allowed."""


def get_mode_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return config.get("mode", {}) or {}


def get_trading_mode(config: Dict[str, Any]) -> str:
    return str(get_mode_config(config).get("trading_mode", "signal_only")).lower()


def real_account_warning() -> str:
    return (
        "\n"
        "============================================================\n"
        "REAL ACCOUNT DETECTED. EXECUTION BLOCKED.\n"
        "This project is demo-only. No order, modify, close, or live\n"
        "trading action is allowed on a REAL account.\n"
        "============================================================"
    )


def validate_trading_safety(mt5_client: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate account and config before any trading action.

    signal_only is safe for analysis but returns can_execute=False.
    demo_trade can execute only when the MT5 account is verified DEMO.
    """
    mode_config = get_mode_config(config)
    trading_mode = get_trading_mode(config)
    allow_demo_order = bool(mode_config.get("allow_demo_order", False))
    allow_live_order = bool(mode_config.get("allow_live_order", False))

    account_type = mt5_client.get_account_type()

    if account_type == "REAL":
        raise TradingSafetyError("REAL account detected. Demo bot execution is blocked.")

    if trading_mode == "signal_only":
        return {
            "safe": True,
            "can_execute": False,
            "account_type": account_type,
            "mode": trading_mode,
            "message": "Signal-only mode. Order execution is disabled.",
        }

    if trading_mode != "demo_trade":
        raise TradingSafetyError(f"Unsupported trading_mode: {trading_mode}. Allowed: signal_only / demo_trade.")

    if account_type != "DEMO" or not mt5_client.is_demo_account():
        raise TradingSafetyError("Account type cannot be verified. Execution blocked.")

    if not allow_demo_order:
        raise TradingSafetyError("allow_demo_order is false. Demo order execution is blocked.")

    if allow_live_order:
        raise TradingSafetyError("allow_live_order must remain false. Execution blocked.")

    return {
        "safe": True,
        "can_execute": True,
        "account_type": account_type,
        "mode": trading_mode,
        "message": "Demo account verified. Demo order execution is allowed.",
    }
