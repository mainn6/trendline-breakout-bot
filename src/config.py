from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # === 추세선 알고리즘 (v4) ===
    SWING_LOOKBACK: int = 3                # v4: 5→3 (사용자 시각의 작은 swing 잡기)
    MIN_SWING_DISTANCE: int = 5
    MAX_SWING_DISTANCE: int = 250
    MIN_BARS_AFTER_P2: int = 3
    MAX_DISTANCE_FROM_LINE_PCT: float = 0.50
    LENGTH_BONUS_WEIGHT: float = 2.0
    MIN_TOUCHES: int = 1                   # v4: 추세선에 추가로 닿는 swing high 최소 (P1/P2 외)
    MIN_TREND_R2: float = 0.30             # v4: 가격 시계열의 linear fit R² (횡보 코인 제외)

    # === 3단계 알람 임계값 ===
    ATTEMPT_BREAKOUT_PCT: float = 0.005
    HOLDING_DURATION_MINUTES: int = 60
    VOLUME_RATIO_THRESHOLD: float = 1.5
    VOLUME_AVG_WINDOW_MINUTES: int = 60

    # === 심볼 필터 ===
    MIN_QUOTE_VOLUME_USDT: float = 10_000_000.0
    KLINE_LIMIT: int = 250

    # === Binance ===
    REST_BASE: str = "https://fapi.binance.com"
    WS_BASE: str = "wss://fstream.binance.com"

    # === 스케줄 ===
    DAILY_RECALC_HOUR_UTC: int = 0
    DAILY_RECALC_MINUTE: int = 5

    # === 텔레그램 ===
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    DB_PATH: str = "alerts.db"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


CFG = Config()
