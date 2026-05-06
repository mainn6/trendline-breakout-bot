from typing import Sequence
from src.models import Candle, SwingHigh


def is_swing_high(candles: Sequence[Candle], i: int, lookback: int = 5) -> bool:
    if i < lookback or i >= len(candles) - lookback:
        return False
    window = candles[i - lookback : i + lookback + 1]
    window_max = max(c.high for c in window)
    if candles[i].high != window_max:
        return False
    return sum(1 for c in window if c.high == window_max) == 1


def find_swing_highs(candles: Sequence[Candle], lookback: int = 5) -> list[SwingHigh]:
    return [
        SwingHigh(idx=i, high=candles[i].high, open_time=candles[i].open_time)
        for i in range(len(candles))
        if is_swing_high(candles, i, lookback)
    ]
