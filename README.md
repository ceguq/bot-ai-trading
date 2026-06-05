# AI Trading Bot XAUUSD Demo Only

Project Python modular untuk bot analisa XAUUSD berbasis MetaTrader 5. Bot ini memiliki dua mode:

- `signal_only`: membaca candle, membuat sinyal BUY / SELL / SKIP, dan menyimpan log. Tidak membuka order.
- `demo_trade`: hanya boleh membuka dan memodifikasi order pada akun MT5 yang terverifikasi DEMO.

Tidak ada mode `live_trade` di project ini.

## Peringatan

Bot ini hanya untuk akun demo. Live trading dinonaktifkan.

Jika akun REAL terdeteksi, eksekusi harus diblokir dan bot berhenti.

Jangan gunakan akun real sebelum seluruh strategi diuji dan divalidasi.

Saldo demo besar bukan alasan untuk menaikkan lot sembarangan. Tetap gunakan lot kecil untuk menguji logic.

Project ini tidak menyimpan password, tidak melakukan login otomatis dengan password, dan hanya memakai akun yang sudah login di terminal MetaTrader 5.

## Setup

Buka terminal di folder project:

```powershell
cd E:\project\vscode\BOT-AI-TRADING\bot-ai-trading-v1\ai-trading-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Jika memakai CMD:

```bat
.venv\Scripts\activate
```

Pastikan terminal MetaTrader 5 sudah terbuka dan sudah login ke akun DEMO.

## Menjalankan Bot

```powershell
python main.py
```

Default `config.yaml` memakai mode aman:

```yaml
mode:
  trading_mode: "signal_only"
  allow_demo_order: false
  allow_live_order: false
```

Dalam mode ini bot hanya membuat sinyal dan menulis log ke `logs/signals.csv`.

## Menjalankan Dashboard

```powershell
streamlit run dashboard.py
```

Dashboard menampilkan konfigurasi, sinyal terakhir, alasan sinyal, tabel log sinyal, dan tabel order demo.

## Menjalankan Backtest

Backtest tidak membuka order dan tidak mengubah posisi. Script ini mengambil candle dari MT5 lalu mensimulasikan sinyal, SL, dan TP.

Jika symbol default broker bukan `XAUUSD`, jalankan dengan override symbol:

```powershell
python backtest.py --symbol XAUUSD.vx --bars 1000
```

Hasil ditulis ke `logs/backtest.csv`.

## Strategi Saat Ini

Strategi masih rule-based lokal, bukan AI API eksternal.

Filter teknikal utama:

- H4 untuk major trend dan zona pantulan besar
- H1 untuk refined support/resistance/RBS/SBR
- M15 untuk zona respect/execution reference dan trigger eksekusi
- trend H4 dan H1 berbasis MA50
- zona SBR dan RBS dari swing level, body close break, dan FVG
- support/resistance nearest zone
- candle M15
- momentum pendek
- risk reward SL/TP

Config strategi:

```yaml
strategy:
  major_trend_timeframe: "H4"
  major_zone_timeframe: "H4"
  refined_zone_timeframe: "H1"
  execution_timeframe: "M15"
  use_m15_zone_as_execution_reference: true
  use_sbr_rbs: true
  require_body_break_for_sbr_rbs: true
  require_fvg_for_sbr_rbs: true
  break_lookback_candles: 80
  fvg_lookback_candles: 20
  min_break_body_ratio: 1.0
  require_zone_for_entry: false
  zone_tolerance_percent: 0.2
```

Definisi valid yang dipakai:

- SBR valid: support lama ditembus candle body bearish, close di bawah support, muncul bearish FVG setelah break, lalu harga retest ke support lama sebagai resistance.
- RBS valid: resistance lama ditembus candle body bullish, close di atas resistance, muncul bullish FVG setelah break, lalu harga retest ke resistance lama sebagai support.

News filter MT5 sudah disiapkan di `core/news_filter.py`, tetapi default masih off:

```yaml
news:
  enabled: false
  source: "mt5"
```

Catatan: package Python `MetaTrader5` yang terpasang saat ini tidak expose fungsi `calendar_*`, jadi news MT5 belum bisa dibaca langsung dari Python. Modulnya dibuat non-blocking sampai sumber data news yang valid tersedia.

## Learning Journal

Data belajar disimpan di:

```text
data/learning.sqlite
```

Isi utama:

- `signal_journal`: semua sinyal, score, zona, alasan, SL/TP, dan context news.
- `zone_outcomes`: hasil zona dari backtest, misalnya SBR/SELL menang atau kalah.

Lihat ringkasan learning:

```powershell
python learning_report.py
```

Backtest akan menambah sample learning zona:

```powershell
python backtest.py --bars 2000
```

## Mengaktifkan Demo Trade

Ubah `config.yaml` menjadi:

```yaml
mode:
  trading_mode: "demo_trade"
  allow_demo_order: true
  allow_live_order: false
```

Syarat order demo:

- `trading_mode` harus `demo_trade`
- `allow_demo_order` harus `true`
- akun MT5 harus terverifikasi `DEMO`
- `allow_live_order` harus tetap `false`
- SL dan TP harus tersedia dari risk plan
- jumlah posisi bot pada symbol dan magic number belum mencapai `max_layer`

Jika akun MT5 terdeteksi `REAL`, bot menampilkan:

```text
REAL ACCOUNT DETECTED. EXECUTION BLOCKED.
```

Lalu bot berhenti dan tidak membuka order, tidak modify order, tidak close order.

## Struktur

```text
ai-trading-bot/
|-- main.py
|-- backtest.py
|-- learning_report.py
|-- dashboard.py
|-- config.yaml
|-- requirements.txt
|-- README.md
|-- core/
|   |-- __init__.py
|   |-- mt5_client.py
|   |-- market_data.py
|   |-- structure.py
|   |-- ai_filter.py
|   |-- decision.py
|   |-- risk.py
|   |-- executor.py
|   |-- trade_manager.py
|   |-- safety.py
|   `-- logger.py
|-- logs/
|   |-- signals.csv
|   |-- backtest.csv
|   |-- positions.csv
|   |-- performance.csv
|   `-- trades.csv
`-- data/
```

## Catatan Safety Guard

`core/safety.py` adalah gerbang utama. `executor.py` dan `trade_manager.py` memanggil safety check lagi sebelum order atau modify SL.

`executor.py` hanya memiliki fungsi `execute_demo_order`. Tidak ada fungsi live order.

`trade_manager.py` hanya membaca posisi dengan symbol dan `magic_number` milik bot. Fitur break-even juga hanya menyentuh posisi dengan `magic_number` bot dan hanya pada akun demo.
