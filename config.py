# config.py
import os
import sys

API_HOST = os.environ.get("FUNDING_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("FUNDING_API_PORT", "8765"))
REFRESH_INTERVAL_SEC = 15
DEFAULT_SYMBOL = "BTCUSDT"
# При запуске из .exe (PyInstaller) — папка data рядом с exe
if getattr(sys, "frozen", False):
    _base_dir = os.path.dirname(sys.executable)
else:
    _base_dir = os.path.dirname(os.path.abspath(__file__))
PARQUET_DIR = os.path.join(_base_dir, "data")
FUNDING_INTERVAL_HOURS = 8  # для очистки Parquet
