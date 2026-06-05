from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict

import yaml

from core.learning import ensure_learning_db, resolve_db_path, zone_stats


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"


def load_config() -> Dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def main() -> None:
    config = load_config()
    symbol = str(config.get("symbol", "XAUUSD"))
    db_path = resolve_db_path(config, BASE_DIR)
    ensure_learning_db(db_path)

    print(f"Learning DB: {db_path}")
    with sqlite3.connect(db_path) as connection:
        signal_count = connection.execute("SELECT COUNT(*) FROM signal_journal").fetchone()[0]
        outcome_count = connection.execute("SELECT COUNT(*) FROM zone_outcomes").fetchone()[0]
        print(f"Signal journal rows: {signal_count}")
        print(f"Zone outcome rows: {outcome_count}")

    learning_config = config.get("learning", {}) or {}
    hard_block_enabled = bool(learning_config.get("hard_block_bad_zones", True))
    hard_block_min_samples = int(learning_config.get("hard_block_min_samples", 50))
    hard_block_max_win_rate = float(learning_config.get("hard_block_max_win_rate", 30))
    hard_block_require_negative = bool(learning_config.get("hard_block_require_negative_avg_pips", True))

    for zone_type in ("RBS", "SBR", "SNR_SUPPORT", "SNR_RESISTANCE"):
        for action in ("BUY", "SELL"):
            stats = zone_stats(db_path, symbol, action, zone_type)
            if stats["samples"]:
                blocked = (
                    hard_block_enabled
                    and int(stats["samples"]) >= hard_block_min_samples
                    and float(stats["win_rate"]) <= hard_block_max_win_rate
                    and (float(stats["avg_pips"]) < 0 if hard_block_require_negative else True)
                )
                status = "BLOCKED" if blocked else "ACTIVE"
                print(
                    f"{zone_type}/{action}: "
                    f"status={status}, "
                    f"samples={stats['samples']}, "
                    f"wins={stats['wins']}, "
                    f"losses={stats['losses']}, "
                    f"win_rate={stats['win_rate']}%, "
                    f"avg_pips={stats['avg_pips']}"
                )


if __name__ == "__main__":
    main()
