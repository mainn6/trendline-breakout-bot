import logging
from datetime import datetime, timezone, timedelta

import httpx

from src.config import CFG
from src.models import Transition, StageState
from src.trendline import classify

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


def _binance_url(symbol: str) -> str:
    return f"https://www.binance.com/en/futures/{symbol}"


def _pct_above(price: float, line_value: float) -> float:
    if line_value <= 0:
        return 0.0
    return (price - line_value) / line_value * 100


def _kst(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=KST).strftime("%Y-%m-%d %H:%M KST")


def _line_label(t: Transition) -> str:
    p1_d = datetime.fromtimestamp(t.trendline.p1.open_time / 1000, tz=KST).strftime("%y-%m-%d")
    p2_d = datetime.fromtimestamp(t.trendline.p2.open_time / 1000, tz=KST).strftime("%y-%m-%d")
    return f"{p1_d} ({t.trendline.p1.high:.6g}) → {p2_d} ({t.trendline.p2.high:.6g})"


def format_attempt(t: Transition) -> str:
    return (
        f"🟡 *시도 알람* — 추세선 도전 중\n\n"
        f"💎 *{t.symbol}* (1d)  {classify(t.trendline)}\n"
        f"💰 현재가 `{t.price:.6g}` (+{_pct_above(t.price, t.line_value):.2f}% above line)\n"
        f"📈 거래량: 평균 대비 {t.volume_ratio:.2f}x\n"
        f"📐 추세선: {_line_label(t)}\n"
        f"🕐 {_kst(t.ts_ms)}\n"
        f"⚠️ 가짜 돌파일 수도 있음 — 1시간 더 지켜봐야 함\n"
        f"🔗 {_binance_url(t.symbol)}"
    )


def format_holding(t: Transition) -> str:
    return (
        f"🟠 *굳히기 성공* — 1시간 추세선 위 유지\n\n"
        f"💎 *{t.symbol}* (1d)  {classify(t.trendline)}\n"
        f"💰 현재가 `{t.price:.6g}`\n"
        f"📐 추세선값: `{t.line_value:.6g}` (+{_pct_above(t.price, t.line_value):.2f}%)\n"
        f"🕐 {_kst(t.ts_ms)}\n"
        f"✅ 신뢰도 ↑ — 종가 마감까지 지켜볼 가치\n"
        f"🔗 {_binance_url(t.symbol)}"
    )


def format_confirmed(t: Transition) -> str:
    return (
        f"🟢 *확정 돌파* — 1d 봉 종가 마감!\n\n"
        f"💎 *{t.symbol}* (1d)  {classify(t.trendline)}\n"
        f"💰 종가 `{t.price:.6g}`\n"
        f"📐 추세선값: `{t.line_value:.6g}` (+{_pct_above(t.price, t.line_value):.2f}%)\n"
        f"📐 추세선: {_line_label(t)}\n"
        f"🕐 {_kst(t.ts_ms)}\n"
        f"🔥 강한 신호 — 진입 검토\n"
        f"🔗 {_binance_url(t.symbol)}"
    )


def format_message(t: Transition) -> str:
    if t.to_state == StageState.ATTEMPT:
        return format_attempt(t)
    if t.to_state == StageState.HOLDING:
        return format_holding(t)
    if t.to_state == StageState.CONFIRMED:
        return format_confirmed(t)
    return f"{t.symbol} {t.from_state.value}→{t.to_state.value}"


async def send_alert(t: Transition) -> None:
    if not CFG.TELEGRAM_BOT_TOKEN or not CFG.TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials 미설정 — 메시지 스킵")
        return
    url = f"https://api.telegram.org/bot{CFG.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CFG.TELEGRAM_CHAT_ID,
        "text": format_message(t),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
    except Exception as e:
        log.exception("Telegram 발송 실패: %s", e)
