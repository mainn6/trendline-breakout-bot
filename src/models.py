from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float


@dataclass(frozen=True)
class SwingHigh:
    idx: int
    high: float
    open_time: int


@dataclass(frozen=True)
class Trendline:
    symbol: str
    p1: SwingHigh
    p2: SwingHigh
    slope: float
    slope_pct: float
    created_at_idx: int


class StageState(str, Enum):
    INITIAL = "initial"
    ATTEMPT = "attempt"
    HOLDING = "holding"
    CONFIRMED = "confirmed"


@dataclass
class TrackingState:
    symbol: str
    trendline: Trendline
    state: StageState = StageState.INITIAL
    attempt_started_ms: int | None = None
    last_above_line_ms: int | None = None
    consecutive_above_minutes: int = 0


@dataclass
class Transition:
    symbol: str
    trendline: Trendline
    from_state: StageState
    to_state: StageState
    price: float
    line_value: float
    ts_ms: int
    volume_ratio: float = 0.0
