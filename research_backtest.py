from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from backtest import load_config, run_backtest
from core.mt5_client import MT5Client


BASE_DIR = Path(__file__).resolve().parent
REPORT_PATH = BASE_DIR / "logs" / "research_backtest.csv"

REPORT_COLUMNS = [
    "timestamp",
    "variant",
    "symbol",
    "bars",
    "trades",
    "wins",
    "losses",
    "skipped",
    "win_rate",
    "total_pips",
]


def deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_update(result[key], value)
        else:
            result[key] = value
    return result


def variants() -> Iterable[tuple[str, Dict[str, Any]]]:
    return (
        ("baseline", {}),
        ("m15_quality_95", {"strategy": {"min_m15_zone_quality_for_entry": 95}}),
        ("no_m15_primary", {"strategy": {"use_m15_zone_as_execution_reference": False}}),
        ("m15_tp30_sl50", {"strategy": {"m15_zone_tp_pips": 30, "m15_zone_sl_pips": 50}}),
        ("min_score_90", {"ai": {"min_score_entry": 90}}),
    )


def append_report(row: Dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not REPORT_PATH.exists() or REPORT_PATH.stat().st_size == 0
    with REPORT_PATH.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=REPORT_COLUMNS)
        if needs_header:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in REPORT_COLUMNS})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run several safe, order-free strategy research backtests.")
    parser.add_argument("--symbol", default=None, help="Override symbol, for example XAUUSD.vx.")
    parser.add_argument("--bars", type=int, default=500, help="Number of M15 bars per variant.")
    parser.add_argument("--variant", default=None, help="Run only one variant name, for example min_score_90.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_config = load_config()
    symbol = args.symbol or str(base_config.get("symbol", "XAUUSD"))

    mt5_client = MT5Client()
    try:
        mt5_client.initialize()
        print(f"Account Type: {mt5_client.get_account_type()}")
        print("Research mode: order execution disabled, learning writes disabled.")
        for name, overrides in variants():
            if args.variant and name != args.variant:
                continue
            config = deep_update(base_config, overrides)
            summary = run_backtest(
                mt5_client,
                config,
                symbol=symbol,
                bars=args.bars,
                write_log=False,
                write_learning=False,
            )
            row = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "variant": name,
                "symbol": symbol,
                **summary,
            }
            append_report(row)
            print(
                f"{name}: trades={summary['trades']}, wins={summary['wins']}, "
                f"losses={summary['losses']}, win_rate={summary['win_rate']}%, "
                f"pips={summary['total_pips']}"
            )
    finally:
        mt5_client.shutdown()


if __name__ == "__main__":
    main()
