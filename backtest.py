from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from core.ai_filter import analyze_signal
from core.decision import make_decision
from core.learning import (
    ensure_learning_db,
    learned_zone_bias,
    learning_enabled,
    record_zone_outcome,
    resolve_db_path,
)
from core.mt5_client import MT5Client
from core.risk import build_risk_plan
from core.structure import analyze_structure


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
LOGS_DIR = BASE_DIR / "logs"
BACKTEST_LOG_PATH = LOGS_DIR / "backtest.csv"

BACKTEST_COLUMNS = [
    "timestamp",
    "symbol",
    "entry_time",
    "exit_time",
    "action",
    "score",
    "entry_price",
    "exit_price",
    "sl",
    "tp",
    "result",
    "pips",
    "reasons",
]


def load_config() -> Dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def ensure_backtest_log() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if BACKTEST_LOG_PATH.exists() and BACKTEST_LOG_PATH.stat().st_size > 0:
        return
    with BACKTEST_LOG_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=BACKTEST_COLUMNS)
        writer.writeheader()


def write_backtest_rows(rows: List[Dict[str, Any]]) -> None:
    ensure_backtest_log()
    with BACKTEST_LOG_PATH.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=BACKTEST_COLUMNS)
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in BACKTEST_COLUMNS})


def trend_slice(df: pd.DataFrame, current_time: pd.Timestamp, min_rows: int = 60) -> pd.DataFrame:
    sliced = df[df["time"] <= current_time].copy()
    if len(sliced) < min_rows:
        return pd.DataFrame()
    return sliced


def simulate_exit(
    forward_df: pd.DataFrame,
    action: str,
    sl: float,
    tp: float,
) -> Tuple[Optional[pd.Timestamp], Optional[float], str]:
    for _, candle in forward_df.iterrows():
        low = float(candle["low"])
        high = float(candle["high"])
        candle_time = candle["time"]

        if action == "BUY":
            sl_hit = low <= sl
            tp_hit = high >= tp
        else:
            sl_hit = high >= sl
            tp_hit = low <= tp

        if sl_hit and tp_hit:
            return candle_time, sl, "SL"
        if sl_hit:
            return candle_time, sl, "SL"
        if tp_hit:
            return candle_time, tp, "TP"

    return None, None, "OPEN"


def pips_result(action: str, entry_price: float, exit_price: float, point: float) -> float:
    if action == "BUY":
        return round((exit_price - entry_price) / point, 2)
    return round((entry_price - exit_price) / point, 2)


def run_backtest(
    mt5_client: MT5Client,
    config: Dict[str, Any],
    symbol: str,
    bars: int,
    write_log: bool = True,
    write_learning: bool = True,
) -> Dict[str, Any]:
    mt5_client.ensure_symbol(symbol)
    symbol_info = mt5_client.get_symbol_info(symbol)
    point = float(getattr(symbol_info, "point", 0.01) or 0.01)

    timeframes = config.get("timeframes", {}) or {}
    entry_tf = timeframes.get("entry", "M15")
    confirm_1_tf = timeframes.get("confirm_1", "H1")
    confirm_2_tf = timeframes.get("confirm_2", "H4")

    entry_df = mt5_client.get_candles(symbol, entry_tf, count=bars)
    confirm_1_df = mt5_client.get_candles(symbol, confirm_1_tf, count=max(300, bars))
    confirm_2_df = mt5_client.get_candles(symbol, confirm_2_tf, count=max(300, bars))

    if entry_df.empty:
        raise RuntimeError(f"No candle data returned for {symbol} {entry_tf}.")

    learning_db_path = resolve_db_path(config, BASE_DIR)
    strategy_version = str((config.get("strategy", {}) or {}).get("version", "default"))
    if learning_enabled(config):
        ensure_learning_db(learning_db_path)

    rows: List[Dict[str, Any]] = []
    wins = 0
    losses = 0
    skipped = 0
    total_pips = 0.0
    next_available_index = 60

    for index in range(60, len(entry_df) - 1):
        if index < next_available_index:
            continue

        current_time = entry_df["time"].iloc[index]
        entry_slice = entry_df.iloc[: index + 1].copy()
        confirm_1_slice = trend_slice(confirm_1_df, current_time)
        confirm_2_slice = trend_slice(confirm_2_df, current_time)

        if confirm_1_slice.empty or confirm_2_slice.empty:
            skipped += 1
            continue

        data = {
            "symbol": symbol,
            "timeframes": {
                "entry": entry_tf,
                "confirm_1": confirm_1_tf,
                "confirm_2": confirm_2_tf,
            },
            "entry": entry_slice,
            "confirm_1": confirm_1_slice,
            "confirm_2": confirm_2_slice,
        }

        structure_result = analyze_structure(data, config)
        learning_context: Dict[str, Any] = {}
        if learning_enabled(config):
            zone_type = str(structure_result.get("zone_type", "NONE"))
            learning_context = {
                action_name: learned_zone_bias(learning_db_path, config, symbol, action_name, zone_type)
                for action_name in ("BUY", "SELL")
            }
        signal = analyze_signal(data, structure_result, config, learning_context=learning_context)
        decision = make_decision(signal, config)
        action = decision.get("action", "SKIP")

        if action not in {"BUY", "SELL"}:
            skipped += 1
            continue

        entry_price = float(entry_df["close"].iloc[index])
        risk_plan = build_risk_plan(
            action,
            entry_price,
            config,
            symbol_info=symbol_info,
            structure_result=structure_result,
        )
        sl = risk_plan.get("estimated_sl_price")
        tp = risk_plan.get("estimated_tp_price")
        if sl is None or tp is None:
            skipped += 1
            continue

        forward_df = entry_df.iloc[index + 1 :].copy()
        exit_time, exit_price, result = simulate_exit(forward_df, action, float(sl), float(tp))
        if exit_time is None or exit_price is None:
            skipped += 1
            continue

        trade_pips = pips_result(action, entry_price, float(exit_price), point)
        total_pips += trade_pips
        if result == "TP":
            wins += 1
        elif result == "SL":
            losses += 1

        if write_learning and learning_enabled(config):
            record_zone_outcome(
                learning_db_path,
                symbol=symbol,
                action=action,
                entry_time=str(current_time),
                strategy_version=strategy_version,
                zone_type=str(structure_result.get("zone_type", "NONE")),
                zone_direction=str(structure_result.get("zone_direction", "NEUTRAL")),
                score=int(decision.get("score", 0)),
                result=result,
                pips=trade_pips,
                source="backtest",
            )

        exit_indexes = entry_df.index[entry_df["time"] == exit_time].tolist()
        if exit_indexes:
            next_available_index = int(exit_indexes[0]) + 1

        rows.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "symbol": symbol,
                "entry_time": current_time,
                "exit_time": exit_time,
                "action": action,
                "score": decision.get("score", 0),
                "entry_price": round(entry_price, int(risk_plan.get("digits", 2))),
                "exit_price": exit_price,
                "sl": sl,
                "tp": tp,
                "result": result,
                "pips": trade_pips,
                "reasons": " | ".join(decision.get("reasons", [])),
            }
        )

    if write_log:
        write_backtest_rows(rows)

    trades = len(rows)
    win_rate = round((wins / trades) * 100, 2) if trades else 0.0
    return {
        "symbol": symbol,
        "bars": len(entry_df),
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "skipped": skipped,
        "win_rate": win_rate,
        "total_pips": round(total_pips, 2),
        "log_path": str(BACKTEST_LOG_PATH) if write_log else "disabled",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a safe, order-free MT5 candle backtest.")
    parser.add_argument("--symbol", default=None, help="Override symbol for backtest, for example XAUUSD.vx.")
    parser.add_argument("--bars", type=int, default=1000, help="Number of entry timeframe bars to load.")
    parser.add_argument("--no-learn", action="store_true", help="Do not write backtest outcomes to learning DB.")
    parser.add_argument("--no-log", action="store_true", help="Do not append backtest rows to logs/backtest.csv.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    symbol = args.symbol or str(config.get("symbol", "XAUUSD"))

    mt5_client = MT5Client()
    try:
        mt5_client.initialize()
        account_type = mt5_client.get_account_type()
        print(f"Account Type: {account_type}")
        print("Backtest mode: order execution disabled.")
        summary = run_backtest(
            mt5_client,
            config,
            symbol=symbol,
            bars=args.bars,
            write_log=not args.no_log,
            write_learning=not args.no_learn,
        )
        print("Backtest completed.")
        print(f"Symbol: {summary['symbol']}")
        print(f"Bars: {summary['bars']}")
        print(f"Trades: {summary['trades']}")
        print(f"Wins: {summary['wins']}")
        print(f"Losses: {summary['losses']}")
        print(f"Skipped signals: {summary['skipped']}")
        print(f"Win rate: {summary['win_rate']}%")
        print(f"Total pips: {summary['total_pips']}")
        print(f"Log: {summary['log_path']}")
    finally:
        mt5_client.shutdown()


if __name__ == "__main__":
    main()
