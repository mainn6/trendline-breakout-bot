import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.analyzer import build_latest_trendline
from src.binance_rest import BinanceRest
from src.alert_db import AlertDB
from src.config import CFG
from src.models import Trendline
from src.state_machine import StateMachine

log = logging.getLogger(__name__)


class TrendlineManager:
    def __init__(self, rest: BinanceRest, db: AlertDB):
        self.rest = rest
        self.db = db
        self.symbols: list[str] = []

    def refresh_all(self) -> dict[str, list[Trendline]]:
        self.symbols = self.rest.get_top_usdt_symbols(CFG.MIN_QUOTE_VOLUME_USDT)
        log.info("선정된 심볼 수: %d", len(self.symbols))
        result: dict[str, list[Trendline]] = {}
        for sym in self.symbols:
            try:
                candles = self.rest.get_klines(sym, "1d", CFG.KLINE_LIMIT)
                line = build_latest_trendline(sym, candles)
                if line:
                    result[sym] = [line]
                    self.db.upsert_trendline(line)
            except Exception as e:
                log.warning("%s 추세선 계산 실패: %s", sym, e)
        log.info("추세선 그려진 심볼: %d", len(result))
        return result

    async def schedule_daily(self, sm: StateMachine) -> None:
        while True:
            wait = self._seconds_until_next_recalc()
            log.info("다음 추세선 재계산까지 %d초 대기", wait)
            await asyncio.sleep(wait)
            try:
                lines_by_symbol = await asyncio.get_event_loop().run_in_executor(
                    None, self.refresh_all
                )
                sm.replace_all(lines_by_symbol)
                log.info("추세선 재계산 완료")
            except Exception as e:
                log.exception("추세선 재계산 실패: %s", e)

    @staticmethod
    def _seconds_until_next_recalc() -> int:
        now = datetime.now(tz=timezone.utc)
        target = now.replace(
            hour=CFG.DAILY_RECALC_HOUR_UTC, minute=CFG.DAILY_RECALC_MINUTE,
            second=0, microsecond=0,
        )
        if target <= now:
            target += timedelta(days=1)
        return int((target - now).total_seconds())
