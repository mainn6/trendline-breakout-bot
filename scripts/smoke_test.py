"""부팅만 검증: 추세선 1차 계산 + 텔레그램 부팅 알람 + WS 연결 확인 후 종료."""
import asyncio
import logging

from src.config import CFG
from src.main import Bot
from src.binance_ws import stream_klines


async def smoke():
    logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log = logging.getLogger("smoke")

    bot = Bot()
    log.info("부팅: 추세선 1차 계산 시작")
    loop = asyncio.get_event_loop()
    lines = await loop.run_in_executor(None, bot.tm.refresh_all)
    for ls in lines.values():
        for ln in ls:
            bot.sm.register(ln)
    symbols = list(lines.keys())
    log.info("✅ 추세선 그려진 심볼: %d", len(symbols))

    # 텔레그램 부팅 알람
    import httpx
    msg = (
        f"🤖 *봇 부팅 완료*\n\n"
        f"📊 모니터링 심볼: *{len(symbols)}개*\n"
        f"📈 추세선 그려진: {len(lines)}개\n"
        f"💵 거래량 필터: ≥ ${CFG.MIN_QUOTE_VOLUME_USDT/1e6:.0f}M\n"
        f"🎯 알람 조건: 0.5% 돌파 + 거래량 1.5배\n\n"
        f"이제 1d 봉 추세선을 실시간 추적합니다."
    )
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"https://api.telegram.org/bot{CFG.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CFG.TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
            },
        )
        r.raise_for_status()
        log.info("✅ 텔레그램 부팅 알람 발송 성공")

    # WS 연결 검증 — 90초만 받아보고 종료
    received = {"count": 0, "samples": []}

    async def on_msg(m):
        received["count"] += 1
        if len(received["samples"]) < 3:
            data = m.get("data") or m
            k = data.get("k", {})
            received["samples"].append(
                f"{k.get('s', '?')} {k.get('i', '?')} close={k.get('c', '?')}"
            )

    log.info("WebSocket 연결 — 90초 동안 메시지 수신 검증")
    # 처음 20개 심볼만 (스모크용)
    test_syms = symbols[:20]
    try:
        await asyncio.wait_for(stream_klines(test_syms, on_msg, streams_per_conn=40), timeout=90)
    except asyncio.TimeoutError:
        log.info("✅ WS 90초 동안 메시지 %d개 수신", received["count"])
        for s in received["samples"]:
            log.info("   샘플: %s", s)


if __name__ == "__main__":
    asyncio.run(smoke())
