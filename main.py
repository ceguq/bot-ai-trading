from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

from core.ai_filter import analyze_signal
from core.decision import make_decision
from core.executor import execute_demo_order
from core.learning import (
    ensure_learning_db,
    learned_zone_bias,
    learning_enabled,
    record_signal,
    resolve_db_path,
)
from core.logger import ensure_log_files, log_performance, log_positions, log_signal, log_trade
from core.market_data import get_multi_timeframe_data
from core.mt5_client import MT5Client
from core.news_filter import analyze_news_context
from core.performance import performance_summary, position_snapshots
from core.risk import build_risk_plan
from core.safety import TradingSafetyError, get_trading_mode, real_account_warning, validate_trading_safety
from core.structure import analyze_structure
from core.trade_manager import manage_demo_positions


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
LOGS_DIR = BASE_DIR / "logs"


def load_config() -> Dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def field(value: Any, name: str, default: Any = "-") -> Any:
    return getattr(value, name, default) if value is not None else default


def latest_entry_candle_time(data: Dict[str, Any]) -> str:
    entry_df = data.get("entry")
    if entry_df is None or entry_df.empty:
        return ""
    return str(entry_df["time"].iloc[-1])


def print_account_summary(mt5_client: MT5Client) -> None:
    account_info = mt5_client.get_account_info()
    account_type = mt5_client.get_account_type()
    print(f"Login: {field(account_info, 'login')}")
    print(f"Server: {field(account_info, 'server')}")
    print(f"Account Type: {account_type}")
    print(f"Balance: {field(account_info, 'balance')}")
    print(f"Equity: {field(account_info, 'equity')}")


def print_signal_summary(
    config: Dict[str, Any],
    account_type: str,
    decision: Dict[str, Any],
    risk_plan: Dict[str, Any],
    structure_result: Dict[str, Any],
) -> None:
    symbol = str(config.get("symbol", "XAUUSD"))
    mode = get_trading_mode(config)
    reasons = decision.get("reasons", [])

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print(f"Account Type: {account_type}")
    print(f"Symbol: {symbol}")
    print(f"Mode: {mode}")
    print(f"Action: {decision.get('action', 'SKIP')}")
    print(f"Score: {decision.get('score', 0)}")
    print(f"Price: {decision.get('last_price')}")
    print(f"Lot: {risk_plan.get('lot')}")
    print(f"SL: {risk_plan.get('sl_pips')} pips")
    print(f"TP: {risk_plan.get('tp_pips')} pips")
    print(f"Max Layer: {risk_plan.get('max_layer')}")
    print(
        "Zone: "
        f"{structure_result.get('zone_type')} "
        f"({structure_result.get('zone_source')}) "
        f"quality={structure_result.get('zone_quality_score')}/100 "
        f"grade={structure_result.get('zone_quality_grade')}"
    )
    if risk_plan.get("risk_profile"):
        print(f"Risk Profile: {risk_plan.get('risk_profile')}")
    for note in risk_plan.get("risk_notes", []) or []:
        print(note)
    if risk_plan.get("warning"):
        print(risk_plan["warning"])
    print("Reasons:")
    for reason in reasons:
        print(f"- {reason}")


def run_once(mt5_client: MT5Client, config: Dict[str, Any]) -> None:
    symbol = str(config.get("symbol", "XAUUSD"))
    mode = get_trading_mode(config)

    account_type = mt5_client.get_account_type()
    if account_type == "REAL":
        raise TradingSafetyError("REAL account detected. Demo bot execution is blocked.")

    validation = validate_trading_safety(mt5_client, config)
    if mode == "demo_trade":
        print(validation["message"])

    data = get_multi_timeframe_data(mt5_client, symbol, config)
    structure_result = analyze_structure(data, config)
    news_context = analyze_news_context(mt5_client, config)
    learning_context: Dict[str, Any] = {}
    learning_db_path = resolve_db_path(config, BASE_DIR)
    if learning_enabled(config):
        ensure_learning_db(learning_db_path)
        zone_type = str(structure_result.get("zone_type", "NONE"))
        learning_context = {
            action: learned_zone_bias(learning_db_path, config, symbol, action, zone_type)
            for action in ("BUY", "SELL")
        }
    signal = analyze_signal(
        data,
        structure_result,
        config,
        news_context=news_context,
        learning_context=learning_context,
    )
    decision = make_decision(signal, config)

    symbol_info = mt5_client.get_symbol_info(symbol)
    plan_price = decision.get("last_price")
    if mode == "demo_trade" and decision["action"] in {"BUY", "SELL"}:
        tick = mt5_client.get_latest_tick(symbol)
        plan_price = float(tick.ask if decision["action"] == "BUY" else tick.bid)
    risk_plan = build_risk_plan(
        decision["action"],
        plan_price,
        config,
        symbol_info=symbol_info,
        structure_result=structure_result,
    )
    risk_plan["signal_time"] = latest_entry_candle_time(data)

    print_signal_summary(config, account_type, decision, risk_plan, structure_result)
    log_signal(
        LOGS_DIR,
        symbol=symbol,
        mode=mode,
        action=decision["action"],
        score=int(decision.get("score", 0)),
        price=decision.get("last_price"),
        risk_plan=risk_plan,
        reasons=decision.get("reasons", []),
    )
    if learning_enabled(config):
        record_signal(
            learning_db_path,
            source="live_loop",
            symbol=symbol,
            mode=mode,
            entry_time=risk_plan["signal_time"],
            decision=decision,
            structure_result=structure_result,
            risk_plan=risk_plan,
            news_context=news_context,
        )

    if mode == "signal_only":
        print("Signal-only mode: no order execution.")
        return

    if mode == "demo_trade":
        trade_result = execute_demo_order(mt5_client, risk_plan, config)
        log_trade(LOGS_DIR, symbol=symbol, mode=mode, action=decision["action"], trade_result=trade_result)
        if trade_result.get("message"):
            print(trade_result["message"])
        manage_demo_positions(mt5_client, config)
        position_rows = position_snapshots(mt5_client, config)
        log_positions(LOGS_DIR, position_rows)
        summary = performance_summary(mt5_client, config)
        log_performance(LOGS_DIR, summary)
        print(
            "Performance: "
            f"closed={summary['closed_trades']}, "
            f"wins={summary['wins']}, "
            f"losses={summary['losses']}, "
            f"win_rate={summary['win_rate']}%, "
            f"profit={summary['total_profit']}, "
            f"open={summary['open_positions']}"
        )
        return

    raise RuntimeError(f"Unsupported trading_mode: {mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI trading bot.")
    parser.add_argument("--once", action="store_true", help="Run one loop iteration and exit.")
    args = parser.parse_args()

    ensure_log_files(LOGS_DIR)
    mt5_client = MT5Client()

    try:
        config = load_config()
        interval_seconds = int((config.get("loop", {}) or {}).get("interval_seconds", 60))

        mt5_client.initialize()
        print("MT5 initialized using the already logged-in terminal session.")
        print_account_summary(mt5_client)

        if args.once:
            run_once(mt5_client, config)
            return

        while True:
            config = load_config()
            interval_seconds = int((config.get("loop", {}) or {}).get("interval_seconds", interval_seconds))
            try:
                run_once(mt5_client, config)
            except TradingSafetyError as exc:
                if mt5_client.get_account_type() == "REAL":
                    print(real_account_warning())
                print(str(exc))
                break
            except Exception as exc:
                print(f"Loop error: {exc}")

            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    finally:
        mt5_client.shutdown()
        print("MT5 shutdown completed.")


if __name__ == "__main__":
    main()
