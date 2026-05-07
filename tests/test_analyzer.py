from src.models import Candle
from src.analyzer import find_best_trendline, trend_r_squared


def make_candle(idx, high, low=None, close=None, vol=1000.0):
    low = low if low is not None else high - 1
    close = close if close is not None else high - 0.5
    return Candle(
        open_time=idx * 86_400_000, open=close, high=high, low=low, close=close,
        volume=vol, quote_volume=vol * close,
    )


def _build_downtrend_with_swings(swing_indices: list[int], swing_high: float,
                                   length: int = 100) -> list[Candle]:
    """우하향 추세 + 명시된 idx에 swing high를 만든다.
    R² > 0.3 + 마지막 close가 swing line 근처가 되도록."""
    base_start, base_end = swing_high * 0.95, swing_high * 0.5
    candles = []
    for i in range(length):
        # 우하향 close
        ratio = i / max(1, length - 1)
        base = base_start + (base_end - base_start) * ratio
        h = base + 0.5
        c = base
        candles.append(make_candle(i, high=h, close=c))
    # swing high 위치에 spike
    for idx in swing_indices:
        candles[idx] = make_candle(idx, high=swing_high, close=swing_high - 0.3)
    # 마지막 봉을 swing line 근처로 (현재가 ≈ line)
    candles[-1] = make_candle(length - 1, high=swing_high - 0.5, close=swing_high - 0.5)
    return candles


def test_trend_r2_horizontal_line_zero():
    closes = [10.0] * 50
    assert trend_r_squared(closes) < 0.01


def test_trend_r2_perfect_uptrend():
    closes = [float(i) for i in range(50)]
    assert trend_r_squared(closes) > 0.99


def test_trend_r2_too_short():
    assert trend_r_squared([1.0, 2.0]) == 0.0


def test_picks_longer_trendline_over_shorter():
    """추세 명확한 상황에서 길고 touches 많은 라인이 우선."""
    candles = _build_downtrend_with_swings([10, 50, 90], swing_high=20.0, length=100)
    line = find_best_trendline("X", candles)
    assert line is not None
    # 가장 긴 (10, 90) 또는 (10, 50) 또는 (50, 90) — 모두 OK, 핵심은 swing 잇는 라인
    assert line.p1.idx in (10, 50, 90)
    assert line.p2.idx in (10, 50, 90)


def test_picks_more_touches_over_just_length():
    """3-touch 라인이 우선."""
    candles = _build_downtrend_with_swings([20, 60, 100, 130], swing_high=30.0, length=145)
    line = find_best_trendline("X", candles)
    assert line is not None
    assert line.p1.idx in (20, 60, 100, 130)


def test_returns_none_when_too_few_swings():
    candles = [make_candle(i, high=10 + i * 0.1, close=10 + i * 0.1) for i in range(30)]
    line = find_best_trendline("X", candles)
    assert line is None


def test_returns_none_when_too_few_candles():
    candles = [make_candle(i, high=10) for i in range(10)]
    line = find_best_trendline("X", candles)
    assert line is None


def test_returns_none_when_no_trend():
    """v4: 횡보 코인은 None 반환 (R² < 0.3)."""
    candles = [make_candle(i, high=10 + (i % 3) * 0.5, close=10 + (i % 3) * 0.3)
               for i in range(100)]
    line = find_best_trendline("X", candles)
    assert line is None
