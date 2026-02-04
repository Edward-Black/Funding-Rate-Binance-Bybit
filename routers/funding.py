"""
Funding rate API. Returns cached data; background task refreshes every 15s.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

import httpx
import time

import app_state
from services.exchange_fetcher import fetch_all, fetch_all_funding_history

router = APIRouter(prefix="/api", tags=["funding"])

_FETCH_TTL_MS = 15_000


def _normalize_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    # Разрешаем короткий тикер: ZIL -> ZILUSDT
    if s and "-" not in s and not s.endswith("USDT"):
        s = s + "USDT"
    return s


@router.get("/funding")
async def funding(symbol: str = Query("BTCUSDT", description="Futures pair, uppercase Latin e.g. BTCUSDT")):
    """Return funding rate, next funding time (ms), and interval for Binance, Bybit, OKX."""
    symbol = _normalize_symbol(symbol)
    if not symbol or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in symbol):
        return {"error": "Invalid symbol: only uppercase Latin letters, digits, hyphen"}

    app_state.set_requested_symbol(symbol)

    now_ms = int(time.time() * 1000)
    # If we have fresh cache, return immediately; otherwise fetch on-demand (no 30s wait)
    last_ms = app_state.get_last_fetch_ms(symbol)
    if app_state.has_cached(symbol) and (int(now_ms) - last_ms) < _FETCH_TTL_MS:
        return app_state.get_cached_funding(symbol)

    async with httpx.AsyncClient() as client:
        data = await fetch_all(symbol, client)
    app_state.set_funding_cache(symbol, data)
    return data


@router.get("/funding-history")
async def funding_history(symbol: str = Query("BTCUSDT", description="Futures pair, e.g. BTCUSDT")):
    """Return funding rate history for Binance, Bybit, OKX. Each value: list of {fundingTime (ms), fundingRate}."""
    symbol = _normalize_symbol(symbol)
    if not symbol or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in symbol):
        return {"error": "Invalid symbol"}
    async with httpx.AsyncClient() as client:
        data = await fetch_all_funding_history(symbol, client)
    return data
