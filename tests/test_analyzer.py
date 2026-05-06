from src.models import Candle
from src.analyzer import find_best_trendline


def make_candle(idx, high, low=None, close=None, vol=1000.0):
    low = low if low is not None else high - 1
    close = close if close is not None else high - 0.5
    return Candle(
        open_time=idx * 86_400_000, open=close, high=high, low=low, close=close,
        volume=vol, quote_volume=vol * close,
    )


def _peak_at(idx, peak_high, base_high=10.0):
    """idx에 봉 하나 만들고 좌우 5봉은 base_high.
    peak_high가 base_high보다 크면 swing high 후보."""
    return make_candle(idx, peak_high)


def test_picks_longer_trendline_over_shorter():
    """짧고 가까운 swing 쌍보다 길고 멀리 있는 쌍을 선호."""
    candles = [make_candle(i, high=10, close=19.8) for i in range(80)]
    # 긴 추세선용: idx 10, 50  (40 길이)
    candles[10] = make_candle(10, high=20, close=19.5)
    candles[50] = make_candle(50, high=20, close=19.5)
    # 짧은 쌍: idx 60, 72  (12 길이)
    candles[60] = make_candle(60, high=15, close=14.5)
    candles[72] = make_candle(72, high=15, close=14.5)
    # 마지막 봉 close가 line(=20)에 가깝게
    candles[-1] = make_candle(79, high=20.5, close=20.1)

    line = find_best_trendline("X", candles)
    assert line is not None
    assert line.p1.idx == 10
    assert line.p2.idx == 50


def test_picks_more_touches_over_just_length():
    """3-touch 라인이 길이만 긴 2-touch보다 우선."""
    candles = [make_candle(i, high=10, close=29.5) for i in range(150)]
    for i in (20, 60, 100):
        candles[i] = make_candle(i, high=30, close=29.5)
    candles[30] = make_candle(30, high=20, close=19.5)
    candles[140] = make_candle(140, high=20, close=19.5)
    # 마지막 봉 close가 3-touch 라인(=30)에 가깝게
    candles[-1] = make_candle(149, high=30.2, close=29.9)

    line = find_best_trendline("X", candles)
    assert line is not None
    assert line.p1.idx in (20, 60, 100)
    assert line.p2.idx in (20, 60, 100)


def test_returns_none_when_too_few_swings():
    candles = [make_candle(i, high=10) for i in range(30)]
    line = find_best_trendline("X", candles)
    assert line is None


def test_returns_none_when_too_few_candles():
    candles = [make_candle(i, high=10) for i in range(10)]
    line = find_best_trendline("X", candles)
    assert line is None
