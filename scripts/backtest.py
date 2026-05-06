"""백테스트: SUI/TON/POPCAT/KAITO 1d 캔들에 슬라이딩 윈도우 적용.
1d 봉 단위만 시뮬레이션 가능 (intraday 데이터 없음). 즉 🟢 CONFIRMED 알람만 검증."""
from datetime import datetime, timezone, timedelta

from src.analyzer import build_latest_trendline
from src.binance_rest import BinanceRest
from src.config import CFG
from src.filters import is_first_breakout
from src.trendline import line_value_at, classify

KST = timezone(timedelta(hours=9))
SYMBOLS = ["SUIUSDT", "TONUSDT", "POPCATUSDT", "KAITOUSDT", "BTCUSDT"]


def main():
    rest = BinanceRest()
    for sym in SYMBOLS:
        try:
            full = rest.get_klines(sym, "1d", 500)
        except Exception as e:
            print(f"\n=== {sym} === fetch 실패: {e}")
            continue

        print(f"\n=== {sym} (총 {len(full)} 봉) ===")
        last_alert_idx = -1000
        for end in range(60, len(full)):
            window = full[: end + 1]
            line = build_latest_trendline(sym, window)
            if not line:
                continue

            current = window[-1]
            current_idx = len(window) - 1
            line_val = line_value_at(line, current_idx)

            # 종가 0.5% 위 + 첫 돌파만
            if current.close <= line_val * (1 + CFG.ATTEMPT_BREAKOUT_PCT):
                continue
            if not is_first_breakout(line, window, current_idx):
                continue
            # 거래량 1.5배
            avg_vol = sum(c.volume for c in window[-CFG.VOLUME_AVG_WINDOW_MINUTES - 1 : -1]) / CFG.VOLUME_AVG_WINDOW_MINUTES
            ratio = current.volume / avg_vol if avg_vol > 0 else 0
            if ratio < CFG.VOLUME_RATIO_THRESHOLD:
                continue
            # 같은 알람 너무 가까이 안 나오게
            if end - last_alert_idx < 3:
                continue
            last_alert_idx = end

            t = datetime.fromtimestamp(current.open_time / 1000, tz=KST)
            print(f"  📍 {t:%Y-%m-%d}  close={current.close:.6g}  line={line_val:.6g}  "
                  f"vol×{ratio:.2f}  {classify(line)}")


if __name__ == "__main__":
    main()
