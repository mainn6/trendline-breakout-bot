from src.models import SwingHigh, Trendline, StageState, Transition
from src.telegram_notifier import format_message


def make_t(to_state):
    line = Trendline(
        symbol="SUIUSDT",
        p1=SwingHigh(idx=0, high=2.0, open_time=1_700_000_000_000),
        p2=SwingHigh(idx=50, high=1.0, open_time=1_704_320_000_000),
        slope=-0.02, slope_pct=-0.01, created_at_idx=100,
    )
    return Transition(
        symbol="SUIUSDT", trendline=line,
        from_state=StageState.INITIAL, to_state=to_state,
        price=1.05, line_value=1.0, ts_ms=1_730_000_000_000,
        volume_ratio=2.1,
    )


def test_attempt_message_contains_emoji_and_symbol():
    msg = format_message(make_t(StageState.ATTEMPT))
    assert "🟡" in msg and "SUIUSDT" in msg and "다운트렌드" in msg
    assert "binance.com" in msg


def test_holding_message():
    msg = format_message(make_t(StageState.HOLDING))
    assert "🟠" in msg and "굳히기" in msg


def test_confirmed_message():
    msg = format_message(make_t(StageState.CONFIRMED))
    assert "🟢" in msg and "확정" in msg
