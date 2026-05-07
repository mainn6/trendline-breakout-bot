# Trendline Breakout Alert Bot

Binance USDT 무기한 선물 시장에서 **1일봉 추세선(Trend Line) 돌파**를 자동 감지하여 Telegram으로 3단계 알람을 보내는 봇.

## 핵심 기능

- 거래량 ≥ $10M USDT 페어 자동 선정 (~170개, 매일 갱신)
- 매일 00:05 UTC에 추세선 자동 재계산 (Swing High 기반)
- **REST polling** 1분 주기 — Binance Futures (한국 IP에서도 동작)
- **3단계 알람**:
  - 🟡 **시도** — 가격이 추세선 +0.5% 돌파 + 거래량 1.5배
  - 🟠 **굳히기** — 1시간 동안 추세선 위 유지
  - 🟢 **확정** — 1일봉 종가가 추세선 위로 마감

## 알고리즘 (v3)

모든 Swing High 쌍 평가 후 점수 가장 높은 추세선 1개 선택:
- `score = (2 + touches) × 100 + length × 2 + proximity_bonus − above × 50`
- **touches**: 다른 swing high가 직선에 ±0.5% 이내 닿는 개수
- **length**: 추세선이 길수록 우선 (장기 추세선이 의미)
- **proximity**: 현재가가 추세선 ±10% 안일수록 가산
- 현재가가 추세선에서 ±50% 이상 벗어나면 제외 (이미 돌파한 옛 라인)
- 현재가가 추세선에서 ±10% 이상 벗어나면 제외 (이미 돌파한 옛 라인)

## 빠른 시작

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# .env 작성
cp .env.example .env
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 채우기

# 테스트
pytest -q

# 백테스트
python scripts/backtest.py

# 실행
python -m src.main
```

## 구조

```
src/
├── config.py              # 모든 파라미터
├── models.py              # dataclass: Candle / Trendline / Transition / ...
├── swing_detector.py      # Swing High (좌우 5봉 피벗)
├── trendline.py           # 추세선 계산 + 분류
├── filters.py             # 거리 / 첫 돌파 필터
├── analyzer.py            # 다중 swing 평가 → 최적 추세선 (v2)
├── state_machine.py       # 3단계 상태 머신 (INITIAL→ATTEMPT→HOLDING→CONFIRMED)
├── alert_db.py            # SQLite 영속화 + 중복 알람 방지
├── binance_rest.py        # REST: 심볼/캔들
├── binance_poller.py      # REST polling (1m/1d kline) — WS 대체
├── telegram_notifier.py   # 3종 메시지 포맷 + 발송
├── trendline_manager.py   # 추세선 캐시 + 매일 자동 재계산
└── main.py                # asyncio 진입점

tests/         # 41 tests
scripts/       # backtest.py, smoke_test.py
docs/superpowers/plans/    # 구현 계획서
```

## 라이선스

Personal use.
