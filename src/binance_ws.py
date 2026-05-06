import asyncio
import json
import logging
from typing import Awaitable, Callable

import websockets

from src.config import CFG

log = logging.getLogger(__name__)

OnMessage = Callable[[dict], Awaitable[None]]


def build_streams(symbols: list[str]) -> list[str]:
    """심볼당 kline_1d + kline_1m 두 stream."""
    out: list[str] = []
    for s in symbols:
        s_low = s.lower()
        out.append(f"{s_low}@kline_1d")
        out.append(f"{s_low}@kline_1m")
    return out


def chunks(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def _run_one_stream(streams: list[str], on_message: OnMessage) -> None:
    url = f"{CFG.WS_BASE}/stream?streams={'/'.join(streams)}"
    while True:
        try:
            async with websockets.connect(url, ping_interval=180, ping_timeout=600,
                                          max_size=2**22) as ws:
                log.info("WS connected: %d streams", len(streams))
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        await on_message(msg)
                    except Exception as e:
                        log.exception("on_message 처리 실패: %s", e)
        except (websockets.ConnectionClosed, OSError) as e:
            log.warning("WS 연결 끊김: %s — 5초 후 재연결", e)
            await asyncio.sleep(5)
        except Exception as e:
            log.exception("WS unexpected: %s", e)
            await asyncio.sleep(5)


async def stream_klines(symbols: list[str], on_message: OnMessage,
                         streams_per_conn: int = 100) -> None:
    """N개 심볼을 streams_per_conn 단위로 묶어 멀티 connection."""
    all_streams = build_streams(symbols)
    groups = chunks(all_streams, streams_per_conn)
    log.info("총 %d streams를 %d connection으로 분할", len(all_streams), len(groups))
    await asyncio.gather(*[_run_one_stream(g, on_message) for g in groups])
