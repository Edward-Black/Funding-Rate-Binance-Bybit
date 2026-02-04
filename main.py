"""
FastAPI app: funding rate API, refresh every 30s, optional Parquet cache.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import FastAPI

from config import REFRESH_INTERVAL_SEC
from routers.funding import router as funding_router
from services.exchange_fetcher import fetch_all

import app_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Funding Rate API")
app.include_router(funding_router)

_http_client: httpx.AsyncClient | None = None


async def _refresh_loop() -> None:
    global _http_client
    _http_client = httpx.AsyncClient()
    try:
        while True:
            try:
                symbol = app_state.get_cache_symbol()
                data = await fetch_all(symbol, _http_client)
                app_state.set_funding_cache(symbol, data)
                try:
                    from storage.parquet_cache import write_row
                    for name, row in data.items():
                        if "error" not in row and row.get("nextFundingTimeMs"):
                            write_row(
                                name,
                                row.get("symbol", symbol),
                                row.get("fundingRate", ""),
                                row.get("nextFundingTimeMs", 0),
                                row.get("interval", ""),
                            )
                except Exception as e:
                    logger.debug("Parquet write skip: %s", e)
            except Exception as e:
                logger.warning("Refresh failed: %s", e)
            await asyncio.sleep(REFRESH_INTERVAL_SEC)
    finally:
        await _http_client.aclose()


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_refresh_loop())


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Funding Rate API", "docs": "/docs", "api": "/api/funding?symbol=BTCUSDT"}


if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT
    uvicorn.run(app, host=API_HOST, port=API_PORT)
