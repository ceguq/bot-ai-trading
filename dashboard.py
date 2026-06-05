from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd
import streamlit as st
import yaml


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
SIGNALS_PATH = BASE_DIR / "logs" / "signals.csv"
TRADES_PATH = BASE_DIR / "logs" / "trades.csv"
POSITIONS_PATH = BASE_DIR / "logs" / "positions.csv"
PERFORMANCE_PATH = BASE_DIR / "logs" / "performance.csv"


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def value(config: Dict[str, Any], section: str, key: str, default: Any = "-") -> Any:
    return (config.get(section, {}) or {}).get(key, default)


st.set_page_config(page_title="AI Demo Trading Bot", layout="wide")

st.title("AI Trading Bot XAUUSD")
st.caption("Demo-only MetaTrader 5 signal and execution monitor")

if st.button("Refresh"):
    st.rerun()

config = load_config()
signals = load_csv(SIGNALS_PATH)
trades = load_csv(TRADES_PATH)
positions = load_csv(POSITIONS_PATH)
performance = load_csv(PERFORMANCE_PATH)

mode_config = config.get("mode", {}) or {}
risk_config = config.get("risk", {}) or {}
trade_config = config.get("trade", {}) or {}
strategy_config = config.get("strategy", {}) or {}
news_config = config.get("news", {}) or {}

st.warning("Order execution only works in demo_trade mode and demo account.")
st.error("Live trading is disabled.")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Mode", mode_config.get("trading_mode", "signal_only"))
col2.metric("Symbol", config.get("symbol", "XAUUSD"))
col3.metric("Allow Demo Order", str(mode_config.get("allow_demo_order", False)))
col4.metric("Allow Live Order", str(mode_config.get("allow_live_order", False)))

col5, col6, col7, col8 = st.columns(4)
col5.metric("Lot", risk_config.get("lot", "-"))
col6.metric("SL", f"{risk_config.get('sl_pips', '-')} pips")
col7.metric("TP", f"{risk_config.get('tp_pips', '-')} pips")
col8.metric("Max Layer", risk_config.get("max_layer", "-"))

st.divider()

perf_cols = st.columns(5)
if performance.empty:
    perf_cols[0].metric("Closed", 0)
    perf_cols[1].metric("Wins", 0)
    perf_cols[2].metric("Losses", 0)
    perf_cols[3].metric("Win Rate", "0%")
    perf_cols[4].metric("Balance", "-")
else:
    perf_row = performance.iloc[-1]
    perf_cols[0].metric("Closed", perf_row.get("closed_trades", 0))
    perf_cols[1].metric("Wins", perf_row.get("wins", 0))
    perf_cols[2].metric("Losses", perf_row.get("losses", 0))
    perf_cols[3].metric("Win Rate", f"{perf_row.get('win_rate', 0)}%")
    perf_cols[4].metric("Balance", perf_row.get("account_balance", "-"))

st.divider()

latest_signal = signals.tail(1) if not signals.empty else pd.DataFrame()
left, right = st.columns([1, 2])

with left:
    st.subheader("Sinyal Terakhir")
    if latest_signal.empty:
        st.info("Belum ada sinyal.")
    else:
        row = latest_signal.iloc[-1]
        st.metric("Action", row.get("action", "-"))
        st.metric("Score", row.get("score", "-"))
        st.metric("Price", row.get("price", "-"))

with right:
    st.subheader("Alasan Sinyal")
    if latest_signal.empty:
        st.info("Belum ada alasan sinyal.")
    else:
        reasons = str(latest_signal.iloc[-1].get("reasons", "")).split(" | ")
        for reason in [item for item in reasons if item and item != "nan"]:
            st.write(f"- {reason}")

st.divider()

st.subheader("Konfigurasi Trading")
config_cols = st.columns(4)
config_cols[0].write(f"Allow BUY: `{trade_config.get('allow_buy', True)}`")
config_cols[1].write(f"Allow SELL: `{trade_config.get('allow_sell', True)}`")
config_cols[2].write(f"Layering: `{trade_config.get('allow_layering', False)}`")
config_cols[3].write(f"Move SL to BE: `{trade_config.get('allow_move_to_be', True)}`")

st.subheader("Strategi")
strategy_cols = st.columns(4)
strategy_cols[0].write(f"SBR/RBS: `{strategy_config.get('use_sbr_rbs', True)}`")
strategy_cols[1].write(f"Require Zone: `{strategy_config.get('require_zone_for_entry', False)}`")
strategy_cols[2].write(f"Zone Tolerance: `{strategy_config.get('zone_tolerance_percent', 0.2)}%`")
strategy_cols[3].write(f"News Filter: `{news_config.get('enabled', False)}`")

st.subheader("Posisi Bot")
if positions.empty:
    st.info("logs/positions.csv masih kosong.")
else:
    st.dataframe(positions.tail(50), use_container_width=True)

st.subheader("Log Sinyal")
if signals.empty:
    st.info("logs/signals.csv masih kosong.")
else:
    st.dataframe(signals.tail(100), use_container_width=True)

st.subheader("Order Demo")
if trades.empty:
    st.info("logs/trades.csv masih kosong.")
else:
    st.dataframe(trades.tail(100), use_container_width=True)
