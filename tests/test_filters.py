from src.models import SwingHigh, Trendline, Candle
from src.trendline import build_trendline
from src.filters import passes_distance, passes_min_bars_after_p2, is_first_breakout


def sw(idx, high):
    return SwingHigh(idx=idx, high=high, open_time=idx * 86_400_000)


def candle(idx, close, high=None, low=None, vol=1000.0):
    high = high if high is not None else close + 0.1
    low = low if low is not None else close - 0.1
    return Candle(
        open_time=idx * 86_400_000, open=close, high=high, low=low, close=close,
        volume=vol, quote_volume=vol * close,
    )


def test_distance_within_range():
    line = build_trendline("X", sw(0, 100), sw(50, 100), current_idx=60)
    assert passes_distance(line, 10, 200) is True


def test_distance_too_close():
    line = build_trendline("X", sw(0, 100), sw(5, 100), current_idx=10)
    assert passes_distance(line, 10, 200) is False


def test_distance_too_far():
    line = build_trendline("X", sw(0, 100), sw(250, 100), current_idx=260)
    assert passes_distance(line, 10, 200) is False


def test_min_bars_after_p2():
    line = build_trendline("X", sw(0, 100), sw(50, 100), current_idx=53)
    assert passes_min_bars_after_p2(line, current_idx=53, min_bars=3) is True
    assert passes_min_bars_after_p2(line, current_idx=52, min_bars=3) is False


def test_first_breakout_clean():
    line = build_trendline("X", sw(0, 100), sw(5, 100), current_idx=9)
    candles = [candle(i, close=99) for i in range(10)]
    candles[9] = candle(9, close=101)
    assert is_first_breakout(line, candles, current_idx=9) is True


def test_not_first_breakout_when_already_above():
    line = build_trendline("X", sw(0, 100), sw(5, 100), current_idx=9)
    candles = [candle(i, close=99) for i in range(10)]
    candles[7] = candle(7, close=102)
    candles[9] = candle(9, close=101)
    assert is_first_breakout(line, candles, current_idx=9) is False
