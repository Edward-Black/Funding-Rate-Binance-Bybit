"""
Parquet cache for funding data. Cleans up each funding period to avoid history buildup.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from config import PARQUET_DIR

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# One file per period; we overwrite to keep only current period
CACHE_FILE = "funding_cache.parquet"


def _path() -> Path:
    Path(PARQUET_DIR).mkdir(parents=True, exist_ok=True)
    return Path(PARQUET_DIR) / CACHE_FILE


def write_row(exchange: str, symbol: str, funding_rate: str, next_funding_time_ms: int, interval: str) -> None:
    if not HAS_PANDAS:
        return
    path = _path()
    row = {
        "ts": int(time.time() * 1000),
        "exchange": exchange,
        "symbol": symbol,
        "fundingRate": funding_rate,
        "nextFundingTimeMs": next_funding_time_ms,
        "interval": interval,
    }
    df = pd.DataFrame([row])
    if path.exists():
        try:
            existing = pd.read_parquet(path)
            # Keep only rows from current 8h window (next funding in future or recent)
            now_ms = int(time.time() * 1000)
            window_ms = 8 * 3600 * 1000
            existing = existing[
                (existing["nextFundingTimeMs"] > now_ms - window_ms)
                | (existing["ts"] > now_ms - window_ms)
            ]
            df = pd.concat([existing, df], ignore_index=True)
        except Exception:
            pass
    df.to_parquet(path, index=False)


def cleanup_old() -> None:
    """Remove parquet file each funding period so we don't accumulate history."""
    path = _path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
