from src.models import Trendline, StageState, TrackingState, Transition
from src.trendline import line_value_at
from src.config import CFG


MS_PER_DAY = 86_400_000
MS_PER_MINUTE = 60_000


def _line_value_at_ms(line: Trendline, ts_ms: int) -> float:
    """ts_ms 시점의 추세선 가격. 기준은 line.p2 (이상치 보호)."""
    bars_since_p2 = (ts_ms - line.p2.open_time) / MS_PER_DAY
    idx_now = line.p2.idx + bars_since_p2
    return line_value_at(line, idx_now)


class StateMachine:
    def __init__(self):
        self.lines_by_symbol: dict[str, list[Trendline]] = {}
        self.states: dict[tuple, TrackingState] = {}

    def _key(self, line: Trendline) -> tuple:
        return (line.symbol, line.p1.open_time, line.p2.open_time)

    def register(self, line: Trendline) -> None:
        self.lines_by_symbol.setdefault(line.symbol, []).append(line)
        key = self._key(line)
        if key not in self.states:
            self.states[key] = TrackingState(symbol=line.symbol, trendline=line)

    def replace_all(self, lines_by_symbol: dict[str, list[Trendline]]) -> None:
        """매일 추세선 재계산 후 호출. CONFIRMED 상태는 그대로 두고 새 추세선만 추가."""
        old_keys = set(self.states.keys())
        new_keys = set()
        for sym, lines in lines_by_symbol.items():
            for line in lines:
                self.register(line)
                new_keys.add(self._key(line))
        for k in old_keys - new_keys:
            st = self.states.get(k)
            if st and st.state != StageState.CONFIRMED:
                self.lines_by_symbol.get(k[0], [])
                self.states.pop(k, None)
        for sym in list(self.lines_by_symbol.keys()):
            self.lines_by_symbol[sym] = [
                ln for ln in self.lines_by_symbol[sym] if self._key(ln) in new_keys
            ]
            if not self.lines_by_symbol[sym]:
                self.lines_by_symbol.pop(sym, None)

    def get_state(self, symbol: str, line: Trendline) -> TrackingState:
        return self.states[self._key(line)]

    def on_price_tick(self, symbol: str, price: float, volume_ratio: float, ts_ms: int) -> Transition | None:
        """1분 내 가격 갱신마다. INITIAL→ATTEMPT, ATTEMPT→INITIAL 검사."""
        for line in self.lines_by_symbol.get(symbol, []):
            st = self.states[self._key(line)]
            line_val = _line_value_at_ms(line, ts_ms)

            if st.state == StageState.INITIAL:
                if (price > line_val * (1 + CFG.ATTEMPT_BREAKOUT_PCT)
                        and volume_ratio >= CFG.VOLUME_RATIO_THRESHOLD):
                    st.state = StageState.ATTEMPT
                    st.attempt_started_ms = ts_ms
                    st.last_above_line_ms = ts_ms
                    st.consecutive_above_minutes = 0
                    return Transition(
                        symbol=symbol, trendline=line,
                        from_state=StageState.INITIAL, to_state=StageState.ATTEMPT,
                        price=price, line_value=line_val, ts_ms=ts_ms,
                        volume_ratio=volume_ratio,
                    )
            elif st.state == StageState.ATTEMPT:
                if price <= line_val:
                    st.state = StageState.INITIAL
                    st.attempt_started_ms = None
                    st.consecutive_above_minutes = 0
                    return Transition(
                        symbol=symbol, trendline=line,
                        from_state=StageState.ATTEMPT, to_state=StageState.INITIAL,
                        price=price, line_value=line_val, ts_ms=ts_ms,
                    )
        return None

    def on_minute_tick(self, symbol: str, price: float, ts_ms: int) -> Transition | None:
        """1분봉 마감마다. ATTEMPT 상태에서 1분 카운트 누적."""
        for line in self.lines_by_symbol.get(symbol, []):
            st = self.states[self._key(line)]
            line_val = _line_value_at_ms(line, ts_ms)

            if st.state == StageState.ATTEMPT:
                if price > line_val:
                    st.consecutive_above_minutes += 1
                    st.last_above_line_ms = ts_ms
                    if st.consecutive_above_minutes >= CFG.HOLDING_DURATION_MINUTES:
                        st.state = StageState.HOLDING
                        return Transition(
                            symbol=symbol, trendline=line,
                            from_state=StageState.ATTEMPT, to_state=StageState.HOLDING,
                            price=price, line_value=line_val, ts_ms=ts_ms,
                        )
                else:
                    st.state = StageState.INITIAL
                    st.attempt_started_ms = None
                    st.consecutive_above_minutes = 0
                    return Transition(
                        symbol=symbol, trendline=line,
                        from_state=StageState.ATTEMPT, to_state=StageState.INITIAL,
                        price=price, line_value=line_val, ts_ms=ts_ms,
                    )
        return None

    def on_daily_close(self, symbol: str, close: float, ts_ms: int) -> Transition | None:
        """1일봉 마감 시. HOLDING→CONFIRMED 또는 INITIAL."""
        for line in self.lines_by_symbol.get(symbol, []):
            st = self.states[self._key(line)]
            line_val = _line_value_at_ms(line, ts_ms)

            if st.state == StageState.HOLDING:
                if close > line_val:
                    st.state = StageState.CONFIRMED
                    return Transition(
                        symbol=symbol, trendline=line,
                        from_state=StageState.HOLDING, to_state=StageState.CONFIRMED,
                        price=close, line_value=line_val, ts_ms=ts_ms,
                    )
                else:
                    st.state = StageState.INITIAL
                    st.attempt_started_ms = None
                    st.consecutive_above_minutes = 0
                    return Transition(
                        symbol=symbol, trendline=line,
                        from_state=StageState.HOLDING, to_state=StageState.INITIAL,
                        price=close, line_value=line_val, ts_ms=ts_ms,
                    )
        return None
