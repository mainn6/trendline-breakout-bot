from typing import Sequence
from src.models import Trendline, Candle
from src.trendline import line_value_at


def passes_distance(line: Trendline, min_dist: int, max_dist: int) -> bool:
    d = line.p2.idx - line.p1.idx
    return min_dist <= d <= max_dist


def passes_min_bars_after_p2(line: Trendline, current_idx: int, min_bars: int) -> bool:
    return current_idx - line.p2.idx >= min_bars


def is_first_breakout(line: Trendline, candles: Sequence[Candle], current_idx: int) -> bool:
    for i in range(line.p2.idx + 1, current_idx):
        if candles[i].close > line_value_at(line, i):
            return False
    return True
