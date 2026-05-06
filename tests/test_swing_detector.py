from src.models import Candle
from src.swing_detector import find_swing_highs, is_swing_high


def make_candle(idx, high, low=None, close=None, vol=1000.0):
    low = low if low is not None else high - 1
    close = close if close is not None else high - 0.5
    return Candle(
        open_time=idx * 86_400_000, open=close, high=high, low=low, close=close,
        volume=vol, quote_volume=vol * close,
    )


def test_simple_swing_high_in_middle():
    candles = [make_candle(i, high=10) for i in range(11)]
    candles[5] = make_candle(5, high=20)
    swings = find_swing_highs(candles, lookback=5)
    assert len(swings) == 1
    assert swings[0].idx == 5
    assert swings[0].high == 20


def test_no_swing_at_edges():
    """좌우 5봉 미만이면 swing 인정 안 됨 — idx 5가 유일한 후보."""
    highs = [10, 11, 12, 13, 14, 50, 14, 13, 12, 11, 10]
    candles = [make_candle(i, high=h) for i, h in enumerate(highs)]
    swings = find_swing_highs(candles, lookback=5)
    assert [s.idx for s in swings] == [5]


def test_two_swings():
    candles = [make_candle(i, high=10) for i in range(30)]
    candles[7] = make_candle(7, high=20)
    candles[20] = make_candle(20, high=25)
    swings = find_swing_highs(candles, lookback=5)
    assert [s.idx for s in swings] == [7, 20]


def test_no_swing_when_tied_neighbor():
    candles = [make_candle(i, high=10) for i in range(11)]
    candles[5] = make_candle(5, high=15)
    candles[6] = make_candle(6, high=15)
    swings = find_swing_highs(candles, lookback=5)
    assert swings == []


def test_is_swing_high_index_too_low():
    candles = [make_candle(i, high=10) for i in range(11)]
    assert is_swing_high(candles, 4, lookback=5) is False
