"""REST polling으로 WebSocket을 대체.

한국 IP / Surfshark Tokyo 같이 fstream WS가 차단된 환경에서도 봇이 동작하도록.
공식 binance-futures-connector(UMFutures REST 클라이언트) 사용 — 재시도/에러 처리 내장.

설계:
  - 매 1분: 모든 심볼의 1m kline (limit=2) — WS의 kline_1m stream 대체
  - 매 5분: 모든 심볼의 1d kline (limit=2) — WS의 kline_1d stream 대체

Rate limit:
  - klines weight=5 (limit≤100), Binance Futures 한도 2400/min/IP
  - 150 symbols × weight 5 / min = 750 (1m) + 150 (1d/5min) = 900 weight/min ≈ 37%
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from binance.um_futures import UMFutures
from binance.error import ClientError

log = logging.getLogger(__name__)

OnMessage = Callable[[dict], Awaitable[None]]


def kline_to_msg(symbol: str, interval: str, k: list, server_now_ms: int) -> dict:
    """REST kline list → WebSocket kline payload-호환 dict.

    Binance kline 형식 (12개 필드):
      [open_time, open, high, low, close, volume, close_time,
       quote_volume, trades, taker_buy_vol, taker_buy_quote_vol, ignore]
    """
    open_time = int(k[0])
    close_time = int(k[6])
    is_final = close_time < server_now_ms
    return {
        "data": {
            "k": {
                "s": symbol,
                "i": interval,
                "t": open_time,
                "T": close_time,
                "o": k[1],
                "h": k[2],
                "l": k[3],
                "c": k[4],
                "v": k[5],
                "x": is_final,
            }
        }
    }


class BinancePoller:
    def __init__(self, base_url: str | None = None):
        self.client = UMFutures(base_url=base_url) if base_url else UMFutures()

    def server_now_ms(self) -> int:
        try:
            return int(self.client.time()["serverTime"])
        except Exception:
            return int(time.time() * 1000)

    async def _poll_one(self, sym: str, interval: str, limit: int,
                         on_message: OnMessage, server_now: int) -> None:
        loop = asyncio.get_event_loop()
        try:
            klines = await loop.run_in_executor(
                None,
                lambda: self.client.klines(symbol=sym, interval=interval, limit=limit),
            )
            for k in klines:
                await on_message(kline_to_msg(sym, interval, k, server_now))
        except ClientError as e:
            log.warning("polling %s %s: ClientError %s", sym, interval, e)
        except Exception as e:
            log.warning("polling %s %s: %s", sym, interval, e)

    async def poll_loop(self, symbols: list[str], on_message: OnMessage,
                         minute_interval: int = 60,
                         daily_every_n_cycles: int = 5) -> None:
        cycle = 0
        log.info("REST polling 시작: %d 심볼, 1m=%ds, 1d every %d cycles",
                 len(symbols), minute_interval, daily_every_n_cycles)
        while True:
            t0 = time.time()
            server_now = self.server_now_ms()

            # 1m polling (매 사이클)
            for sym in symbols:
                await self._poll_one(sym, "1m", 2, on_message, server_now)
                await asyncio.sleep(0.03)  # rate limit 분산

            # 1d polling (매 N 사이클)
            if cycle % daily_every_n_cycles == 0:
                for sym in symbols:
                    await self._poll_one(sym, "1d", 2, on_message, server_now)
                    await asyncio.sleep(0.03)

            cycle += 1
            elapsed = time.time() - t0
            sleep_for = max(1.0, minute_interval - elapsed)
            log.info("polling cycle #%d done (%.1fs, next in %.0fs)",
                     cycle, elapsed, sleep_for)
            await asyncio.sleep(sleep_for)
