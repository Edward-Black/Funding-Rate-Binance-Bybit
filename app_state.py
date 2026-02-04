"""
Общее состояние API: кэш фандинга и символ.
Вынесено в отдельный модуль, чтобы избежать циклического импорта main <-> routers.funding.
"""
from __future__ import annotations

import time
from typing import Any

from config import DEFAULT_SYMBOL

_funding_cache: dict[str, dict[str, dict[str, Any]]] = {}
_cache_symbol: str = DEFAULT_SYMBOL
_last_fetch_ms: dict[str, int] = {}


def set_requested_symbol(symbol: str) -> None:
    """Установить символ для следующего обновления (вызывается из API)."""
    global _cache_symbol
    s = symbol.upper().strip()
    if s and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in s):
        _cache_symbol = s


def get_cached_funding(symbol: str) -> dict[str, Any]:
    """Вернуть кэш фандинга по символу."""
    symbol = symbol.upper().strip()
    if symbol in _funding_cache:
        return _funding_cache[symbol]
    if _funding_cache:
        return _funding_cache.get(_cache_symbol, _funding_cache[next(iter(_funding_cache))])
    return {"binance": {}, "bybit": {}, "okx": {}}


def has_cached(symbol: str) -> bool:
    return symbol.upper().strip() in _funding_cache


def get_last_fetch_ms(symbol: str) -> int:
    return _last_fetch_ms.get(symbol.upper().strip(), 0)


def get_cache_symbol() -> str:
    """Символ, который сейчас обновляется в фоне."""
    return _cache_symbol


def set_funding_cache(symbol: str, data: dict[str, dict[str, Any]]) -> None:
    """Записать результат обновления в кэш (вызывается из main._refresh_loop)."""
    global _funding_cache, _last_fetch_ms
    s = symbol.upper().strip()
    _funding_cache[s] = data
    _last_fetch_ms[s] = int(time.time() * 1000)
