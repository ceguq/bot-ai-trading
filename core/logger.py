"""CSV logging helpers for signals and demo trade attempts."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


SIGNAL_COLUMNS = [
    "timestamp",
    "symbol",
    "mode",
    "action",
    "score",
    "price",
    "lot",
    "sl_pips",
    "tp_pips",
    "max_layer",
    "reasons",
]

TRADE_COLUMNS = [
    "timestamp",
    "symbol",
    "mode",
    "action",
    "order_ticket",
    "retcode",
    "price",
    "sl",
    "tp",
    "lot",
    "comment",
    "message",
]

POSITION_COLUMNS = [
    "timestamp",
    "symbol",
    "ticket",
    "type",
    "volume",
    "price_open",
    "price_current",
    "sl",
    "tp",
    "profit",
    "swap",
    "magic",
    "comment",
]

PERFORMANCE_COLUMNS = [
    "timestamp",
    "symbol",
    "days",
    "closed_trades",
    "wins",
    "losses",
    "breakeven",
    "win_rate",
    "total_profit",
    "account_balance",
    "account_equity",
    "floating_profit",
    "margin",
    "open_positions",
    "magic",
]


def ensure_log_files(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    _ensure_csv_header(logs_dir / "signals.csv", SIGNAL_COLUMNS)
    _ensure_csv_header(logs_dir / "trades.csv", TRADE_COLUMNS)
    _ensure_csv_header(logs_dir / "positions.csv", POSITION_COLUMNS)
    _ensure_csv_header(logs_dir / "performance.csv", PERFORMANCE_COLUMNS)


def _ensure_csv_header(path: Path, columns: List[str]) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()


def _append_row(path: Path, columns: List[str], row: Dict[str, Any]) -> None:
    _ensure_csv_header(path, columns)
    clean_row = {column: row.get(column, "") for column in columns}
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writerow(clean_row)


def _format_reasons(reasons: Iterable[str]) -> str:
    return " | ".join(str(reason) for reason in reasons)


def log_signal(
    logs_dir: Path,
    symbol: str,
    mode: str,
    action: str,
    score: int,
    price: Any,
    risk_plan: Dict[str, Any],
    reasons: Iterable[str],
) -> None:
    ensure_log_files(logs_dir)
    _append_row(
        logs_dir / "signals.csv",
        SIGNAL_COLUMNS,
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "mode": mode,
            "action": action,
            "score": score,
            "price": price,
            "lot": risk_plan.get("lot"),
            "sl_pips": risk_plan.get("sl_pips"),
            "tp_pips": risk_plan.get("tp_pips"),
            "max_layer": risk_plan.get("max_layer"),
            "reasons": _format_reasons(reasons),
        },
    )


def log_trade(
    logs_dir: Path,
    symbol: str,
    mode: str,
    action: str,
    trade_result: Dict[str, Any],
) -> None:
    ensure_log_files(logs_dir)
    _append_row(
        logs_dir / "trades.csv",
        TRADE_COLUMNS,
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "mode": mode,
            "action": action,
            "order_ticket": trade_result.get("order_ticket"),
            "retcode": trade_result.get("retcode"),
            "price": trade_result.get("price"),
            "sl": trade_result.get("sl"),
            "tp": trade_result.get("tp"),
            "lot": trade_result.get("lot"),
            "comment": trade_result.get("comment"),
            "message": trade_result.get("message"),
        },
    )


def log_positions(logs_dir: Path, position_rows: Iterable[Dict[str, Any]]) -> None:
    ensure_log_files(logs_dir)
    for row in position_rows:
        _append_row(logs_dir / "positions.csv", POSITION_COLUMNS, row)


def log_performance(logs_dir: Path, summary: Dict[str, Any]) -> None:
    ensure_log_files(logs_dir)
    _append_row(logs_dir / "performance.csv", PERFORMANCE_COLUMNS, summary)
