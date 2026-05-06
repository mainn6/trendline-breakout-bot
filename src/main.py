import asyncio
import logging
from collections import defaultdict, deque

from src.alert_db import AlertDB
from src.binance_rest import BinanceRest
from src.binance_ws import stream_klines
from src.config import CFG
from src.models import StageState
from src.state_machine import StateMachine
from src.telegram_notifier import send_alert
from src.trendline_manager import TrendlineManager


log = logging.getLogger("bot")


class VolumeTracker:
    """심볼별 직전 N개 1m 봉 거래량을 보관해 ratio 계산."""

    def __init__(self, window: int = 60):
        self.window = window
        self.history: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))

    def record(self, symbol: str, volume: float) -> None:
        self.history[symbol].append(volume)

    def ratio_against_avg(self, symbol: str, current_volume: float) -> float:
        h = self.history[symbol]
        if len(h) < 5:
            return 0.0
        avg = sum(h) / len(h)
        if avg <= 0:
            return 0.0
        return current_volume / avg


class Bot:
    def __init__(self):
        self.db = AlertDB(CFG.DB_PATH)
        self.rest = BinanceRest()
        self.sm = StateMachine()
        self.tm = TrendlineManager(self.rest, self.db)
        self.vol = VolumeTracker(window=CFG.VOLUME_AVG_WINDOW_MINUTES)

    async def on_message(self, msg: dict) -> None:
        data = msg.get("data") or msg
        k = data.get("k")
        if not k:
            return
        symbol = k["s"]
        ts = int(k["t"])
        close = float(k["c"])
        volume = float(k["v"])
        is_final = bool(k["x"])
        interval = k["i"]

        if interval == "1m":
            ratio = self.vol.ratio_against_avg(symbol, volume)
            t = self.sm.on_price_tick(symbol, close, ratio, ts)
            if t:
                await self._handle_transition(t)
            if is_final:
                self.vol.record(symbol, volume)
                t2 = self.sm.on_minute_tick(symbol, close, ts)
                if t2:
                    await self._handle_transition(t2)

        elif interval == "1d" and is_final:
            t = self.sm.on_daily_close(symbol, close, ts)
            if t:
                await self._handle_transition(t)

    async def _handle_transition(self, t) -> None:
        if t.to_state in (StageState.ATTEMPT, StageState.HOLDING, StageState.CONFIRMED):
            already = self.db.was_alerted(
                t.symbol, t.trendline.p1.open_time, t.trendline.p2.open_time, t.to_state,
            )
            if not already:
                await send_alert(t)
                self.db.record_alert(t)
                log.info("🚨 %s %s @ %.6g (line=%.6g)",
                         t.symbol, t.to_state.value, t.price, t.line_value)
        try:
            self.db.save_state(self.sm.get_state(t.symbol, t.trendline))
        except Exception:
            pass

    async def run(self) -> None:
        log.info("부팅: 추세선 1차 계산")
        loop = asyncio.get_event_loop()
        lines_by_symbol = await loop.run_in_executor(None, self.tm.refresh_all)
        for lines in lines_by_symbol.values():
            for ln in lines:
                self.sm.register(ln)
        symbols = list(lines_by_symbol.keys())
        if not symbols:
            log.error("모니터링할 심볼이 없음 — 종료")
            return
        log.info("WebSocket 시작: %d 심볼", len(symbols))
        await asyncio.gather(
            stream_klines(symbols, self.on_message),
            self.tm.schedule_daily(self.sm),
        )


def main():
    logging.basicConfig(
        level=CFG.LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(Bot().run())


if __name__ == "__main__":
    main()
