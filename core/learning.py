"""Learning journal and local statistics for strategy improvement.

This is not an external AI API. It stores signals, zones, and outcomes in
SQLite so the bot can later evaluate which SBR/RBS setups actually work.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def resolve_db_path(config: Dict[str, Any], base_dir: Path) -> Path:
    learning_config = config.get("learning", {}) or {}
    raw_path = str(learning_config.get("db_path", "data/learning.sqlite"))
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    return path


def learning_enabled(config: Dict[str, Any]) -> bool:
    return bool((config.get("learning", {}) or {}).get("enabled", True))


def ensure_learning_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                symbol TEXT NOT NULL,
                mode TEXT NOT NULL,
                entry_time TEXT,
                action TEXT NOT NULL,
                candidate_action TEXT,
                score INTEGER,
                price REAL,
                zone_type TEXT,
                zone_source TEXT,
                zone_confluence INTEGER,
                zone_validation TEXT,
                fvg_json TEXT,
                zone_direction TEXT,
                zone_level REAL,
                zone_distance REAL,
                zone_tolerance REAL,
                zone_quality_score INTEGER,
                zone_quality_grade TEXT,
                lot REAL,
                sl_pips INTEGER,
                tp_pips INTEGER,
                sl_price REAL,
                tp_price REAL,
                reasons_json TEXT,
                news_json TEXT,
                outcome TEXT,
                outcome_pips REAL,
                outcome_profit REAL,
                order_ticket TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS zone_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                entry_time TEXT,
                strategy_version TEXT,
                source_key TEXT,
                zone_type TEXT NOT NULL,
                zone_direction TEXT,
                score INTEGER,
                result TEXT NOT NULL,
                pips REAL,
                profit REAL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_zone_outcomes_lookup ON zone_outcomes(symbol, action, zone_type)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal_journal_lookup ON signal_journal(symbol, action, zone_type)"
        )
        signal_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(signal_journal)").fetchall()
        }
        for column_name, column_type in (
            ("zone_source", "TEXT"),
            ("zone_confluence", "INTEGER"),
            ("zone_validation", "TEXT"),
            ("fvg_json", "TEXT"),
            ("zone_quality_score", "INTEGER"),
            ("zone_quality_grade", "TEXT"),
        ):
            if column_name not in signal_columns:
                connection.execute(f"ALTER TABLE signal_journal ADD COLUMN {column_name} {column_type}")

        outcome_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(zone_outcomes)").fetchall()
        }
        for column_name, column_type in (
            ("entry_time", "TEXT"),
            ("strategy_version", "TEXT"),
            ("source_key", "TEXT"),
        ):
            if column_name not in outcome_columns:
                connection.execute(f"ALTER TABLE zone_outcomes ADD COLUMN {column_name} {column_type}")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_zone_outcomes_source_key "
            "ON zone_outcomes(source_key) WHERE source_key IS NOT NULL"
        )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, default=str)


def record_signal(
    db_path: Path,
    *,
    source: str,
    symbol: str,
    mode: str,
    entry_time: str,
    decision: Dict[str, Any],
    structure_result: Dict[str, Any],
    risk_plan: Dict[str, Any],
    news_context: Dict[str, Any],
) -> int:
    ensure_learning_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO signal_journal (
                timestamp, source, symbol, mode, entry_time, action, candidate_action,
                score, price, zone_type, zone_direction, zone_level, zone_distance,
                zone_source, zone_confluence, zone_validation, fvg_json, zone_tolerance,
                zone_quality_score, zone_quality_grade,
                lot, sl_pips, tp_pips, sl_price, tp_price,
                reasons_json, news_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                source,
                symbol,
                mode,
                entry_time,
                decision.get("action", "SKIP"),
                decision.get("candidate_action"),
                decision.get("score"),
                decision.get("last_price"),
                structure_result.get("zone_type"),
                structure_result.get("zone_direction"),
                structure_result.get("zone_level"),
                structure_result.get("zone_distance"),
                structure_result.get("zone_source"),
                1 if structure_result.get("zone_confluence") else 0,
                structure_result.get("zone_validation"),
                _json(structure_result.get("fvg")),
                structure_result.get("zone_tolerance"),
                structure_result.get("zone_quality_score"),
                structure_result.get("zone_quality_grade"),
                risk_plan.get("lot"),
                risk_plan.get("sl_pips"),
                risk_plan.get("tp_pips"),
                risk_plan.get("estimated_sl_price"),
                risk_plan.get("estimated_tp_price"),
                _json(decision.get("reasons", [])),
                _json(news_context),
                now,
            ),
        )
        return int(cursor.lastrowid)


def record_zone_outcome(
    db_path: Path,
    *,
    symbol: str,
    action: str,
    zone_type: str,
    zone_direction: str,
    score: int,
    result: str,
    pips: float,
    profit: Optional[float] = None,
    source: str = "backtest",
    entry_time: Optional[str] = None,
    strategy_version: Optional[str] = None,
) -> None:
    if zone_type in {"", "NONE", None}:
        return
    ensure_learning_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    clean_entry_time = str(entry_time or "")
    clean_strategy_version = str(strategy_version or "default")
    source_key = None
    if clean_entry_time:
        source_key = f"{source}:{clean_strategy_version}:{symbol}:{action}:{zone_type}:{clean_entry_time}"

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO zone_outcomes (
                timestamp, symbol, action, entry_time, strategy_version, source_key, zone_type, zone_direction,
                score, result, pips, profit, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                symbol,
                action,
                clean_entry_time,
                clean_strategy_version,
                source_key,
                zone_type,
                zone_direction,
                score,
                result,
                pips,
                profit,
                source,
                now,
            ),
        )


def zone_stats(db_path: Path, symbol: str, action: str, zone_type: str) -> Dict[str, Any]:
    ensure_learning_db(db_path)
    if zone_type in {"", "NONE", None}:
        return {"samples": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_pips": 0.0}

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT result, pips
            FROM zone_outcomes
            WHERE symbol = ? AND action = ? AND zone_type = ?
            """,
            (symbol, action, zone_type),
        ).fetchall()

    samples = len(rows)
    wins = sum(1 for result, _ in rows if str(result).upper() == "TP")
    losses = sum(1 for result, _ in rows if str(result).upper() == "SL")
    avg_pips = round(sum(float(pips or 0.0) for _, pips in rows) / samples, 2) if samples else 0.0
    win_rate = round((wins / samples) * 100, 2) if samples else 0.0
    return {
        "samples": samples,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_pips": avg_pips,
    }


def learned_zone_bias(
    db_path: Path,
    config: Dict[str, Any],
    symbol: str,
    action: str,
    zone_type: str,
) -> Dict[str, Any]:
    learning_config = config.get("learning", {}) or {}
    min_samples = int(learning_config.get("min_samples_for_zone_bias", 20))
    max_points = int(learning_config.get("max_zone_bias_points", 10))
    stats = zone_stats(db_path, symbol, action, zone_type)

    if stats["samples"] < min_samples:
        return {"points": 0, "stats": stats, "reason": "Not enough learned samples for zone bias."}

    win_rate = float(stats["win_rate"])
    avg_pips = float(stats["avg_pips"])
    points = 0
    if win_rate >= 55 and avg_pips > 0:
        points = max_points
    elif win_rate >= 50 and avg_pips >= 0:
        points = max(1, max_points // 2)
    elif win_rate <= 40 and avg_pips < 0:
        points = -max_points
    elif win_rate <= 45 and avg_pips <= 0:
        points = -max(1, max_points // 2)

    reason = (
        f"Learned zone stats {zone_type}/{action}: "
        f"samples={stats['samples']}, win_rate={stats['win_rate']}%, avg_pips={stats['avg_pips']}."
    )
    return {"points": points, "stats": stats, "reason": reason}


def import_backtest_csv(db_path: Path, csv_rows: Iterable[Dict[str, Any]], symbol: str) -> int:
    count = 0
    for row in csv_rows:
        action = str(row.get("action", "")).upper()
        if action not in {"BUY", "SELL"}:
            continue
        reasons = str(row.get("reasons", ""))
        zone_type = "NONE"
        for candidate in ("RBS", "SBR", "SNR_SUPPORT", "SNR_RESISTANCE"):
            if candidate in reasons:
                zone_type = candidate
                break
        if zone_type == "NONE":
            continue
        record_zone_outcome(
            db_path,
            symbol=str(row.get("symbol", symbol) or symbol),
            action=action,
            zone_type=zone_type,
            zone_direction="BUY" if zone_type in {"RBS", "SNR_SUPPORT"} else "SELL",
            score=int(float(row.get("score", 0) or 0)),
            result=str(row.get("result", "")),
            pips=float(row.get("pips", 0) or 0),
            source="backtest_csv",
        )
        count += 1
    return count
