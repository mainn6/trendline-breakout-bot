import os
import tempfile

import pytest

from src.models import (
    SwingHigh, Trendline, StageState, TrackingState, Transition,
)
from src.alert_db import AlertDB


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield AlertDB(path)
    if os.path.exists(path):
        os.remove(path)


def make_line(symbol="BTCUSDT", p1_t=100, p2_t=200):
    return Trendline(
        symbol=symbol,
        p1=SwingHigh(idx=0, high=100.0, open_time=p1_t),
        p2=SwingHigh(idx=10, high=100.0, open_time=p2_t),
        slope=0.0, slope_pct=0.0, created_at_idx=20,
    )


def make_transition(symbol="BTCUSDT", to_state=StageState.ATTEMPT, p1_t=100, p2_t=200):
    line = make_line(symbol, p1_t, p2_t)
    return Transition(
        symbol=symbol, trendline=line,
        from_state=StageState.INITIAL, to_state=to_state,
        price=101.0, line_value=100.0, ts_ms=1_000_000,
    )


def test_upsert_trendline(db):
    line = make_line()
    db.upsert_trendline(line)
    db.upsert_trendline(line)


def test_first_alert_recorded(db):
    t = make_transition()
    assert db.was_alerted("BTCUSDT", 100, 200, StageState.ATTEMPT) is False
    assert db.record_alert(t) is True
    assert db.was_alerted("BTCUSDT", 100, 200, StageState.ATTEMPT) is True


def test_duplicate_alert_returns_false(db):
    t = make_transition()
    assert db.record_alert(t) is True
    assert db.record_alert(t) is False


def test_different_stage_separate(db):
    t1 = make_transition(to_state=StageState.ATTEMPT)
    t2 = make_transition(to_state=StageState.HOLDING)
    db.record_alert(t1)
    assert db.was_alerted("BTCUSDT", 100, 200, StageState.HOLDING) is False
    db.record_alert(t2)
    assert db.was_alerted("BTCUSDT", 100, 200, StageState.HOLDING) is True


def test_different_trendline_separate(db):
    db.record_alert(make_transition(p2_t=200))
    assert db.was_alerted("BTCUSDT", 100, 250, StageState.ATTEMPT) is False
    assert db.was_alerted("ETHUSDT", 100, 200, StageState.ATTEMPT) is False


def test_save_state(db):
    line = make_line()
    ts = TrackingState(symbol="BTCUSDT", trendline=line,
                       state=StageState.ATTEMPT, attempt_started_ms=1234,
                       consecutive_above_minutes=15)
    db.save_state(ts)
    db.save_state(ts)
