"""추세선 자동 탐색 v4 — 모든 swing 쌍 평가 후 최적 1개 선택.

점수 = (2 + touches) × TOUCH_WEIGHT + length × LENGTH_BONUS − above × ABOVE_PENALTY + proximity_bonus

v4 변경:
  - SWING_LOOKBACK 5 → 3 (사용자 시각의 작은 swing도 포착)
  - 추세선의 touches가 MIN_TOUCHES 미만이면 제외 (= 2점만 우연 매칭 거름)
  - 가격 시계열의 linear regression R² < MIN_TREND_R2 면 제외 (= 횡보 코인 거름)
"""
import statistics
from dataclasses import dataclass
from typing import Optional

from src.config import CFG
from src.models import Candle, SwingHigh, Trendline
from src.swing_detector import find_swing_highs
from src.trendline import build_trendline, line_value_at


def trend_r_squared(closes: list[float]) -> float:
    """종가 시계열에 linear fit → R² (0~1, 1이 완벽 추세)."""
    n = len(closes)
    if n < 3:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(closes) / n
    cov = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
    var_x = sum((i - x_mean) ** 2 for i in range(n))
    var_y = sum((y - y_mean) ** 2 for y in closes)
    if var_x == 0 or var_y == 0:
        return 0.0
    correlation = cov / (var_x ** 0.5 * var_y ** 0.5)
    return correlation ** 2


TOUCH_TOLERANCE = 0.005          # 0.5% 이내면 "닿음"
MAX_SLOPE_PCT_PER_BAR = 0.05     # 1봉당 5% 넘는 추세선은 비현실
TOUCH_WEIGHT = 100.0
ABOVE_PENALTY = 50.0


@dataclass
class TrendlineCandidate:
    line: Trendline
    score: float
    touches: int
    length: int
    above_count: int


def _evaluate(p1: SwingHigh, p2: SwingHigh, all_swings: list[SwingHigh],
              symbol: str, current_idx: int, current_close: float) -> Optional[TrendlineCandidate]:
    distance = p2.idx - p1.idx
    if distance < CFG.MIN_SWING_DISTANCE or distance > CFG.MAX_SWING_DISTANCE:
        return None

    line = build_trendline(symbol, p1, p2, current_idx)
    if abs(line.slope_pct) > MAX_SLOPE_PCT_PER_BAR:
        return None

    line_val_now = line_value_at(line, current_idx)
    if line_val_now <= 0:
        return None
    distance_pct = abs(current_close - line_val_now) / line_val_now
    if distance_pct > CFG.MAX_DISTANCE_FROM_LINE_PCT:
        return None

    touches = 0
    above = 0
    for sw in all_swings:
        if sw.idx == p1.idx or sw.idx == p2.idx:
            continue
        line_val = line_value_at(line, sw.idx)
        if line_val <= 0:
            continue
        rel = (sw.high - line_val) / line_val
        if abs(rel) <= TOUCH_TOLERANCE:
            touches += 1
        elif rel > TOUCH_TOLERANCE:
            above += 1

    # v4: 추세선 신뢰도 검사
    if touches < CFG.MIN_TOUCHES:
        return None  # 2개 점만 우연히 맞춘 라인 거름

    proximity_bonus = max(0.0, (0.10 - distance_pct)) * 800
    length_bonus = distance * CFG.LENGTH_BONUS_WEIGHT
    score = (2 + touches) * TOUCH_WEIGHT + length_bonus - above * ABOVE_PENALTY + proximity_bonus
    return TrendlineCandidate(
        line=line, score=score, touches=touches,
        length=distance, above_count=above,
    )


def find_best_trendline(symbol: str, candles: list[Candle]) -> Optional[Trendline]:
    """모든 swing high 쌍을 평가해 점수 최고인 추세선 1개 반환.
    v4: 추세 강도(R²) 필터 추가 — 횡보 코인 제외."""
    if len(candles) < 2 * CFG.SWING_LOOKBACK + CFG.MIN_SWING_DISTANCE + CFG.MIN_BARS_AFTER_P2:
        return None

    # v4: 추세 강도 검사 (횡보 코인 제외)
    closes_recent = [c.close for c in candles[-100:]]
    r2 = trend_r_squared(closes_recent)
    if r2 < CFG.MIN_TREND_R2:
        return None

    swings = find_swing_highs(candles, CFG.SWING_LOOKBACK)
    if len(swings) < 2:
        return None

    current_idx = len(candles) - 1

    best: Optional[TrendlineCandidate] = None
    for i in range(len(swings)):
        for j in range(i + 1, len(swings)):
            p1, p2 = swings[i], swings[j]
            if current_idx - p2.idx < CFG.MIN_BARS_AFTER_P2:
                continue
            cand = _evaluate(p1, p2, swings, symbol, current_idx, candles[-1].close)
            if cand is None:
                continue
            if best is None or cand.score > best.score:
                best = cand

    return best.line if best else None


def find_top_trendlines(symbol: str, candles: list[Candle], top_n: int = 3) -> list[Trendline]:
    """디버깅/시각화용: 점수 상위 N개."""
    if len(candles) < 2 * CFG.SWING_LOOKBACK + CFG.MIN_SWING_DISTANCE + CFG.MIN_BARS_AFTER_P2:
        return []
    swings = find_swing_highs(candles, CFG.SWING_LOOKBACK)
    if len(swings) < 2:
        return []
    current_idx = len(candles) - 1

    cands: list[TrendlineCandidate] = []
    for i in range(len(swings)):
        for j in range(i + 1, len(swings)):
            p1, p2 = swings[i], swings[j]
            if current_idx - p2.idx < CFG.MIN_BARS_AFTER_P2:
                continue
            c = _evaluate(p1, p2, swings, symbol, current_idx, candles[-1].close)
            if c:
                cands.append(c)
    cands.sort(key=lambda c: -c.score)
    return [c.line for c in cands[:top_n]]


# 호환성: trendline_manager가 이 이름으로 import
build_latest_trendline = find_best_trendline
