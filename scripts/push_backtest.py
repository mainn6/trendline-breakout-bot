"""백테스트 최근 N일 알람을 텔레그램에 retro 발송.

실제 봇이 그 시점에 보냈을 🟢 확정 메시지 포맷 + 발송 후 실제 수익률(+1d/+3d) 표시.
스팸 방지: 최근 7일 분만 (DAYS_LOOKBACK 변경 가능).
"""
import asyncio
import statistics
from datetime import datetime, timedelta, timezone

import httpx

from src.analyzer import find_best_trendline
from src.binance_rest import BinanceRest
from src.config import CFG
from src.filters import is_first_breakout
from src.trendline import classify, line_value_at

KST = timezone(timedelta(hours=9))
DAYS_LOOKBACK = 7
TOP_N_SYMBOLS = 80
LOOKBACK_BARS = 500


def backtest_symbol(symbol: str, candles: list, cutoff_ms: int) -> list[dict]:
    alarms: list[dict] = []
    last_alarm_end = -1000
    avg_window = CFG.VOLUME_AVG_WINDOW_MINUTES

    for end in range(60, len(candles)):
        if candles[end].open_time < cutoff_ms:
            continue
        window = candles[: end + 1]
        line = find_best_trendline(symbol, window)
        if line is None:
            continue
        current = window[-1]
        current_idx = len(window) - 1
        line_val = line_value_at(line, current_idx)

        if current.close <= line_val * (1 + CFG.ATTEMPT_BREAKOUT_PCT):
            continue
        if not is_first_breakout(line, window, current_idx):
            continue
        if end - avg_window < 0:
            continue
        avg_vol = sum(c.volume for c in window[end - avg_window : end]) / avg_window
        if avg_vol <= 0:
            continue
        ratio = current.volume / avg_vol
        if ratio < CFG.VOLUME_RATIO_THRESHOLD:
            continue
        if end - last_alarm_end < 3:
            continue
        last_alarm_end = end

        future_pnl = {}
        for d in [1, 3, 7]:
            if end + d < len(candles):
                future_pnl[d] = (candles[end + d].close - current.close) / current.close * 100

        alarms.append({
            "symbol": symbol,
            "time": datetime.fromtimestamp(current.open_time / 1000, tz=KST),
            "entry": current.close,
            "line_val": line_val,
            "vol_ratio": ratio,
            "label": classify(line),
            "trendline_p1": (line.p1.high, datetime.fromtimestamp(line.p1.open_time / 1000, tz=KST)),
            "trendline_p2": (line.p2.high, datetime.fromtimestamp(line.p2.open_time / 1000, tz=KST)),
            "future": future_pnl,
        })
    return alarms


def format_message(a: dict) -> str:
    p1_h, p1_t = a["trendline_p1"]
    p2_h, p2_t = a["trendline_p2"]
    pct_above = (a["entry"] - a["line_val"]) / a["line_val"] * 100

    msg = (
        f"🟢 *[BACKTEST] 확정 돌파* — 1d 봉 종가 마감!\n\n"
        f"💎 *{a['symbol']}*  {a['label']}\n"
        f"💰 종가 `{a['entry']:.6g}`\n"
        f"📐 추세선값 `{a['line_val']:.6g}` (+{pct_above:.2f}%)\n"
        f"📈 거래량 평균 대비 {a['vol_ratio']:.2f}x\n"
        f"📐 P1: {p1_t:%y-%m-%d} ({p1_h:.4g}) → P2: {p2_t:%y-%m-%d} ({p2_h:.4g})\n"
        f"🕐 {a['time']:%Y-%m-%d} (KST)\n"
    )
    if a["future"]:
        parts = []
        for d in (1, 3, 7):
            if d in a["future"]:
                pnl = a["future"][d]
                emoji = "✅" if pnl > 0 else "❌"
                parts.append(f"{emoji} +{d}d {pnl:+.2f}%")
        if parts:
            msg += f"\n📊 *실제 결과*: {' | '.join(parts)}\n"
    msg += f"\n🔗 https://www.binance.com/en/futures/{a['symbol']}"
    return msg


async def send(client, msg: str) -> None:
    try:
        r = await client.post(
            f"https://api.telegram.org/bot{CFG.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CFG.TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  send error: {e}")


async def main():
    rest = BinanceRest()
    symbols = rest.get_top_usdt_symbols(CFG.MIN_QUOTE_VOLUME_USDT)[:TOP_N_SYMBOLS]
    print(f"[INFO] {len(symbols)} 심볼, 최근 {DAYS_LOOKBACK}일 백테스트")

    cutoff_ms = int((datetime.now(tz=KST) - timedelta(days=DAYS_LOOKBACK)).timestamp() * 1000)
    all_alarms: list[dict] = []
    for sym in symbols:
        try:
            candles = rest.get_klines(sym, "1d", LOOKBACK_BARS)
        except Exception as e:
            continue
        alarms = backtest_symbol(sym, candles, cutoff_ms)
        if alarms:
            all_alarms.extend(alarms)

    all_alarms.sort(key=lambda x: x["time"])
    print(f"[INFO] 최근 {DAYS_LOOKBACK}일 알람: {len(all_alarms)}개\n")

    if not all_alarms:
        print("알람 없음")
        return

    # 헤더 + 통계 1번
    n = len(all_alarms)
    pnl_1d = [a["future"][1] for a in all_alarms if 1 in a["future"]]
    n_up = sum(1 for a in all_alarms if a["future"].get(1, 0) > 0) if pnl_1d else 0
    wr_1d = (n_up / len(pnl_1d) * 100) if pnl_1d else 0
    avg_1d = statistics.mean(pnl_1d) if pnl_1d else 0
    classes_count = {a["label"]: sum(1 for x in all_alarms if x["label"] == a["label"]) for a in all_alarms}
    cls_lines = "\n".join(f"  {l}: {c}건" for l, c in sorted(classes_count.items(), key=lambda x: -x[1]))

    header = (
        f"📊 *백테스트 푸쉬 시작*\n\n"
        f"기간: 최근 *{DAYS_LOOKBACK}일*\n"
        f"심볼: 거래량 상위 {len(symbols)}개\n"
        f"알람: *{n}건*\n\n"
        f"분류 분포:\n{cls_lines}\n\n"
        f"+1d 통계: 승률 *{wr_1d:.1f}%* / 평균 *{avg_1d:+.2f}%*\n\n"
        f"⏬ 시간순으로 알람 1건씩 발송"
    )

    async with httpx.AsyncClient(timeout=15) as client:
        await send(client, header)
        await asyncio.sleep(1.5)
        for i, a in enumerate(all_alarms, 1):
            print(f"  [{i}/{n}] {a['time']:%m-%d} {a['symbol']:<15s} {a['label']}")
            await send(client, format_message(a))
            await asyncio.sleep(1.5)

    print(f"\n✅ {n}개 알람 텔레그램 발송 완료")


if __name__ == "__main__":
    asyncio.run(main())
