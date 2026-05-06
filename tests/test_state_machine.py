from src.models import Trendline, SwingHigh, StageState
from src.state_machine import StateMachine, MS_PER_DAY, MS_PER_MINUTE


def make_line(symbol="BTCUSDT", slope=0.0, p1_high=100.0, p1_idx=0, p2_idx=10):
    p1 = SwingHigh(idx=p1_idx, high=p1_high, open_time=p1_idx * MS_PER_DAY)
    p2 = SwingHigh(idx=p2_idx, high=p1_high + slope * (p2_idx - p1_idx),
                   open_time=p2_idx * MS_PER_DAY)
    return Trendline(
        symbol=symbol, p1=p1, p2=p2,
        slope=slope, slope_pct=slope / p1_high,
        created_at_idx=p2_idx + 5,
    )


def ts_at_idx(idx: int) -> int:
    return idx * MS_PER_DAY


def test_initial_to_attempt_on_breakout():
    sm = StateMachine()
    line = make_line()
    sm.register(line)
    t = sm.on_price_tick("BTCUSDT", price=100.6, volume_ratio=1.6, ts_ms=ts_at_idx(15))
    assert t is not None
    assert t.from_state == StageState.INITIAL
    assert t.to_state == StageState.ATTEMPT


def test_no_attempt_below_buffer():
    sm = StateMachine()
    sm.register(make_line())
    t = sm.on_price_tick("BTCUSDT", price=100.3, volume_ratio=1.6, ts_ms=ts_at_idx(15))
    assert t is None


def test_no_attempt_low_volume():
    sm = StateMachine()
    sm.register(make_line())
    t = sm.on_price_tick("BTCUSDT", price=100.6, volume_ratio=1.0, ts_ms=ts_at_idx(15))
    assert t is None


def test_attempt_to_initial_on_drop():
    sm = StateMachine()
    line = make_line()
    sm.register(line)
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, ts_at_idx(15))
    t = sm.on_price_tick("BTCUSDT", 99.5, 1.0, ts_at_idx(15) + 1000)
    assert t is not None
    assert t.from_state == StageState.ATTEMPT
    assert t.to_state == StageState.INITIAL


def test_attempt_to_holding_after_60min():
    sm = StateMachine()
    line = make_line()
    sm.register(line)
    base = ts_at_idx(15)
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, base)
    transition = None
    for m in range(1, 61):
        transition = sm.on_minute_tick("BTCUSDT", price=100.5, ts_ms=base + m * MS_PER_MINUTE)
    assert transition is not None
    assert transition.to_state == StageState.HOLDING


def test_attempt_does_not_promote_before_60min():
    sm = StateMachine()
    line = make_line()
    sm.register(line)
    base = ts_at_idx(15)
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, base)
    for m in range(1, 60):
        t = sm.on_minute_tick("BTCUSDT", 100.5, base + m * MS_PER_MINUTE)
        assert t is None or t.to_state != StageState.HOLDING
    state = sm.get_state("BTCUSDT", line)
    assert state.state == StageState.ATTEMPT


def test_holding_to_confirmed_on_daily_close():
    sm = StateMachine()
    line = make_line()
    sm.register(line)
    base = ts_at_idx(15)
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, base)
    for m in range(1, 61):
        sm.on_minute_tick("BTCUSDT", 100.5, base + m * MS_PER_MINUTE)
    t = sm.on_daily_close("BTCUSDT", close=101.0, ts_ms=ts_at_idx(16))
    assert t is not None
    assert t.to_state == StageState.CONFIRMED


def test_holding_to_initial_on_failed_close():
    sm = StateMachine()
    line = make_line()
    sm.register(line)
    base = ts_at_idx(15)
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, base)
    for m in range(1, 61):
        sm.on_minute_tick("BTCUSDT", 100.5, base + m * MS_PER_MINUTE)
    t = sm.on_daily_close("BTCUSDT", close=99.5, ts_ms=ts_at_idx(16))
    assert t is not None
    assert t.to_state == StageState.INITIAL


def test_attempt_resets_on_minute_below_line():
    sm = StateMachine()
    line = make_line()
    sm.register(line)
    base = ts_at_idx(15)
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, base)
    for m in range(1, 30):
        sm.on_minute_tick("BTCUSDT", 100.5, base + m * MS_PER_MINUTE)
    t = sm.on_minute_tick("BTCUSDT", 99.0, base + 30 * MS_PER_MINUTE)
    assert t is not None
    assert t.to_state == StageState.INITIAL
    assert sm.get_state("BTCUSDT", line).consecutive_above_minutes == 0


def test_descending_trendline_value_at_future():
    """다운트렌드: line slope=-1/봉, p1(0,200) p2(10,190). idx=20에서 line=180."""
    line = make_line(slope=-1.0, p1_high=200.0)
    sm = StateMachine()
    sm.register(line)
    t = sm.on_price_tick("BTCUSDT", price=181.0, volume_ratio=1.6, ts_ms=ts_at_idx(20))
    assert t is not None
    assert t.to_state == StageState.ATTEMPT
    assert abs(t.line_value - 180.0) < 1e-6
