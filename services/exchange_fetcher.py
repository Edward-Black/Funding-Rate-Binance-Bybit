"""
Fetch funding rate data from Binance, Bybit, OKX.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BINANCE_PREMIUM = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_FUNDING_INFO = "https://fapi.binance.com/fapi/v1/fundingInfo"
BINANCE_FUNDING_RATE_HISTORY = "https://fapi.binance.com/fapi/v1/fundingRate"
BYBIT_URL = "https://api.bybit.com/v5/market/tickers"
BYBIT_FUNDING_HISTORY = "https://api.bybit.com/v5/market/funding/history"
OKX_URL = "https://www.okx.com/api/v5/public/funding-rate"
OKX_FUNDING_HISTORY = "https://www.okx.com/api/v5/public/funding-rate-history"


def _symbol_okx(symbol: str) -> str:
    """Convert BTCUSDT -> BTC-USDT-SWAP for OKX."""
    if "-" in symbol:
        base, quote = symbol.split("-", 1)
        return f"{base}-{quote}-SWAP"
    if len(symbol) >= 6 and symbol.endswith("USDT"):
        base = symbol[:-4]
        return f"{base}-USDT-SWAP"
    return f"{symbol}-SWAP"


async def _binance_interval(symbol: str, client: httpx.AsyncClient) -> str:
    """Получить интервал фандинга по символу (fundingInfo). По умолчанию 8h."""
    try:
        r = await client.get(BINANCE_FUNDING_INFO, timeout=10.0)
        r.raise_for_status()
        lst = r.json()
        if isinstance(lst, list):
            for x in lst:
                if x.get("symbol") == symbol.upper():
                    h = x.get("fundingIntervalHours", "8")
                    return f"{h}h"
    except Exception:
        pass
    return "8h"


async def fetch_binance(symbol: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch funding from Binance. Symbol: BTCUSDT."""
    try:
        r = await client.get(BINANCE_PREMIUM, params={"symbol": symbol.upper()}, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            data = next((x for x in data if x.get("symbol") == symbol.upper()), data[0] if data else {})
        next_ts_ms = int(data.get("nextFundingTime", 0))
        interval = await _binance_interval(symbol, client)
        return {
            "exchange": "binance",
            "symbol": data.get("symbol", symbol),
            "fundingRate": str(data.get("lastFundingRate", "")),
            "nextFundingTimeMs": next_ts_ms,
            "interval": interval,
        }
    except Exception as e:
        logger.exception("Binance fetch failed: %s", e)
        return None


async def fetch_bybit(symbol: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch funding from Bybit. Symbol: BTCUSDT."""
    try:
        r = await client.get(
            BYBIT_URL,
            params={"category": "linear", "symbol": symbol.upper()},
            timeout=10.0,
        )
        r.raise_for_status()
        out = r.json()
        if out.get("retCode") != 0:
            return None
        lst = out.get("result", {}).get("list") or []
        if not lst:
            return None
        item = lst[0]
        next_ts = item.get("nextFundingTime") or "0"
        next_ts_ms = int(next_ts) if next_ts else 0
        interval_h = item.get("fundingIntervalHour") or "8"
        return {
            "exchange": "bybit",
            "symbol": item.get("symbol", symbol),
            "fundingRate": str(item.get("fundingRate", "")),
            "nextFundingTimeMs": next_ts_ms,
            "interval": f"{interval_h}h",
        }
    except Exception as e:
        logger.exception("Bybit fetch failed: %s", e)
        return None


def _okx_ts_ms(raw: str) -> int:
    """OKX timestamp: в ответе в миллисекундах; если < 1e12 — считаем секунды."""
    if not raw:
        return 0
    try:
        ts = int(raw)
        if 0 < ts < 1_000_000_000_000:
            return ts * 1000
        return ts
    except (ValueError, TypeError):
        return 0


def _okx_interval_hours(item: dict[str, Any]) -> int:
    """Интервал в часах из разницы nextFundingTime и fundingTime (или prevFundingTime)."""
    try:
        next_ts = _okx_ts_ms(item.get("nextFundingTime") or "0")
        curr_ts = _okx_ts_ms(item.get("fundingTime") or "0")
        if curr_ts > 0 and next_ts > curr_ts:
            h = round((next_ts - curr_ts) / 3600000)
            if 1 <= h <= 24:
                return h
        prev_ts = _okx_ts_ms(item.get("prevFundingTime") or "0")
        if prev_ts > 0 and next_ts > prev_ts:
            h = round((next_ts - prev_ts) / 3600000)
            if 1 <= h <= 24:
                return h
    except (ValueError, TypeError):
        pass
    return 8


async def fetch_okx(symbol: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Fetch funding from OKX. Symbol: BTCUSDT -> instId BTC-USDT-SWAP."""
    inst_id = _symbol_okx(symbol)
    try:
        r = await client.get(
            OKX_URL,
            params={"instId": inst_id},
            timeout=10.0,
        )
        r.raise_for_status()
        out = r.json()
        if out.get("code") != "0":
            return None
        data_list = out.get("data") or []
        if not data_list:
            return None
        item = data_list[0]
        next_ts_ms = _okx_ts_ms(item.get("nextFundingTime") or "0")
        interval_h = _okx_interval_hours(item)
        # На OKX nextFundingTime по факту даёт время + интервал; вычитаем интервал для корректного Time to Next
        interval_ms = interval_h * 3600 * 1000
        if next_ts_ms > interval_ms:
            next_ts_ms -= interval_ms
        return {
            "exchange": "okx",
            "symbol": item.get("instId", inst_id),
            "fundingRate": str(item.get("fundingRate") or item.get("settFundingRate", "")),
            "nextFundingTimeMs": next_ts_ms,
            "interval": f"{interval_h}h",
        }
    except Exception as e:
        logger.exception("OKX fetch failed: %s", e)
        return None


FUNDING_HISTORY_LIMIT = 50


async def fetch_funding_history_binance(symbol: str, client: httpx.AsyncClient, limit: int = FUNDING_HISTORY_LIMIT) -> list[dict[str, Any]]:
    """История фандингов Binance: список {fundingTime (ms), fundingRate}."""
    try:
        r = await client.get(
            BINANCE_FUNDING_RATE_HISTORY,
            params={"symbol": symbol.upper(), "limit": limit},
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return []
        return [{"fundingTime": int(x.get("fundingTime", 0)), "fundingRate": str(x.get("fundingRate", ""))} for x in data]
    except Exception as e:
        logger.debug("Binance funding history failed: %s", e)
        return []


async def fetch_funding_history_bybit(symbol: str, client: httpx.AsyncClient, limit: int = FUNDING_HISTORY_LIMIT) -> list[dict[str, Any]]:
    """История фандингов Bybit: список {fundingTime (ms), fundingRate}."""
    try:
        r = await client.get(
            BYBIT_FUNDING_HISTORY,
            params={"category": "linear", "symbol": symbol.upper(), "limit": limit},
            timeout=10.0,
        )
        r.raise_for_status()
        out = r.json()
        if out.get("retCode") != 0:
            return []
        lst = out.get("result", {}).get("list") or []
        result = []
        for x in lst:
            ft = x.get("fundingRateTimestamp") or x.get("fundingRateTime") or "0"
            ts_ms = int(ft) if ft else 0
            if 0 < ts_ms < 1_000_000_000_000:
                ts_ms *= 1000
            result.append({"fundingTime": ts_ms, "fundingRate": str(x.get("fundingRate", ""))})
        return result
    except Exception as e:
        logger.debug("Bybit funding history failed: %s", e)
        return []


async def fetch_funding_history_okx(symbol: str, client: httpx.AsyncClient, limit: int = FUNDING_HISTORY_LIMIT) -> list[dict[str, Any]]:
    """История фандингов OKX: список {fundingTime (ms), fundingRate}."""
    inst_id = _symbol_okx(symbol)
    try:
        r = await client.get(
            OKX_FUNDING_HISTORY,
            params={"instId": inst_id, "limit": str(limit)},
            timeout=10.0,
        )
        r.raise_for_status()
        out = r.json()
        if out.get("code") != "0":
            return []
        data_list = out.get("data") or []
        result = []
        for x in data_list:
            ts_ms = _okx_ts_ms(x.get("fundingTime") or "0")
            result.append({"fundingTime": ts_ms, "fundingRate": str(x.get("fundingRate", ""))})
        return result
    except Exception as e:
        logger.debug("OKX funding history failed: %s", e)
        return []


async def fetch_all_funding_history(symbol: str, client: httpx.AsyncClient) -> dict[str, list[dict[str, Any]]]:
    """История фандингов по всем биржам. Ключи: binance, bybit, okx."""
    import asyncio
    symbol = symbol.upper().replace(" ", "")
    tasks = [
        fetch_funding_history_binance(symbol, client),
        fetch_funding_history_bybit(symbol, client),
        fetch_funding_history_okx(symbol, client),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = {}
    for i, name in enumerate(["binance", "bybit", "okx"]):
        r = results[i]
        if isinstance(r, Exception):
            logger.warning("%s history failed: %s", name, r)
            out[name] = []
        elif isinstance(r, list):
            out[name] = r
        else:
            out[name] = []
    return out


async def fetch_all(symbol: str, client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    """Fetch from all three exchanges. Symbol in uppercase Latin, e.g. BTCUSDT."""
    import asyncio

    symbol = symbol.upper().replace(" ", "")
    tasks = [
        fetch_binance(symbol, client),
        fetch_bybit(symbol, client),
        fetch_okx(symbol, client),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = {}
    for i, name in enumerate(["binance", "bybit", "okx"]):
        r = results[i]
        if isinstance(r, Exception):
            logger.warning("%s failed: %s", name, r)
            out[name] = {"exchange": name, "error": str(r), "fundingRate": "", "nextFundingTimeMs": 0, "interval": ""}
        elif r:
            out[name] = r
        else:
            out[name] = {"exchange": name, "error": "No data", "fundingRate": "", "nextFundingTimeMs": 0, "interval": ""}
    return out
