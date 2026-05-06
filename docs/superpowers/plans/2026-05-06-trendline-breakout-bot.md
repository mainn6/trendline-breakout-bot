# Trendline Breakout Alert Bot 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Binance USDT 무기한 선물 시장에서 Swing High 추세선(Trend Line)을 자동으로 그리고, 종가가 그 선을 위로 돌파하는 코인을 감지해 Telegram으로 즉시 알람을 보내는 봇.

**Architecture:** Python 단일 프로세스. APScheduler가 매일 1일봉 마감 시점(UTC 00:00 = KST 09:00) 직후에 Binance Futures REST API로 거래량 상위 USDT-PERP 심볼 ~70개의 1d 캔들을 fetch → Swing High 검출 → 최근 2개 Swing High로 추세선 그리기 → 마지막 캔들 종가가 추세선을 0.3% 이상 돌파하면 Telegram Bot API로 알람 발송. SQLite로 (symbol + 추세선 ID) 중복 알람 방지.

**Tech Stack:** Python 3.11+, `httpx` (HTTP), `APScheduler` (스케줄러), `python-dotenv` (환경변수), `sqlite3` (stdlib, 중복 방지), `pytest` + `pytest-mock` (테스트). 차트 라이브러리 불필요 (헤드리스 봇).

---

## 1. 추세 알고리즘 정의 (이 봇의 두뇌)

### 1.1 Swing High 검출

```
def is_swing_high(candles, i, lookback=5):
    """좌우 lookback봉의 high보다 i번째 봉의 high가 같거나 크면 True"""
    if i < lookback or i >= len(candles) - lookback:
        return False
    window_max = max(c.high for c in candles[i-lookback : i+lookback+1])
    return candles[i].high == window_max
```

- **lookback = 5**(1d 기준): 좌우 5봉씩, 총 11봉 윈도우의 중심이 최고가
- 동률 처리: `>=` 아니라 `==`로 (가장 큰 봉 1개만)
- 마지막 5봉은 아직 좌측 5봉의 미래가 부족해 swing 확정 불가 — 이건 일부러 무시

### 1.2 추세선 그리기

```
swings = [(i, c.high) for i, c in enumerate(candles) if is_swing_high(candles, i)]
if len(swings) < 2:
    return None  # 추세선 그릴 수 없음

# 최근 2개 swing high
p1 = swings[-2]  # (idx1, high1)
p2 = swings[-1]  # (idx2, high2)

slope = (p2[1] - p1[1]) / (p2[0] - p1[0])
def line_value_at(idx):
    return p1[1] + slope * (idx - p1[0])
```

### 1.3 돌파 판정

```
current_idx = len(candles) - 1
current = candles[current_idx]
line_now = line_value_at(current_idx)

BREAKOUT_BUFFER = 0.003  # 0.3%
is_breakout = current.close > line_now * (1 + BREAKOUT_BUFFER)
```

**왜 종가? 왜 0.3%?**
- 종가 돌파 = 매수자가 그날 종가를 추세선 위로 끌어올렸다 = 신뢰도 ↑
- 0.3% 버퍼 = 추세선에 살짝 닿는 가짜 돌파 거름

### 1.4 신호 품질 필터 (모두 만족해야 알람)

| # | 필터 | 임계값 | 이유 |
|---|---|---|---|
| F1 | 두 swing high 사이 거리 | **10 ≤ 봉 ≤ 200** | 너무 가까우면 노이즈, 너무 멀면 의미 없음 |
| F2 | 두 번째 swing 이후 봉 수 | **≥ 3봉** | 추세선이 최소한 검증된 상태 |
| F3 | 첫 돌파 여부 | 두 번째 swing 이후 그 어떤 봉의 종가도 line 위에 있던 적 없음 | 한 추세선당 1회 알람 |
| F4 | 거래량 | 현재 봉 vol ≥ 직전 20봉 평균의 **1.3배** | 의미 있는 돌파만 |
| F5 (선택) | slope 분류 | slope < 0 → "다운트렌드 돌파"(강), slope ≥ 0 → "돌파"(중) | 메시지 차별화용 |

### 1.5 추세선 종류 자동 분류

```
if slope < -1e-6:
    label = "🔥 다운트렌드 돌파 (추세 반전)"  # SUI, TON
elif abs(slope) <= 1e-6:
    label = "📦 박스권 돌파"                   # POPCAT
else:
    label = "⚡ 상승 저항 돌파"                # KAITO
```

기울기는 % per bar 단위로 정규화: `slope_pct = slope / p1[1]`. 임계값 `1e-4`(=0.01%)로 평탄 vs 기울임 분류.

---

## 2. 시스템 아키텍처

```
                  ┌─────────────────────────────────┐
                  │   APScheduler (UTC 00:05)       │
                  └──────────────┬──────────────────┘
                                 │ 매일 1d 봉 마감 5분 후
                                 ▼
   ┌──────────────────┐    ┌──────────────────────┐
   │ binance_client   │───►│  symbol_filter       │
   │ - get_24h_ticker │    │  거래량 ≥ $50M        │
   │ - get_klines     │    │  USDT-PERP 약 70개    │
   └──────────────────┘    └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │  for each symbol:    │
                           │   fetch 200d candles │
                           │   ↓                  │
                           │   swing_detector     │
                           │   ↓                  │
                           │   trendline.check    │
                           │   ↓                  │
                           │   filters F1..F4     │
                           └──────────┬───────────┘
                                      │ breakout=True
                                      ▼
                           ┌──────────────────────┐
                           │  alert_db (SQLite)   │
                           │  중복? → skip        │
                           │  새 알람? → 기록      │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │  telegram_notifier   │
                           │  봇 → Chat ID        │
                           └──────────────────────┘
```

### 2.1 파일 구조

```
/Users/jevis/트레이딩뷰/
├── .env                         # TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── alerts.db                    # SQLite (gitignore)
├── src/
│   ├── __init__.py
│   ├── config.py                # 모든 파라미터 한 곳
│   ├── binance_client.py        # REST 호출
│   ├── swing_detector.py        # is_swing_high, find_swing_highs
│   ├── trendline.py             # build, check_breakout, classify
│   ├── filters.py               # F1~F4 필터
│   ├── alert_db.py              # SQLite 중복 방지
│   ├── telegram_notifier.py     # 메시지 발송
│   ├── analyzer.py              # 위 모듈들 조합
│   └── main.py                  # 진입점 + 스케줄러
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── sui_downtrend.json   # SUI 실제 캔들 (돌파 케이스)
    │   ├── ton_downtrend.json   # TON 실제 캔들
    │   └── kaito_uptrend.json
    ├── test_swing_detector.py
    ├── test_trendline.py
    ├── test_filters.py
    ├── test_alert_db.py
    └── test_analyzer.py         # 통합 테스트
```

### 2.2 데이터 모델

```python
# src/models.py — 모든 모듈 공유
from dataclasses import dataclass

@dataclass(frozen=True)
class Candle:
    open_time: int      # ms epoch
    open: float
    high: float
    low: float
    close: float
    volume: float       # base asset volume
    quote_volume: float # USDT volume

@dataclass(frozen=True)
class SwingHigh:
    idx: int
    high: float
    open_time: int

@dataclass(frozen=True)
class Trendline:
    p1: SwingHigh
    p2: SwingHigh
    slope: float            # high per bar
    slope_pct: float        # slope / p1.high

@dataclass(frozen=True)
class BreakoutSignal:
    symbol: str
    trendline: Trendline
    breakout_candle: Candle
    breakout_idx: int
    line_value: float
    label: str              # "🔥 다운트렌드 돌파" 등
    volume_ratio: float
```

### 2.3 중복 알람 방지 (SQLite 스키마)

```sql
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    p1_open_time INTEGER NOT NULL,    -- 첫 swing high 시점
    p2_open_time INTEGER NOT NULL,    -- 두 번째 swing high 시점
    breakout_open_time INTEGER NOT NULL,
    breakout_close REAL NOT NULL,
    line_value REAL NOT NULL,
    sent_at INTEGER NOT NULL,
    UNIQUE(symbol, p1_open_time, p2_open_time)
);
```

같은 (symbol, p1, p2) 조합은 한 번만 발송. 새 swing high가 추가되면 새 추세선 → 새 알람 가능.

---

## 3. Tasks

### Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `/Users/jevis/트레이딩뷰/pyproject.toml`
- Create: `/Users/jevis/트레이딩뷰/.gitignore`
- Create: `/Users/jevis/트레이딩뷰/.env.example`
- Create: `/Users/jevis/트레이딩뷰/src/__init__.py`
- Create: `/Users/jevis/트레이딩뷰/tests/__init__.py`

- [ ] **Step 1: pyproject.toml 작성**

```toml
[project]
name = "trendline-breakout-bot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "apscheduler>=3.10",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-mock>=3.12", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: .gitignore 작성**

```
.env
*.db
__pycache__/
.pytest_cache/
.venv/
venv/
*.pyc
```

- [ ] **Step 3: .env.example 작성**

```
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id
```

- [ ] **Step 4: 가상환경 + 의존성 설치**

Run:
```bash
cd /Users/jevis/트레이딩뷰
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```
Expected: 모든 패키지 정상 설치

- [ ] **Step 5: Commit**

```bash
git init && git add -A && git commit -m "chore: 프로젝트 스캐폴딩"
```

---

### Task 2: config.py — 파라미터 중앙화

**Files:**
- Create: `/Users/jevis/트레이딩뷰/src/config.py`

- [ ] **Step 1: config 작성**

```python
# src/config.py
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    # 알고리즘
    SWING_LOOKBACK: int = 5
    BREAKOUT_BUFFER: float = 0.003       # 0.3%
    MIN_SWING_DISTANCE: int = 10         # F1
    MAX_SWING_DISTANCE: int = 200        # F1
    MIN_BARS_AFTER_P2: int = 3           # F2
    VOLUME_RATIO_THRESHOLD: float = 1.3  # F4
    VOLUME_AVG_WINDOW: int = 20

    # 데이터 수집
    INTERVAL: str = "1d"
    KLINE_LIMIT: int = 250               # 약 8개월
    MIN_QUOTE_VOLUME_USDT: float = 50_000_000.0  # $50M
    BINANCE_FUTURES_BASE: str = "https://fapi.binance.com"

    # 텔레그램
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # 스케줄
    SCHEDULE_HOUR_UTC: int = 0     # UTC 00:05 = KST 09:05
    SCHEDULE_MINUTE: int = 5

    # 저장소
    DB_PATH: str = "alerts.db"

CFG = Config()
```

- [ ] **Step 2: Commit**

```bash
git add src/config.py && git commit -m "feat: 설정 중앙화"
```

---

### Task 3: models.py — 데이터 클래스

**Files:**
- Create: `/Users/jevis/트레이딩뷰/src/models.py`

- [ ] **Step 1: dataclass 정의**

위 §2.2의 `Candle`, `SwingHigh`, `Trendline`, `BreakoutSignal` 모두 작성.

- [ ] **Step 2: Commit**

```bash
git add src/models.py && git commit -m "feat: 데이터 모델 정의"
```

---

### Task 4: swing_detector.py — Swing High 검출 (TDD)

**Files:**
- Create: `tests/test_swing_detector.py`
- Create: `src/swing_detector.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_swing_detector.py
from src.models import Candle
from src.swing_detector import find_swing_highs

def make_candle(idx, high, low=None, close=None, vol=1000):
    low = low if low is not None else high - 1
    close = close if close is not None else high - 0.5
    return Candle(open_time=idx*86400000, open=close, high=high, low=low, close=close,
                  volume=vol, quote_volume=vol*close)

def test_simple_swing_high_in_middle():
    """11봉 중 가운데가 최고면 swing high"""
    candles = [make_candle(i, high=10) for i in range(11)]
    candles[5] = make_candle(5, high=20)
    swings = find_swing_highs(candles, lookback=5)
    assert len(swings) == 1
    assert swings[0].idx == 5
    assert swings[0].high == 20

def test_no_swing_at_edges():
    """좌우 5봉 미만이면 swing 인정 안 함"""
    candles = [make_candle(i, high=i+1) for i in range(11)]  # 단조 증가
    swings = find_swing_highs(candles, lookback=5)
    assert all(5 <= s.idx <= 5 for s in swings)  # idx 0~4, 6~10 제외

def test_two_swings():
    """두 개의 명확한 고점"""
    candles = [make_candle(i, high=10) for i in range(30)]
    candles[7] = make_candle(7, high=20)
    candles[20] = make_candle(20, high=25)
    swings = find_swing_highs(candles, lookback=5)
    assert [s.idx for s in swings] == [7, 20]

def test_no_swing_when_tied_neighbor():
    """동률이면 swing 아님 (== 비교)"""
    candles = [make_candle(i, high=10) for i in range(11)]
    candles[5] = make_candle(5, high=15)
    candles[6] = make_candle(6, high=15)  # 동률
    swings = find_swing_highs(candles, lookback=5)
    assert swings == []
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `pytest tests/test_swing_detector.py -v`
Expected: ImportError 또는 4 failures

- [ ] **Step 3: 최소 구현**

```python
# src/swing_detector.py
from typing import Sequence
from src.models import Candle, SwingHigh

def is_swing_high(candles: Sequence[Candle], i: int, lookback: int = 5) -> bool:
    if i < lookback or i >= len(candles) - lookback:
        return False
    window = candles[i - lookback : i + lookback + 1]
    window_max = max(c.high for c in window)
    if candles[i].high != window_max:
        return False
    # 동률이 다른 위치에 있으면 swing 아님
    return sum(1 for c in window if c.high == window_max) == 1

def find_swing_highs(candles: Sequence[Candle], lookback: int = 5) -> list[SwingHigh]:
    return [
        SwingHigh(idx=i, high=candles[i].high, open_time=candles[i].open_time)
        for i in range(len(candles))
        if is_swing_high(candles, i, lookback)
    ]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_swing_detector.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/swing_detector.py tests/test_swing_detector.py
git commit -m "feat(swing): Swing High 검출 + tests"
```

---

### Task 5: trendline.py — 추세선 + 돌파 판정 (TDD)

**Files:**
- Create: `tests/test_trendline.py`
- Create: `src/trendline.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_trendline.py
from src.models import SwingHigh, Candle
from src.trendline import build_trendline, line_value_at, check_breakout, classify

def sw(idx, high): return SwingHigh(idx=idx, high=high, open_time=idx*86400000)

def test_horizontal_line_value():
    p1, p2 = sw(0, 100), sw(10, 100)
    line = build_trendline(p1, p2)
    assert abs(line_value_at(line, 5) - 100) < 1e-6
    assert abs(line_value_at(line, 50) - 100) < 1e-6

def test_descending_line_value():
    p1, p2 = sw(0, 200), sw(10, 100)  # slope = -10/bar
    line = build_trendline(p1, p2)
    assert abs(line_value_at(line, 20) - 0) < 1e-6
    assert line.slope < 0

def test_breakout_above_buffer():
    p1, p2 = sw(0, 100), sw(10, 100)
    line = build_trendline(p1, p2)
    candle = Candle(0,0,0,0, close=100.5, volume=1, quote_volume=100)  # 0.5% > 0.3%
    assert check_breakout(line, candle, current_idx=15, buffer=0.003) is True

def test_no_breakout_within_buffer():
    p1, p2 = sw(0, 100), sw(10, 100)
    line = build_trendline(p1, p2)
    candle = Candle(0,0,0,0, close=100.2, volume=1, quote_volume=100)  # 0.2% < 0.3%
    assert check_breakout(line, candle, current_idx=15, buffer=0.003) is False

def test_classify_downtrend():
    p1, p2 = sw(0, 200), sw(50, 100)
    line = build_trendline(p1, p2)
    assert "다운트렌드" in classify(line)

def test_classify_box():
    p1, p2 = sw(0, 100.0), sw(50, 100.001)
    line = build_trendline(p1, p2)
    assert "박스" in classify(line)

def test_classify_rising():
    p1, p2 = sw(0, 100), sw(50, 150)
    line = build_trendline(p1, p2)
    assert "상승" in classify(line) or "Rising" in classify(line)
```

- [ ] **Step 2: 테스트 실행, 실패 확인**

Run: `pytest tests/test_trendline.py -v` → 7 failures

- [ ] **Step 3: 구현**

```python
# src/trendline.py
from src.models import Trendline, SwingHigh, Candle

def build_trendline(p1: SwingHigh, p2: SwingHigh) -> Trendline:
    if p2.idx == p1.idx:
        raise ValueError("두 swing high의 idx가 같음")
    slope = (p2.high - p1.high) / (p2.idx - p1.idx)
    slope_pct = slope / p1.high
    return Trendline(p1=p1, p2=p2, slope=slope, slope_pct=slope_pct)

def line_value_at(line: Trendline, idx: int) -> float:
    return line.p1.high + line.slope * (idx - line.p1.idx)

def check_breakout(line: Trendline, candle: Candle, current_idx: int, buffer: float) -> bool:
    line_now = line_value_at(line, current_idx)
    return candle.close > line_now * (1 + buffer)

FLAT_THRESHOLD = 1e-4  # 0.01% per bar

def classify(line: Trendline) -> str:
    if line.slope_pct < -FLAT_THRESHOLD:
        return "🔥 다운트렌드 돌파 (추세 반전)"
    if abs(line.slope_pct) <= FLAT_THRESHOLD:
        return "📦 박스권 돌파"
    return "⚡ 상승 저항 돌파"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_trendline.py -v` → 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/trendline.py tests/test_trendline.py
git commit -m "feat(trendline): 추세선 + 돌파 판정 + 분류 + tests"
```

---

### Task 6: filters.py — 신호 품질 필터 (TDD)

**Files:**
- Create: `tests/test_filters.py`
- Create: `src/filters.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_filters.py
from src.models import SwingHigh, Trendline, Candle
from src.filters import (
    passes_distance, passes_min_bars_after_p2,
    is_first_breakout, passes_volume_filter
)

def sw(idx, high): return SwingHigh(idx=idx, high=high, open_time=idx*86400000)
def tl(i1, h1, i2, h2):
    p1, p2 = sw(i1, h1), sw(i2, h2)
    slope = (h2 - h1) / (i2 - i1)
    return Trendline(p1=p1, p2=p2, slope=slope, slope_pct=slope/h1)

def candle(close, vol=1000):
    return Candle(0, close, close, close, close, vol, vol*close)

def test_distance_within_range():
    assert passes_distance(tl(0, 100, 50, 100), 10, 200) is True
    assert passes_distance(tl(0, 100, 5, 100), 10, 200) is False
    assert passes_distance(tl(0, 100, 250, 100), 10, 200) is False

def test_min_bars_after_p2():
    line = tl(0, 100, 50, 100)
    assert passes_min_bars_after_p2(line, current_idx=53, min_bars=3) is True
    assert passes_min_bars_after_p2(line, current_idx=52, min_bars=3) is False

def test_first_breakout_detection():
    """p2 이후 ~ current 이전 모든 봉의 종가가 line 아래여야 first breakout"""
    line = tl(0, 100, 5, 100)
    candles = [candle(99) for _ in range(10)]  # 모두 line 아래
    candles[9] = candle(101)                    # current만 돌파
    assert is_first_breakout(line, candles, current_idx=9) is True
    candles[7] = candle(102)                    # 중간에 이미 돌파
    assert is_first_breakout(line, candles, current_idx=9) is False

def test_volume_ratio():
    candles = [candle(100, vol=1000) for _ in range(20)]
    candles.append(candle(110, vol=2000))  # 2배
    assert passes_volume_filter(candles, current_idx=20, threshold=1.3, window=20) is True
    candles[20] = candle(110, vol=1100)    # 1.1배만
    assert passes_volume_filter(candles, current_idx=20, threshold=1.3, window=20) is False
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_filters.py -v` → all fail

- [ ] **Step 3: 구현**

```python
# src/filters.py
from typing import Sequence
from src.models import Trendline, Candle
from src.trendline import line_value_at

def passes_distance(line: Trendline, min_dist: int, max_dist: int) -> bool:
    d = line.p2.idx - line.p1.idx
    return min_dist <= d <= max_dist

def passes_min_bars_after_p2(line: Trendline, current_idx: int, min_bars: int) -> bool:
    return current_idx - line.p2.idx >= min_bars

def is_first_breakout(line: Trendline, candles: Sequence[Candle], current_idx: int) -> bool:
    """p2 직후 ~ current 직전까지 종가가 line을 넘은 적이 없어야 첫 돌파"""
    for i in range(line.p2.idx + 1, current_idx):
        if candles[i].close > line_value_at(line, i):
            return False
    return True

def passes_volume_filter(candles: Sequence[Candle], current_idx: int,
                         threshold: float, window: int) -> bool:
    if current_idx < window:
        return False
    avg = sum(c.volume for c in candles[current_idx - window : current_idx]) / window
    if avg <= 0:
        return False
    return candles[current_idx].volume / avg >= threshold
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_filters.py -v` → 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/filters.py tests/test_filters.py
git commit -m "feat(filters): 신호 품질 필터 F1~F4 + tests"
```

---

### Task 7: alert_db.py — 중복 방지 SQLite (TDD)

**Files:**
- Create: `tests/test_alert_db.py`
- Create: `src/alert_db.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/test_alert_db.py
import os, tempfile, pytest
from src.alert_db import AlertDB

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield AlertDB(path)
    os.remove(path)

def test_first_alert_recorded(db):
    assert db.was_alerted("BTCUSDT", 100, 200) is False
    db.record_alert("BTCUSDT", p1_open_time=100, p2_open_time=200,
                    breakout_open_time=300, breakout_close=50000.0, line_value=49500.0)
    assert db.was_alerted("BTCUSDT", 100, 200) is True

def test_different_trendline_separate(db):
    db.record_alert("BTCUSDT", 100, 200, 300, 50000.0, 49500.0)
    assert db.was_alerted("BTCUSDT", 100, 250) is False  # 다른 p2
    assert db.was_alerted("ETHUSDT", 100, 200) is False  # 다른 symbol
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_alert_db.py -v`

- [ ] **Step 3: 구현**

```python
# src/alert_db.py
import sqlite3, time

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    p1_open_time INTEGER NOT NULL,
    p2_open_time INTEGER NOT NULL,
    breakout_open_time INTEGER NOT NULL,
    breakout_close REAL NOT NULL,
    line_value REAL NOT NULL,
    sent_at INTEGER NOT NULL,
    UNIQUE(symbol, p1_open_time, p2_open_time)
);
"""

class AlertDB:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path)

    def was_alerted(self, symbol: str, p1_open_time: int, p2_open_time: int) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM alerts WHERE symbol=? AND p1_open_time=? AND p2_open_time=?",
                (symbol, p1_open_time, p2_open_time),
            ).fetchone()
        return row is not None

    def record_alert(self, symbol, p1_open_time, p2_open_time,
                     breakout_open_time, breakout_close, line_value):
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO alerts
                   (symbol, p1_open_time, p2_open_time, breakout_open_time,
                    breakout_close, line_value, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (symbol, p1_open_time, p2_open_time, breakout_open_time,
                 breakout_close, line_value, int(time.time())),
            )
```

- [ ] **Step 4: 통과 확인 + Commit**

```bash
pytest tests/test_alert_db.py -v
git add src/alert_db.py tests/test_alert_db.py
git commit -m "feat(db): 중복 알람 방지 SQLite"
```

---

### Task 8: binance_client.py — REST 호출

**Files:**
- Create: `src/binance_client.py`
- Create: `tests/test_binance_client.py` (mock 기반)

- [ ] **Step 1: mock 테스트 작성**

```python
# tests/test_binance_client.py
from unittest.mock import patch, MagicMock
from src.binance_client import BinanceFuturesClient

def test_select_symbols_filters_by_volume_and_usdt():
    fake = [
        {"symbol": "BTCUSDT", "quoteVolume": "1000000000"},
        {"symbol": "ETHUSDT", "quoteVolume": "500000000"},
        {"symbol": "DOGEUSDT", "quoteVolume": "10000000"},   # too low
        {"symbol": "BTCUSD_PERP", "quoteVolume": "1000000000"},  # not USDT
    ]
    with patch("src.binance_client.httpx.get") as g:
        g.return_value = MagicMock(json=lambda: fake, raise_for_status=lambda: None)
        c = BinanceFuturesClient()
        symbols = c.get_top_usdt_symbols(min_quote_volume=50_000_000)
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" in symbols
    assert "DOGEUSDT" not in symbols
    assert "BTCUSD_PERP" not in symbols
```

- [ ] **Step 2: 구현**

```python
# src/binance_client.py
import httpx
from src.models import Candle
from src.config import CFG

class BinanceFuturesClient:
    def __init__(self, base_url: str = CFG.BINANCE_FUTURES_BASE):
        self.base = base_url

    def get_top_usdt_symbols(self, min_quote_volume: float) -> list[str]:
        r = httpx.get(f"{self.base}/fapi/v1/ticker/24hr", timeout=15)
        r.raise_for_status()
        data = r.json()
        return sorted(
            [d["symbol"] for d in data
             if d["symbol"].endswith("USDT")
             and float(d["quoteVolume"]) >= min_quote_volume],
            key=lambda s: -float(next(d["quoteVolume"] for d in data if d["symbol"] == s)),
        )

    def get_klines(self, symbol: str, interval: str = "1d", limit: int = 250) -> list[Candle]:
        r = httpx.get(
            f"{self.base}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=15,
        )
        r.raise_for_status()
        return [
            Candle(
                open_time=int(k[0]),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
                quote_volume=float(k[7]),
            )
            for k in r.json()
        ]
```

- [ ] **Step 3: 통과 확인 + Commit**

```bash
pytest tests/test_binance_client.py -v
git add src/binance_client.py tests/test_binance_client.py
git commit -m "feat(binance): REST 클라이언트 — symbols + klines"
```

---

### Task 9: telegram_notifier.py — 알람 발송

**Files:**
- Create: `src/telegram_notifier.py`
- Create: `tests/test_telegram_notifier.py`

- [ ] **Step 1: 메시지 포맷터 테스트 작성**

```python
# tests/test_telegram_notifier.py
from src.models import SwingHigh, Trendline, Candle, BreakoutSignal
from src.telegram_notifier import format_message

def test_format_message_contains_essentials():
    line = Trendline(
        p1=SwingHigh(0, 200, 1700000000000),
        p2=SwingHigh(50, 100, 1704320000000),
        slope=-2.0, slope_pct=-0.01,
    )
    candle = Candle(1730000000000, 100, 105, 99, 104, 5000, 520000)
    sig = BreakoutSignal(
        symbol="SUIUSDT", trendline=line, breakout_candle=candle,
        breakout_idx=53, line_value=94.0,
        label="🔥 다운트렌드 돌파 (추세 반전)",
        volume_ratio=2.1,
    )
    msg = format_message(sig)
    assert "SUIUSDT" in msg
    assert "다운트렌드" in msg
    assert "104" in msg or "104.0" in msg
    assert "binance.com" in msg
```

- [ ] **Step 2: 구현**

```python
# src/telegram_notifier.py
import httpx
from datetime import datetime, timezone, timedelta
from src.models import BreakoutSignal
from src.config import CFG

KST = timezone(timedelta(hours=9))

def format_message(sig: BreakoutSignal) -> str:
    candle_time = datetime.fromtimestamp(sig.breakout_candle.open_time / 1000, tz=KST)
    line = sig.trendline
    p1_time = datetime.fromtimestamp(line.p1.open_time / 1000, tz=KST)
    p2_time = datetime.fromtimestamp(line.p2.open_time / 1000, tz=KST)
    pct_above = (sig.breakout_candle.close - sig.line_value) / sig.line_value * 100
    return (
        f"{sig.label}\n\n"
        f"💎 *{sig.symbol}*\n"
        f"🕐 {candle_time:%Y-%m-%d} (1d 마감)\n"
        f"💰 종가: `{sig.breakout_candle.close:.6g}`\n"
        f"📏 추세선값: `{sig.line_value:.6g}` (+{pct_above:.2f}%)\n"
        f"📈 거래량: 평균 대비 {sig.volume_ratio:.2f}x\n"
        f"📐 추세선: {p1_time:%y-%m-%d} ({line.p1.high:.6g}) → "
        f"{p2_time:%y-%m-%d} ({line.p2.high:.6g})\n\n"
        f"🔗 https://www.binance.com/en/futures/{sig.symbol}"
    )

def send_alert(sig: BreakoutSignal) -> None:
    if not CFG.TELEGRAM_BOT_TOKEN or not CFG.TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정")
    url = f"https://api.telegram.org/bot{CFG.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CFG.TELEGRAM_CHAT_ID,
        "text": format_message(sig),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    r = httpx.post(url, json=payload, timeout=15)
    r.raise_for_status()
```

- [ ] **Step 3: 통과 확인 + Commit**

```bash
pytest tests/test_telegram_notifier.py -v
git add src/telegram_notifier.py tests/test_telegram_notifier.py
git commit -m "feat(telegram): 메시지 포맷 + 발송"
```

---

### Task 10: analyzer.py — 통합 분석기 (TDD)

**Files:**
- Create: `src/analyzer.py`
- Create: `tests/test_analyzer.py`
- Create: `tests/fixtures/` (실제 캔들 JSON)

- [ ] **Step 1: 실제 데이터 fixture 받아오기**

수동 1회 실행:
```python
# 임시 스크립트
from src.binance_client import BinanceFuturesClient
import json
c = BinanceFuturesClient()
for sym in ["SUIUSDT", "TONUSDT", "POPCATUSDT", "KAITOUSDT", "BTCUSDT"]:
    candles = c.get_klines(sym, "1d", 250)
    with open(f"tests/fixtures/{sym.lower()}_1d.json", "w") as f:
        json.dump([c.__dict__ for c in candles], f)
```

- [ ] **Step 2: 통합 테스트 작성**

```python
# tests/test_analyzer.py
import json
from src.models import Candle
from src.analyzer import analyze_symbol

def load_fixture(name):
    with open(f"tests/fixtures/{name}_1d.json") as f:
        return [Candle(**d) for d in json.load(f)]

def test_btcusdt_no_false_alarm():
    """현재 BTC가 명확한 돌파 상태가 아니라면 None 반환"""
    candles = load_fixture("btcusdt")
    sig = analyze_symbol("BTCUSDT", candles)
    # 단순히 크래시 없이 None 또는 BreakoutSignal 반환

def test_no_swings_returns_none():
    """캔들이 너무 적으면 None"""
    candles = []
    assert analyze_symbol("FOO", candles) is None
```

- [ ] **Step 3: 구현**

```python
# src/analyzer.py
from typing import Optional
from src.models import Candle, BreakoutSignal
from src.swing_detector import find_swing_highs
from src.trendline import build_trendline, line_value_at, check_breakout, classify
from src.filters import (
    passes_distance, passes_min_bars_after_p2,
    is_first_breakout, passes_volume_filter,
)
from src.config import CFG

def analyze_symbol(symbol: str, candles: list[Candle]) -> Optional[BreakoutSignal]:
    if len(candles) < CFG.VOLUME_AVG_WINDOW + 2 * CFG.SWING_LOOKBACK + 1:
        return None
    swings = find_swing_highs(candles, CFG.SWING_LOOKBACK)
    if len(swings) < 2:
        return None
    line = build_trendline(swings[-2], swings[-1])
    current_idx = len(candles) - 1
    current = candles[current_idx]

    if not passes_distance(line, CFG.MIN_SWING_DISTANCE, CFG.MAX_SWING_DISTANCE):
        return None
    if not passes_min_bars_after_p2(line, current_idx, CFG.MIN_BARS_AFTER_P2):
        return None
    if not check_breakout(line, current, current_idx, CFG.BREAKOUT_BUFFER):
        return None
    if not is_first_breakout(line, candles, current_idx):
        return None
    if not passes_volume_filter(candles, current_idx,
                                CFG.VOLUME_RATIO_THRESHOLD, CFG.VOLUME_AVG_WINDOW):
        return None

    avg = sum(c.volume for c in candles[current_idx - CFG.VOLUME_AVG_WINDOW : current_idx]) / CFG.VOLUME_AVG_WINDOW
    return BreakoutSignal(
        symbol=symbol,
        trendline=line,
        breakout_candle=current,
        breakout_idx=current_idx,
        line_value=line_value_at(line, current_idx),
        label=classify(line),
        volume_ratio=current.volume / avg if avg > 0 else 0,
    )
```

- [ ] **Step 4: 통과 확인 + Commit**

```bash
pytest tests/test_analyzer.py -v
git add src/analyzer.py tests/test_analyzer.py tests/fixtures
git commit -m "feat(analyzer): 통합 분석기 + 실제 캔들 fixtures"
```

---

### Task 11: 백테스트 — SUI/TON 차트 검증

**Goal:** 사용자가 보여준 SUI/TON 차트의 돌파 캔들이 실제로 알람을 만들어내는지 확인.

**Files:**
- Create: `scripts/backtest.py`

- [ ] **Step 1: 스크립트 작성**

```python
# scripts/backtest.py
"""SUI/TON/POPCAT/KAITO 과거 캔들 슬라이딩 윈도우로 돌려보고
   언제 알람이 발생했는지 출력. 사용자 시각 차트와 비교."""
from src.binance_client import BinanceFuturesClient
from src.analyzer import analyze_symbol
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
SYMBOLS = ["SUIUSDT", "TONUSDT", "POPCATUSDT", "KAITOUSDT"]

def main():
    c = BinanceFuturesClient()
    for sym in SYMBOLS:
        full = c.get_klines(sym, "1d", 500)
        print(f"\n=== {sym} ===")
        # 슬라이딩: 각 봉을 "현재"로 가정하고 분석
        for end in range(50, len(full)):
            window = full[:end + 1]
            sig = analyze_symbol(sym, window)
            if sig:
                t = datetime.fromtimestamp(sig.breakout_candle.open_time / 1000, tz=KST)
                print(f"  📍 {t:%Y-%m-%d}  close={sig.breakout_candle.close:.6g}  "
                      f"line={sig.line_value:.6g}  {sig.label}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행해서 결과를 사용자 차트와 대조**

Run: `python scripts/backtest.py`
Expected: SUI/TON 차트에서 사용자가 동그라미 친 날짜 부근에 알람이 한 번씩 출력됨. 너무 많이 나오면 필터 임계값 조정 필요.

- [ ] **Step 3: 결과 리뷰 후 파라미터 튜닝**

가능한 조정:
- 너무 적게 나옴 → `BREAKOUT_BUFFER` 0.003 → 0.001, `VOLUME_RATIO_THRESHOLD` 1.3 → 1.1
- 너무 많이 나옴 (False positive) → 반대로 강화

- [ ] **Step 4: Commit**

```bash
git add scripts/backtest.py
git commit -m "feat(backtest): 과거 데이터 검증 스크립트"
```

---

### Task 12: main.py — 진입점 + 스케줄러

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: 작성**

```python
# src/main.py
import logging, time
from apscheduler.schedulers.blocking import BlockingScheduler
from src.binance_client import BinanceFuturesClient
from src.analyzer import analyze_symbol
from src.alert_db import AlertDB
from src.telegram_notifier import send_alert
from src.config import CFG

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("breakout-bot")

def run_once():
    log.info("스캔 시작")
    client = BinanceFuturesClient()
    db = AlertDB(CFG.DB_PATH)
    symbols = client.get_top_usdt_symbols(CFG.MIN_QUOTE_VOLUME_USDT)
    log.info("대상 심볼 수: %d", len(symbols))
    sent = 0
    for sym in symbols:
        try:
            candles = client.get_klines(sym, CFG.INTERVAL, CFG.KLINE_LIMIT)
            sig = analyze_symbol(sym, candles)
            if not sig:
                continue
            if db.was_alerted(sym, sig.trendline.p1.open_time, sig.trendline.p2.open_time):
                continue
            send_alert(sig)
            db.record_alert(
                sym, sig.trendline.p1.open_time, sig.trendline.p2.open_time,
                sig.breakout_candle.open_time, sig.breakout_candle.close, sig.line_value,
            )
            log.info("🚨 알람 발송: %s @ %.6g", sym, sig.breakout_candle.close)
            sent += 1
            time.sleep(0.2)  # rate limit
        except Exception as e:
            log.exception("심볼 처리 실패: %s — %s", sym, e)
    log.info("스캔 종료. 발송 %d건", sent)

def main():
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(run_once, "cron",
                  hour=CFG.SCHEDULE_HOUR_UTC, minute=CFG.SCHEDULE_MINUTE,
                  id="daily_scan")
    log.info("스케줄러 시작 (매일 UTC %02d:%02d / KST %02d:%02d)",
             CFG.SCHEDULE_HOUR_UTC, CFG.SCHEDULE_MINUTE,
             (CFG.SCHEDULE_HOUR_UTC + 9) % 24, CFG.SCHEDULE_MINUTE)
    # 시작 즉시 1회도 실행
    run_once()
    sched.start()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 수동 실행 테스트**

```bash
.venv/bin/python -m src.main
```
Expected: 스캔 로그가 흐르고, 알람이 있으면 텔레그램에 메시지 옴. 없으면 "발송 0건"으로 끝나고 스케줄러 대기.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat(main): 진입점 + 스케줄러"
```

---

### Task 13: 24시간 환경 배포 (선택)

PC가 항상 켜져 있다면 skip. Oracle Cloud Free Tier 사용 시:

- [ ] Oracle Cloud Free Tier 계정 생성
- [ ] Always Free VM (Ubuntu, ARM Ampere A1) 1대 프로비전
- [ ] SSH 접속, Python 3.11 설치
- [ ] 코드 git clone
- [ ] `.env` 작성
- [ ] `systemd` 서비스 등록 (자동 재시작):

```ini
# /etc/systemd/system/breakout-bot.service
[Unit]
Description=Trendline Breakout Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/트레이딩뷰
ExecStart=/home/ubuntu/트레이딩뷰/.venv/bin/python -m src.main
Restart=always
RestartSec=10
EnvironmentFile=/home/ubuntu/트레이딩뷰/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now breakout-bot
sudo journalctl -u breakout-bot -f   # 로그 확인
```

---

## 4. 검증 체크리스트

플랜 종료 후 확인:

- [ ] `pytest -q` → 모든 테스트 그린
- [ ] `python scripts/backtest.py` → SUI/TON 사용자 차트의 동그라미 날짜와 ±2일 이내에서 알람 발생
- [ ] `python -m src.main` 1회 실행 → 텔레그램에 메시지 도착 (또는 "0건"이라도 정상 종료)
- [ ] 같은 캔들 두 번 스캔해도 알람 1회만 (중복 방지)
- [ ] 새 swing high가 추가된 후 다시 돌파하면 알람 발생 (DB unique 키 동작)

## 5. 향후 확장 (이 플랜 밖)

- 4h / 1h 멀티 시간봉 동시 모니터링
- 추세선 그리는 점 2개 → 3개 이상이 닿는 직선 자동 탐색 (정밀도 ↑)
- 하락 후 돌파 vs 상승 중 돌파 분리 (이미 오른 코인은 무시)
- 차트 이미지 첨부 (matplotlib 또는 lightweight-charts 헤드리스 렌더)
- 종목별 알람 on/off 텔레그램 명령 지원
- 백테스트 → 승률/평균 수익률 통계
