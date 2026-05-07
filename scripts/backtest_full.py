"""본격 백테스트 — 거래량 상위 N개 심볼, 1d 봉, 🟢 확정 알람 기준.

각 알람마다:
  - 알람 시점 + 진입가
  - +1d / +3d / +7d / +14d / +30d 후 종가 대비 수익률
출력:
  - 심볼별 알람 발생 횟수
  - 기간별 승률 / 평균 / 중앙 / 최고 / 최저
"""
import statistics
from datetime import datetime, timedelta, timezone

from src.analyzer import find_best_trendline
from src.binance_rest import BinanceRest
from src.config import CFG
from src.filters import is_first_breakout
from src.trendline import classify, line_value_at

KST = timezone(timedelta(hours=9))
LOOKAHEAD_DAYS = [1, 3, 7, 14, 30]
TOP_N_SYMBOLS = 80
LOOKBACK_BARS = 500


def backtest_symbol(symbol: str, candles: list) -> list[dict]:
    alarms: list[dict] = []
    last_alarm_end = -1000
    avg_window = CFG.VOLUME_AVG_WINDOW_MINUTES

    for end in range(60, len(candles)):
        window = candles[: end + 1]
        line = find_best_trendline(symbol, window)
        if line is None:
            continue
        current = window[-1]
        current_idx = len(window) - 1
        line_val = line_value_at(line, current_idx)

        # 종가 0.5% 위 + 거래량 1.5배 + 첫 돌파 + 최소 간격 3봉
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

        alarm = {
            "symbol": symbol,
            "time": datetime.fromtimestamp(current.open_time / 1000, tz=KST),
            "entry": current.close,
            "line_val": line_val,
            "vol_ratio": ratio,
            "label": classify(line),
            "trendline_len": line.p2.idx - line.p1.idx,
            "future": {},
        }
        for d in LOOKAHEAD_DAYS:
            if end + d < len(candles):
                future_close = candles[end + d].close
                alarm["future"][d] = (future_close - current.close) / current.close * 100
        alarms.append(alarm)
    return alarms


def main():
    rest = BinanceRest()
    print(f"[INFO] 거래량 상위 {TOP_N_SYMBOLS}개 심볼 선정 중...")
    symbols = rest.get_top_usdt_symbols(CFG.MIN_QUOTE_VOLUME_USDT)[:TOP_N_SYMBOLS]
    print(f"[INFO] 선정: {len(symbols)} 심볼\n")

    all_alarms: list[dict] = []
    for i, sym in enumerate(symbols, 1):
        try:
            candles = rest.get_klines(sym, "1d", LOOKBACK_BARS)
        except Exception as e:
            print(f"  [{i:3d}/{len(symbols)}] {sym:15s}  fetch 실패: {e}")
            continue
        alarms = backtest_symbol(sym, candles)
        all_alarms.extend(alarms)
        marker = f"  ← {len(alarms)} 알람" if alarms else ""
        if alarms:
            print(f"  [{i:3d}/{len(symbols)}] {sym:15s}  {len(candles)} bars  {marker}")

    print(f"\n{'=' * 80}")
    print(f"총 알람 수: {len(all_alarms)}")
    print(f"심볼당 평균: {len(all_alarms)/len(symbols):.1f}")
    print(f"{'=' * 80}\n")

    if not all_alarms:
        print("알람이 없음. 임계값 낮춰서 재실행 권장.")
        return

    # 분류별 분포
    classes: dict[str, int] = {}
    for a in all_alarms:
        classes[a["label"]] = classes.get(a["label"], 0) + 1
    print("[알람 종류]")
    for label, count in sorted(classes.items(), key=lambda x: -x[1]):
        print(f"  {label:35s}  {count:4d}")
    print()

    # 기간별 통계
    print(f"{'기간':>6s}  {'N':>4s}  {'승률':>8s}  {'평균':>9s}  {'중앙':>9s}  {'최고':>9s}  {'최저':>9s}")
    print("-" * 70)
    for d in LOOKAHEAD_DAYS:
        pnls = [a["future"][d] for a in all_alarms if d in a["future"]]
        if not pnls:
            continue
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / len(pnls) * 100
        avg = statistics.mean(pnls)
        med = statistics.median(pnls)
        print(f"+{d:2d}d   {len(pnls):4d}   {wr:6.1f}%   {avg:+7.2f}%   {med:+7.2f}%   {max(pnls):+7.2f}%   {min(pnls):+7.2f}%")
    print()

    # 분류별 ×7일 수익률 비교
    print("[분류별 +7d 수익률]")
    print(f"{'분류':<35s}  {'N':>4s}  {'승률':>8s}  {'평균':>9s}  {'중앙':>9s}")
    print("-" * 75)
    for label in sorted(classes, key=lambda x: -classes[x]):
        sub = [a["future"][7] for a in all_alarms if a["label"] == label and 7 in a["future"]]
        if not sub:
            continue
        wr = sum(1 for p in sub if p > 0) / len(sub) * 100
        print(f"{label:<35s}  {len(sub):4d}   {wr:6.1f}%   {statistics.mean(sub):+7.2f}%   {statistics.median(sub):+7.2f}%")
    print()

    # 최근 알람 10개
    print("[최근 알람 10개]")
    print(f"{'time':<17s}  {'symbol':<15s}  {'entry':>10s}  {'+1d':>7s}  {'+7d':>7s}  {'+30d':>7s}  label")
    print("-" * 110)
    for a in sorted(all_alarms, key=lambda x: x["time"], reverse=True)[:10]:
        d1 = f"{a['future'].get(1, 0):+.2f}%" if 1 in a["future"] else " " * 7
        d7 = f"{a['future'].get(7, 0):+.2f}%" if 7 in a["future"] else " " * 7
        d30 = f"{a['future'].get(30, 0):+.2f}%" if 30 in a["future"] else " " * 7
        print(f"  {a['time']:%Y-%m-%d}  {a['symbol']:<15s}  {a['entry']:10.4g}  {d1:>7s}  {d7:>7s}  {d30:>7s}  {a['label']}")


if __name__ == "__main__":
    main()
