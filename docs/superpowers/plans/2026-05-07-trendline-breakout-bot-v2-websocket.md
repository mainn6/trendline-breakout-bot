# Trendline Breakout Alert Bot — v2 (WebSocket 실시간 + 3단계 알람)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Binance USDT 무기한 선물 시장(거래량 ≥ $10M, ~150개)에서 1일봉 Swing High 추세선을 자동으로 그리고, 가격이 그 선을 돌파할 때 3단계(🟡 시도 / 🟠 굳히기 / 🟢 확정)로 Telegram 알람을 실시간 발송하는 봇.

**Architecture:** Python 단일 프로세스. (1) 시작/매일 자정에 REST로 모든 심볼의 1일봉 250개를 가져와 Swing High 검출 + 추세선 메모리 캐시. (2) Binance Futures WebSocket 멀티플렉스 스트림(`<symbol>@kline_1d` × N)을 구독해 1초 단위 가격 + 거래량 + 봉 마감 이벤트 수신. (3) 가격 갱신마다 상태 머신을 돌려 단계 전이 → Telegram 발송. (4) 상태/알람 이력은 SQLite로 영속화 (재시작 안전).

**Tech Stack:** Python 3.11+, `httpx` (REST), `websockets` (WS), `python-dotenv`, stdlib `sqlite3` / `asyncio`, `pytest`+`pytest-asyncio`.

---

## 1. 핵심 알고리즘

### 1.1 추세선 자동 생성 (변경 없음, v1과 동일)
- Swing High = 좌우 5봉보다 high가 큰 봉
- 추세선 = 최근 2개 Swing High를 잇는 직선
- 필터:
  - 두 swing 사이 10~200봉
  - 두 번째 swing 후 ≥ 3봉
  - 같은 (symbol, p1, p2) 추세선당 한 사이클만 추적

### 1.2 3단계 알람 상태 머신

```
                    ┌─────────────────┐
            ┌──────►│    INITIAL      │◄────────┐
            │       └────────┬────────┘         │
            │                │ 가격 > line × 1.005 │
            │                │  AND 거래량 ≥ 1.5x │
            │                ▼                   │
            │       ┌─────────────────┐         │
            │       │  🟡 ATTEMPT      │         │
            │       │  (시도 알람 발송)│         │
            │       └────────┬────────┘         │
            │   가격 ≤ line   │ 1시간 동안       │
            ├────────────────┤ 가격 > line 유지  │
            │                ▼                   │
            │       ┌─────────────────┐         │
            │       │  🟠 HOLDING      │         │
            │       │ (굳히기 알람)    │         │
            │       └────────┬────────┘         │
            │  봉마감 close ≤ │ 1d 봉 마감       │
            │  line          │ close > line     │
            └────────────────┤                   │
                             ▼                   │
                    ┌─────────────────┐         │
                    │  🟢 CONFIRMED    │         │
                    │ (확정 알람, 종료)│         │
                    └─────────────────┘         │
                                                │
   (CONFIRMED 후 새 swing high 생기면 추세선 갱신 → 새 INITIAL)
```

### 1.3 단계별 트리거 조건

| 단계 | 트리거 | 메시지 | 색 |
|------|--------|--------|-----|
| **🟡 ATTEMPT** | `price > line × 1.005` (0.5% 위) AND `1m 거래량 누적 ≥ rolling 평균 × 1.5` | "추세선 시도 — 진입 신호 약함" | 노랑 |
| **🟠 HOLDING** | ATTEMPT 진입 후 **연속 60분간 매 1분 체크에서 가격 > line 유지** | "1시간 굳히기 성공 — 신뢰도 ↑" | 주황 |
| **🟢 CONFIRMED** | HOLDING 상태에서 **1d 봉 마감 시 close > line** (Binance kline `x: true` 이벤트) | "1일봉 종가 돌파 확정 — 강한 신호" | 초록 |

### 1.4 상태 후퇴 / 종료
- ATTEMPT 진입 후 가격이 다시 `line` 아래로 → **INITIAL 복귀** (알람 X)
- HOLDING 진입 후 1d 봉 마감이 `close ≤ line` → **INITIAL 복귀** ("실패" 메시지 옵션)
- CONFIRMED 도달 → 그 추세선 추적 종료. 이후 새 Swing High가 갱신되면 새 추세선 생성 → 새 INITIAL.

### 1.5 정확한 거래량 누적 정의

WebSocket `kline_1d` 메시지의 `V` 필드는 **현재 1d 봉의 누적 거래량(base asset)**. 1.5배 비교 기준은:

```python
# REST에서 미리 계산해 메모리에 저장
volume_avg_20d = sum(c.volume for c in last_20_candles) / 20

# 실시간 비교 — 봉이 진행 중일 때
# 봉이 마감되어 봐야 정확하지만, intraday 비교는:
# 현재 봉의 누적 vol × (24h / 경과시간) 으로 추정 → 너무 부정확

# 단순화: 직전 24시간 평균 대비 현재 1m candle의 거래량 비교
# 또는 직전 1시간 평균 거래량 × 1.5 보다 최근 1m 거래량이 크면 OK

# 실용적 접근: aggTrade stream 또는 1m kline stream 별도 구독
```

→ **결정**: `<symbol>@kline_1m` 도 같이 구독해서 **직전 60분 1m 봉 거래량 평균 × 1.5 ≥ 현재 1m 봉 거래량** 으로 검사. 1d 봉 누적 거래량보다 즉응성 ↑.

---

## 2. 시스템 아키텍처

### 2.1 데이터 흐름

```
                 ┌──────────────────────────────────────┐
                 │  부팅 / 매일 KST 09:00 (1d 마감 후)   │
                 │  ─────────────────────────────────   │
                 │  REST: get_top_usdt_symbols($10M+)   │
                 │  REST: get_klines(1d, 250) × 150개   │
                 │  → 추세선 캐시 in-memory             │
                 │  → SQLite: 활성 추세선 upsert        │
                 └─────────────────┬────────────────────┘
                                   │
                                   ▼
        ┌──────────────────────────────────────────────┐
        │  Binance Futures WebSocket (멀티플렉스)       │
        │  /stream?streams=                            │
        │   btcusdt@kline_1d/btcusdt@kline_1m/         │
        │   ethusdt@kline_1d/ethusdt@kline_1m/...      │
        │  (심볼당 2 stream × 150 = 300 stream)         │
        └──────────────────┬───────────────────────────┘
                           │
                           ▼
              ┌──────────────────────────┐
              │  StreamRouter (asyncio)  │
              │  - kline_1m 메시지       │──► 가격/거래량 갱신
              │    → state_machine.tick()│
              │  - kline_1d (x:true)     │──► 봉 마감 이벤트
              │    → state_machine       │     → CONFIRMED 체크
              │      .on_daily_close()   │     → 추세선 재계산
              └──────────┬───────────────┘
                         │
                         ▼
              ┌──────────────────────────┐
              │  StateMachine            │
              │  - 심볼별 상태 보관       │
              │  - 전이 발생 시 callback  │
              └──────────┬───────────────┘
                         │ (transition: INITIAL→ATTEMPT 등)
                         ▼
              ┌──────────────────────────┐
              │  Telegram Notifier       │
              │  + Alert DB (영속화)     │
              └──────────────────────────┘
```

### 2.2 파일 구조

```
/Users/jevis/트레이딩뷰/
├── .env
├── .env.example
├── pyproject.toml
├── alerts.db                    # SQLite (gitignore)
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py                # 모든 파라미터
│   ├── models.py                # Candle, SwingHigh, Trendline, Signal
│   ├── binance_rest.py          # REST 클라이언트
│   ├── binance_ws.py            # WebSocket 멀티플렉스
│   ├── swing_detector.py        # find_swing_highs
│   ├── trendline.py             # build, line_value_at, classify
│   ├── state_machine.py         # 3단계 상태 머신 (핵심)
│   ├── alert_db.py              # SQLite 영속화
│   ├── telegram_notifier.py     # 3종 메시지 포맷 + 발송
│   ├── trendline_manager.py     # 추세선 캐시 + 매일 갱신
│   ├── analyzer.py              # 추세선 그리는 로직 통합
│   └── main.py                  # asyncio 진입점
└── tests/
    ├── conftest.py
    ├── fixtures/                # SUI/TON/POPCAT/KAITO 1d 캔들
    ├── test_swing_detector.py
    ├── test_trendline.py
    ├── test_state_machine.py    # 핵심: 모든 전이 시나리오
    ├── test_alert_db.py
    └── test_integration.py      # 가짜 WS 이벤트로 end-to-end
```

### 2.3 데이터 모델

```python
# src/models.py
from dataclasses import dataclass
from enum import Enum

@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float; high: float; low: float; close: float
    volume: float; quote_volume: float

@dataclass(frozen=True)
class SwingHigh:
    idx: int; high: float; open_time: int

@dataclass(frozen=True)
class Trendline:
    symbol: str
    p1: SwingHigh
    p2: SwingHigh
    slope: float
    slope_pct: float
    created_at_idx: int  # 마지막 1d 봉 idx (재계산 추적용)

class StageState(str, Enum):
    INITIAL = "initial"
    ATTEMPT = "attempt"
    HOLDING = "holding"
    CONFIRMED = "confirmed"

@dataclass
class TrackingState:
    """심볼+추세선 1조합당 1개"""
    symbol: str
    trendline: Trendline
    state: StageState = StageState.INITIAL
    attempt_started_ms: int | None = None    # ATTEMPT 진입 시각
    last_above_line_ms: int | None = None    # 1m 체크에서 마지막 line 위였던 시각
    consecutive_above_minutes: int = 0       # ATTEMPT 후 연속 line 위 분 수
```

### 2.4 SQLite 스키마

```sql
-- 활성 추세선 (매일 갱신, INSERT OR REPLACE)
CREATE TABLE IF NOT EXISTS trendlines (
    symbol TEXT NOT NULL,
    p1_open_time INTEGER NOT NULL,
    p2_open_time INTEGER NOT NULL,
    p1_high REAL NOT NULL, p2_high REAL NOT NULL,
    p1_idx INTEGER NOT NULL, p2_idx INTEGER NOT NULL,
    slope REAL NOT NULL,
    last_seen_ms INTEGER NOT NULL,
    PRIMARY KEY (symbol, p1_open_time, p2_open_time)
);

-- 추적 상태 (재시작 후 복원용)
CREATE TABLE IF NOT EXISTS tracking (
    symbol TEXT NOT NULL,
    p1_open_time INTEGER NOT NULL,
    p2_open_time INTEGER NOT NULL,
    state TEXT NOT NULL,  -- initial/attempt/holding/confirmed
    attempt_started_ms INTEGER,
    last_above_line_ms INTEGER,
    consecutive_above_minutes INTEGER DEFAULT 0,
    updated_ms INTEGER NOT NULL,
    PRIMARY KEY (symbol, p1_open_time, p2_open_time)
);

-- 발송된 알람 이력 (각 단계별 1회만)
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    p1_open_time INTEGER NOT NULL,
    p2_open_time INTEGER NOT NULL,
    stage TEXT NOT NULL,  -- attempt/holding/confirmed
    sent_ms INTEGER NOT NULL,
    price REAL NOT NULL,
    line_value REAL NOT NULL,
    UNIQUE (symbol, p1_open_time, p2_open_time, stage)
);
```

---

## 3. Tasks

### Task 1: 프로젝트 스캐폴딩 (~5분)

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: pyproject.toml**

```toml
[project]
name = "trendline-breakout-bot"
version = "0.2.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "websockets>=12.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-mock>=3.12"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: .gitignore + .env.example**

```
# .gitignore
.env
*.db
__pycache__/
.pytest_cache/
.venv/
*.pyc

# .env.example
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id
LOG_LEVEL=INFO
```

- [ ] **Step 3: 가상환경 + 설치**

```bash
cd /Users/jevis/트레이딩뷰
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
git init && git add -A && git commit -m "chore: 프로젝트 스캐폴딩 (v2 ws)"
```

---

### Task 2: config.py

**Files:** `src/config.py`

- [ ] **Step 1: 작성**

```python
# src/config.py
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    # 추세선 알고리즘
    SWING_LOOKBACK: int = 5
    MIN_SWING_DISTANCE: int = 10
    MAX_SWING_DISTANCE: int = 200
    MIN_BARS_AFTER_P2: int = 3
    
    # 3단계 임계값
    ATTEMPT_BREAKOUT_PCT: float = 0.005       # 0.5%
    HOLDING_DURATION_MINUTES: int = 60        # 1시간 유지
    VOLUME_RATIO_THRESHOLD: float = 1.5       # 1.5배
    VOLUME_AVG_WINDOW_MINUTES: int = 60       # 직전 60분 평균

    # 심볼 필터
    MIN_QUOTE_VOLUME_USDT: float = 10_000_000.0   # $10M
    KLINE_LIMIT: int = 250

    # Binance
    REST_BASE: str = "https://fapi.binance.com"
    WS_BASE: str = "wss://fstream.binance.com"

    # 일일 추세선 재계산 (UTC, 1d 봉 마감 직후)
    DAILY_RECALC_HOUR_UTC: int = 0
    DAILY_RECALC_MINUTE: int = 5

    # 텔레그램
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    DB_PATH: str = "alerts.db"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

CFG = Config()
```

- [ ] **Step 2: Commit**

```bash
git add src/config.py && git commit -m "feat: config 중앙화 (3단계 알람 파라미터)"
```

---

### Task 3: models.py + swing_detector.py + trendline.py

이 3개는 v1과 동일하므로 PLAN v1의 Task 3,4,5를 그대로 따라 구현.

**(v1 PLAN 참조)** — 변경 없음. TDD로 작성 후 commit:
```bash
git commit -m "feat: 데이터 모델 + Swing 검출 + 추세선 (TDD)"
```

---

### Task 4: state_machine.py — 3단계 상태 머신 (핵심, TDD)

**Files:** `src/state_machine.py`, `tests/test_state_machine.py`

- [ ] **Step 1: 모든 전이 시나리오 테스트**

```python
# tests/test_state_machine.py
from src.state_machine import StateMachine, Transition
from src.models import Trendline, SwingHigh, StageState

def make_line(slope=0.0, p1_high=100.0):
    p1 = SwingHigh(idx=0, high=p1_high, open_time=0)
    p2 = SwingHigh(idx=10, high=p1_high + slope*10, open_time=10*60_000)
    return Trendline(symbol="BTCUSDT", p1=p1, p2=p2,
                     slope=slope, slope_pct=slope/p1_high, created_at_idx=20)

def test_initial_to_attempt_on_breakout():
    sm = StateMachine()
    line = make_line()
    sm.register(line)
    
    # 가격 0.5% 위 + 거래량 1.5배
    t = sm.on_price_tick("BTCUSDT", price=100.6, volume_ratio=1.6, ts_ms=1_000_000)
    assert t is not None
    assert t.from_state == StageState.INITIAL
    assert t.to_state == StageState.ATTEMPT

def test_no_attempt_below_buffer():
    sm = StateMachine()
    sm.register(make_line())
    t = sm.on_price_tick("BTCUSDT", price=100.3, volume_ratio=1.6, ts_ms=1_000_000)  # 0.3%만
    assert t is None

def test_no_attempt_low_volume():
    sm = StateMachine()
    sm.register(make_line())
    t = sm.on_price_tick("BTCUSDT", price=100.6, volume_ratio=1.0, ts_ms=1_000_000)
    assert t is None

def test_attempt_to_initial_on_drop():
    sm = StateMachine()
    sm.register(make_line())
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, 1_000_000)  # → ATTEMPT
    t = sm.on_price_tick("BTCUSDT", 99.5, 1.0, 1_001_000)
    assert t.from_state == StageState.ATTEMPT
    assert t.to_state == StageState.INITIAL

def test_attempt_to_holding_after_60min():
    sm = StateMachine()
    sm.register(make_line())
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, 0)  # → ATTEMPT
    
    # 59분 동안 매분마다 line 위 유지
    for m in range(1, 60):
        sm.on_minute_tick("BTCUSDT", price=100.5, ts_ms=m*60_000)
    state = sm.get_state("BTCUSDT", line=sm.lines["BTCUSDT"][0])
    assert state.state == StageState.ATTEMPT  # 아직 60분 안 됨
    
    t = sm.on_minute_tick("BTCUSDT", price=100.5, ts_ms=60*60_000)
    assert t.to_state == StageState.HOLDING

def test_holding_to_confirmed_on_daily_close():
    sm = StateMachine()
    sm.register(make_line())
    # ATTEMPT → HOLDING 진행
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, 0)
    for m in range(1, 61):
        sm.on_minute_tick("BTCUSDT", 100.5, m*60_000)
    
    t = sm.on_daily_close("BTCUSDT", close=101.0, ts_ms=24*3600_000)
    assert t.to_state == StageState.CONFIRMED

def test_holding_to_initial_on_failed_close():
    sm = StateMachine()
    sm.register(make_line())
    sm.on_price_tick("BTCUSDT", 100.6, 1.6, 0)
    for m in range(1, 61):
        sm.on_minute_tick("BTCUSDT", 100.5, m*60_000)
    
    t = sm.on_daily_close("BTCUSDT", close=99.5, ts_ms=24*3600_000)
    assert t.to_state == StageState.INITIAL
```

- [ ] **Step 2: 구현 (요지)**

```python
# src/state_machine.py
from dataclasses import dataclass
from src.models import Trendline, StageState, TrackingState
from src.trendline import line_value_at
from src.config import CFG

@dataclass
class Transition:
    symbol: str
    trendline: Trendline
    from_state: StageState
    to_state: StageState
    price: float
    line_value: float
    ts_ms: int

class StateMachine:
    def __init__(self):
        self.lines: dict[str, list[Trendline]] = {}      # symbol → 활성 추세선들
        self.states: dict[tuple, TrackingState] = {}     # (symbol, p1_ts, p2_ts) → state

    def register(self, line: Trendline) -> None:
        self.lines.setdefault(line.symbol, []).append(line)
        key = (line.symbol, line.p1.open_time, line.p2.open_time)
        if key not in self.states:
            self.states[key] = TrackingState(symbol=line.symbol, trendline=line)

    def _line_value_now(self, line: Trendline, ts_ms: int) -> float:
        # 시간 → 봉 idx 변환 단순화: line.p2.open_time + N*86400000 = open_time
        bars_since_p2 = (ts_ms - line.p2.open_time) // 86_400_000
        idx_now = line.p2.idx + bars_since_p2
        return line_value_at(line, idx_now)

    def on_price_tick(self, symbol: str, price: float, volume_ratio: float,
                      ts_ms: int) -> Transition | None:
        for line in self.lines.get(symbol, []):
            key = (symbol, line.p1.open_time, line.p2.open_time)
            st = self.states[key]
            line_val = self._line_value_now(line, ts_ms)
            
            if st.state == StageState.INITIAL:
                if (price > line_val * (1 + CFG.ATTEMPT_BREAKOUT_PCT)
                        and volume_ratio >= CFG.VOLUME_RATIO_THRESHOLD):
                    st.state = StageState.ATTEMPT
                    st.attempt_started_ms = ts_ms
                    st.last_above_line_ms = ts_ms
                    st.consecutive_above_minutes = 0
                    return Transition(symbol, line, StageState.INITIAL, StageState.ATTEMPT,
                                       price, line_val, ts_ms)
            
            elif st.state == StageState.ATTEMPT:
                if price <= line_val:
                    st.state = StageState.INITIAL
                    return Transition(symbol, line, StageState.ATTEMPT, StageState.INITIAL,
                                       price, line_val, ts_ms)
        return None

    def on_minute_tick(self, symbol: str, price: float, ts_ms: int) -> Transition | None:
        for line in self.lines.get(symbol, []):
            key = (symbol, line.p1.open_time, line.p2.open_time)
            st = self.states[key]
            line_val = self._line_value_now(line, ts_ms)
            
            if st.state == StageState.ATTEMPT:
                if price > line_val:
                    st.consecutive_above_minutes += 1
                    if st.consecutive_above_minutes >= CFG.HOLDING_DURATION_MINUTES:
                        st.state = StageState.HOLDING
                        return Transition(symbol, line, StageState.ATTEMPT, StageState.HOLDING,
                                           price, line_val, ts_ms)
                else:
                    st.state = StageState.INITIAL
                    return Transition(symbol, line, StageState.ATTEMPT, StageState.INITIAL,
                                       price, line_val, ts_ms)
        return None

    def on_daily_close(self, symbol: str, close: float, ts_ms: int) -> Transition | None:
        for line in self.lines.get(symbol, []):
            key = (symbol, line.p1.open_time, line.p2.open_time)
            st = self.states[key]
            line_val = self._line_value_now(line, ts_ms)
            
            if st.state == StageState.HOLDING:
                if close > line_val:
                    st.state = StageState.CONFIRMED
                    return Transition(symbol, line, StageState.HOLDING, StageState.CONFIRMED,
                                       close, line_val, ts_ms)
                else:
                    st.state = StageState.INITIAL
                    return Transition(symbol, line, StageState.HOLDING, StageState.INITIAL,
                                       close, line_val, ts_ms)
        return None

    def get_state(self, symbol, line):
        return self.states[(symbol, line.p1.open_time, line.p2.open_time)]
```

- [ ] **Step 3: 테스트 통과 확인 + Commit**

```bash
pytest tests/test_state_machine.py -v
git add src/state_machine.py tests/test_state_machine.py
git commit -m "feat(sm): 3단계 상태 머신 + 모든 전이 테스트"
```

---

### Task 5: alert_db.py — 영속화 (TDD)

**Files:** `src/alert_db.py`, `tests/test_alert_db.py`

스키마는 §2.4 참조. 메서드:

```python
class AlertDB:
    def upsert_trendline(self, line: Trendline): ...
    def load_active_trendlines(self) -> list[Trendline]: ...
    def save_state(self, ts: TrackingState): ...
    def load_state(self, symbol, p1_ts, p2_ts) -> TrackingState | None: ...
    def record_alert(self, signal): ...
    def was_alerted(self, symbol, p1_ts, p2_ts, stage: StageState) -> bool: ...
```

- [ ] TDD: 각 메서드 테스트 → 구현 → 테스트 통과 → commit.

---

### Task 6: telegram_notifier.py — 3종 메시지

**Files:** `src/telegram_notifier.py`, `tests/test_telegram_notifier.py`

- [ ] **포맷터**

```python
def format_attempt(sig) -> str:
    return (f"🟡 *시도 알람* — 추세선 도전 중\n\n"
            f"💎 {sig.symbol} (1d)\n"
            f"💰 현재가 `{sig.price:.6g}` (+{sig.pct_above:.2f}% above line)\n"
            f"📈 거래량: 평균 대비 {sig.volume_ratio:.2f}x\n"
            f"📐 추세선: {sig.line_label}\n"
            f"⚠️ 가짜 돌파일 수도 있음 — 1시간 더 지켜봐야 함\n"
            f"🔗 https://www.binance.com/en/futures/{sig.symbol}")

def format_holding(sig) -> str:
    return (f"🟠 *굳히기 성공* — 1시간 추세선 유지\n\n"
            f"💎 {sig.symbol} (1d)\n"
            f"💰 현재가 `{sig.price:.6g}`\n"
            f"📐 추세선값: `{sig.line_value:.6g}`\n"
            f"✅ 신뢰도 ↑ — 종가 마감까지 지켜볼 가치 있음\n"
            f"🔗 https://www.binance.com/en/futures/{sig.symbol}")

def format_confirmed(sig) -> str:
    return (f"🟢 *확정 돌파* — 1d 봉 종가 마감\n\n"
            f"💎 *{sig.symbol}* (1d)\n"
            f"💰 종가 `{sig.price:.6g}`\n"
            f"📐 추세선값: `{sig.line_value:.6g}`\n"
            f"🔥 강한 신호 — 진입 검토\n"
            f"🔗 https://www.binance.com/en/futures/{sig.symbol}")
```

- [ ] `send(transition, db)` 함수: stage별 포맷 + 텔레그램 POST + DB 기록.

---

### Task 7: trendline_manager.py — 추세선 캐시 + 매일 갱신

**Files:** `src/trendline_manager.py`

- [ ] **요점**

```python
class TrendlineManager:
    def __init__(self, rest_client, db):
        self.rest = rest_client
        self.db = db

    async def refresh_all(self) -> dict[str, list[Trendline]]:
        """모든 심볼의 추세선 재계산. 부팅 + 매일 자정+5분."""
        symbols = self.rest.get_top_usdt_symbols(CFG.MIN_QUOTE_VOLUME_USDT)
        result = {}
        for sym in symbols:
            candles = self.rest.get_klines(sym, "1d", CFG.KLINE_LIMIT)
            line = analyzer.build_latest_trendline(sym, candles)
            if line:
                result[sym] = [line]
                self.db.upsert_trendline(line)
        return result

    async def schedule_daily(self, sm: StateMachine):
        while True:
            await sleep_until_next_utc(CFG.DAILY_RECALC_HOUR_UTC, CFG.DAILY_RECALC_MINUTE)
            new_lines = await self.refresh_all()
            sm.replace_all(new_lines)  # 끝난(CONFIRMED) 라인 정리 + 새 라인 등록
```

---

### Task 8: binance_ws.py — WebSocket 멀티플렉스

**Files:** `src/binance_ws.py`, `tests/test_binance_ws.py`

- [ ] **요점**

```python
import json, asyncio, websockets

async def stream_klines(symbols: list[str], on_message):
    """심볼당 kline_1d + kline_1m 두 stream 멀티플렉스."""
    streams = []
    for s in symbols:
        s_low = s.lower()
        streams += [f"{s_low}@kline_1d", f"{s_low}@kline_1m"]
    
    # 100개 stream씩 분할 (Binance 제한)
    chunks = [streams[i:i+100] for i in range(0, len(streams), 100)]
    tasks = [_run_one(chunk, on_message) for chunk in chunks]
    await asyncio.gather(*tasks)

async def _run_one(streams, on_message):
    url = f"{CFG.WS_BASE}/stream?streams={'/'.join(streams)}"
    async for ws in websockets.connect(url, ping_interval=180):
        try:
            async for raw in ws:
                msg = json.loads(raw)
                await on_message(msg)
        except websockets.ConnectionClosed:
            await asyncio.sleep(5)  # 재연결
            continue
```

- [ ] 메시지 라우팅: `stream` 필드로 `kline_1d` vs `kline_1m` 구분, `data.k` 추출.

---

### Task 9: main.py — 통합 진입점

**Files:** `src/main.py`

- [ ] **요점**

```python
import asyncio, logging
from src.config import CFG
from src.binance_rest import BinanceRest
from src.binance_ws import stream_klines
from src.state_machine import StateMachine
from src.alert_db import AlertDB
from src.trendline_manager import TrendlineManager
from src.telegram_notifier import send

log = logging.getLogger("bot")

class Bot:
    def __init__(self):
        self.db = AlertDB(CFG.DB_PATH)
        self.rest = BinanceRest()
        self.sm = StateMachine()
        self.tm = TrendlineManager(self.rest, self.db)

    async def on_message(self, msg):
        data = msg.get("data", {})
        k = data.get("k", {})
        if not k: return
        symbol = k["s"]
        ts = k["t"]
        close = float(k["c"])
        volume = float(k["v"])
        is_final = k["x"]
        interval = k["i"]
        
        if interval == "1m":
            # 거래량 ratio 계산 (rolling 60개 1m 봉)
            volume_ratio = self._compute_volume_ratio(symbol, volume, ts)
            
            # 가격 tick — INITIAL → ATTEMPT 체크
            t = self.sm.on_price_tick(symbol, close, volume_ratio, ts)
            if t: await self._handle_transition(t)
            
            # 분 마감(is_final) — ATTEMPT → HOLDING 카운트
            if is_final:
                t = self.sm.on_minute_tick(symbol, close, ts)
                if t: await self._handle_transition(t)
        
        elif interval == "1d" and is_final:
            # 1d 봉 마감 — HOLDING → CONFIRMED 체크
            t = self.sm.on_daily_close(symbol, close, ts)
            if t: await self._handle_transition(t)

    async def _handle_transition(self, t):
        if t.to_state in (StageState.ATTEMPT, StageState.HOLDING, StageState.CONFIRMED):
            if not self.db.was_alerted(t.symbol, t.trendline.p1.open_time,
                                       t.trendline.p2.open_time, t.to_state):
                await send(t)
                self.db.record_alert(t)
                log.info("🚨 %s %s @ %.6g", t.symbol, t.to_state.value, t.price)
        self.db.save_state(self.sm.get_state(t.symbol, t.trendline))

    async def run(self):
        log.info("부팅: 추세선 1차 계산")
        lines_by_symbol = await self.tm.refresh_all()
        for lines in lines_by_symbol.values():
            for ln in lines:
                self.sm.register(ln)
        symbols = list(lines_by_symbol.keys())
        log.info("WebSocket 시작: %d 심볼", len(symbols))
        
        await asyncio.gather(
            stream_klines(symbols, self.on_message),
            self.tm.schedule_daily(self.sm),
        )

if __name__ == "__main__":
    logging.basicConfig(level=CFG.LOG_LEVEL)
    asyncio.run(Bot().run())
```

---

### Task 10: 통합 테스트 — 가짜 WS 이벤트로 end-to-end

**Files:** `tests/test_integration.py`

- [ ] **시나리오**: 가짜 추세선 등록 → 가짜 1m 가격 tick 시퀀스 주입 → 3단계 모두 발생하는지 확인. Telegram은 mock.

---

### Task 11: 백테스트 — SUI/TON 차트 검증

**Files:** `scripts/backtest.py`

- [ ] **목적**: 사용자가 보여준 SUI/TON/POPCAT/KAITO 1d 캔들에 슬라이딩 윈도우 적용 → 알람이 동그라미 친 날짜 부근에 발생하는지 확인.

WebSocket은 빼고 1d 봉만으로 시뮬레이션 (intraday 시뮬은 1d 캔들로 불가능). 즉, 매일 1d 봉 마감만 시뮬레이션 → 🟢 CONFIRMED 알람만 백테스트 가능. 🟡/🟠는 실시간 운영 중에만.

- [ ] 결과를 보고 임계값 튜닝 (`VOLUME_RATIO_THRESHOLD`, `ATTEMPT_BREAKOUT_PCT`).

---

### Task 12: 실서비스 시작

- [ ] **로컬 PC에서 1주일 시범 운영** — 알람 양/품질 체크.
- [ ] 알람 너무 많음 → 임계값 강화. 너무 적음 → 완화.
- [ ] 안정되면 Oracle Cloud Free Tier로 이전 (Ubuntu + systemd + journald 로그).

---

## 4. 검증 체크리스트

- [ ] `pytest -q` → 전체 테스트 그린
- [ ] `python scripts/backtest.py` → SUI/TON 사용자 차트 동그라미 날짜 ±2일 이내에서 🟢 알람 발생
- [ ] 5분 이상 `python -m src.main` 실행 → WebSocket 연결, 메시지 수신, 상태 전이 정상 동작
- [ ] Telegram 봇 토큰 등록 시 실제 알람이 텔레그램에 도착
- [ ] 봇 재시작 후 SQLite에서 상태 복원되는지 확인 (HOLDING 상태에서 재시작해도 유지)
- [ ] 같은 (symbol, p1, p2, stage) 알람은 **1번만** 발송

## 5. 향후 확장 (이 PLAN 밖)

- 4h 추세선도 동시 모니터링 (시간봉 멀티)
- 추세선이 3개 이상 swing high를 잇는 경우 자동 탐색 (정밀도 ↑)
- 차트 이미지 첨부 (matplotlib 헤드리스 렌더)
- Telegram `/snooze SUIUSDT 24h` 같은 명령으로 일시 음소거
- 백테스트로 승률/평균 수익률 통계 페이지
