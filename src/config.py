from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    SWING_LOOKBACK: int = 5
    MIN_SWING_DISTANCE: int = 5      # KAITO 같은 단기 라인도 잡기
    MAX_SWING_DISTANCE: int = 250
    MIN_BARS_AFTER_P2: int = 3
    MAX_DISTANCE_FROM_LINE_PCT: float = 0.10   # 현재가가 라인에서 ±10% 안에 있는 라인만 추적

    ATTEMPT_BREAKOUT_PCT: float = 0.005
    HOLDING_DURATION_MINUTES: int = 60
    VOLUME_RATIO_THRESHOLD: float = 1.5
    VOLUME_AVG_WINDOW_MINUTES: int = 60

    MIN_QUOTE_VOLUME_USDT: float = 10_000_000.0
    KLINE_LIMIT: int = 250

    REST_BASE: str = "https://fapi.binance.com"
    WS_BASE: str = "wss://fstream.binance.com"

    DAILY_RECALC_HOUR_UTC: int = 0
    DAILY_RECALC_MINUTE: int = 5

    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    DB_PATH: str = "alerts.db"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


CFG = Config()
