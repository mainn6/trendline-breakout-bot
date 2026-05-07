"""봇 부팅 전 1번 실행: 현재 모든 추세선의 모든 stage를 "이미 발송됨"으로 마크.

목적: 봇 부팅 시 가격이 이미 추세선 위에 있는 코인들이 일제히 ATTEMPT 알람을
보내는 폭탄 방지. 새 추세선이 형성될 때만 알람.
"""
import sqlite3
import time

from src.alert_db import AlertDB
from src.binance_rest import BinanceRest
from src.config import CFG
from src.models import StageState
from src.trendline_manager import TrendlineManager


def main():
    rest = BinanceRest()
    db = AlertDB(CFG.DB_PATH)
    tm = TrendlineManager(rest, db)
    lines_by_symbol = tm.refresh_all()

    count = 0
    skipped = 0
    now_ms = int(time.time() * 1000)
    with sqlite3.connect(CFG.DB_PATH) as conn:
        for symbol, lines in lines_by_symbol.items():
            for line in lines:
                for stage in (StageState.ATTEMPT, StageState.HOLDING, StageState.CONFIRMED):
                    try:
                        conn.execute(
                            """INSERT INTO alerts
                               (symbol, p1_open_time, p2_open_time, stage,
                                sent_ms, price, line_value)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (symbol, line.p1.open_time, line.p2.open_time,
                             stage.value, now_ms, 0.0, 0.0),
                        )
                        count += 1
                    except sqlite3.IntegrityError:
                        skipped += 1
    print(f"✅ Dummy alert 기록: 신규 {count}개, 이미 있음 {skipped}개")
    print("이제 봇 재시작해도 부팅 폭탄 없음. 새 추세선 형성 시만 알람.")


if __name__ == "__main__":
    main()
