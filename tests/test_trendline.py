from src.models import SwingHigh, Trendline
from src.trendline import build_trendline, line_value_at, classify


def sw(idx, high):
    return SwingHigh(idx=idx, high=high, open_time=idx * 86_400_000)


def test_horizontal_line_value():
    line = build_trendline("X", sw(0, 100), sw(10, 100), current_idx=20)
    assert abs(line_value_at(line, 5) - 100) < 1e-6
    assert abs(line_value_at(line, 50) - 100) < 1e-6


def test_descending_line_value():
    line = build_trendline("X", sw(0, 200), sw(10, 100), current_idx=20)
    assert abs(line_value_at(line, 20) - 0) < 1e-6
    assert line.slope < 0


def test_ascending_line_value():
    line = build_trendline("X", sw(0, 100), sw(10, 110), current_idx=20)
    assert abs(line_value_at(line, 20) - 120) < 1e-6
    assert line.slope > 0


def test_classify_downtrend():
    line = build_trendline("X", sw(0, 200), sw(50, 100), current_idx=60)
    assert "다운트렌드" in classify(line)


def test_classify_box():
    line = build_trendline("X", sw(0, 100.0), sw(50, 100.001), current_idx=60)
    assert "박스" in classify(line)


def test_classify_rising():
    line = build_trendline("X", sw(0, 100), sw(50, 150), current_idx=60)
    assert "상승" in classify(line)


def test_build_trendline_raises_on_same_idx():
    import pytest
    with pytest.raises(ValueError):
        build_trendline("X", sw(5, 100), sw(5, 110), current_idx=10)
