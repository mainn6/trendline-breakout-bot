"""추세선 자동 탐색 v2 — 모든 swing 쌍 평가 후 최적 1개 선택.

점수 = (2 + touches) × TOUCH_WEIGHT + length_bonus − above_penalty

여기서 touches는 다른 swing high가 직선에 ±touch_tolerance 이내로 닿는 개수.
저항선의 본질은 "여러 고점이 같은 직선 위에 늘어선" 패턴이므로 touches가 가장 강한 신호.
"""
from dataclasses import dataclass
from typing import Optional

from src.config import CFG
from src.models import Candle, SwingHigh, Trendline
from src.swing_detector import find_swing_highs
from src.trendline import build_trendline, line_value_at


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
    # 현재 시점 추세선 값이 비현실적이면 (음수/0) 제외
    if line_val_now <= 0:
        return None
    # 현재가가 추세선에서 너무 멀면 의미 없음 — 이미 돌파한 옛 추세선
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

    # proximity 보너스: 현재가가 추세선에 가까울수록 +
    proximity_bonus = (CFG.MAX_DISTANCE_FROM_LINE_PCT - distance_pct) * 1000
    score = (2 + touches) * TOUCH_WEIGHT + distance - above * ABOVE_PENALTY + proximity_bonus
    return TrendlineCandidate(
        line=line, score=score, touches=touches,
        length=distance, above_count=above,
    )


def find_best_trendline(symbol: str, candles: list[Candle]) -> Optional[Trendline]:
    """모든 swing high 쌍을 평가해 점수 최고인 추세선 1개 반환."""
    if len(candles) < 2 * CFG.SWING_LOOKBACK + CFG.MIN_SWING_DISTANCE + CFG.MIN_BARS_AFTER_P2:
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
