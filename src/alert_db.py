import sqlite3
import time

from src.models import Trendline, StageState, TrackingState, Transition, SwingHigh

SCHEMA = """
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

CREATE TABLE IF NOT EXISTS tracking (
    symbol TEXT NOT NULL,
    p1_open_time INTEGER NOT NULL,
    p2_open_time INTEGER NOT NULL,
    state TEXT NOT NULL,
    attempt_started_ms INTEGER,
    last_above_line_ms INTEGER,
    consecutive_above_minutes INTEGER DEFAULT 0,
    updated_ms INTEGER NOT NULL,
    PRIMARY KEY (symbol, p1_open_time, p2_open_time)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    p1_open_time INTEGER NOT NULL,
    p2_open_time INTEGER NOT NULL,
    stage TEXT NOT NULL,
    sent_ms INTEGER NOT NULL,
    price REAL NOT NULL,
    line_value REAL NOT NULL,
    UNIQUE (symbol, p1_open_time, p2_open_time, stage)
);
"""


class AlertDB:
    def __init__(self, path: str):
        self.path = path
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def upsert_trendline(self, line: Trendline) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO trendlines
                   (symbol, p1_open_time, p2_open_time, p1_high, p2_high,
                    p1_idx, p2_idx, slope, last_seen_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (line.symbol, line.p1.open_time, line.p2.open_time,
                 line.p1.high, line.p2.high, line.p1.idx, line.p2.idx,
                 line.slope, int(time.time() * 1000)),
            )

    def save_state(self, ts: TrackingState) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO tracking
                   (symbol, p1_open_time, p2_open_time, state,
                    attempt_started_ms, last_above_line_ms,
                    consecutive_above_minutes, updated_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts.symbol, ts.trendline.p1.open_time, ts.trendline.p2.open_time,
                 ts.state.value, ts.attempt_started_ms, ts.last_above_line_ms,
                 ts.consecutive_above_minutes, int(time.time() * 1000)),
            )

    def was_alerted(self, symbol: str, p1_open_time: int, p2_open_time: int,
                    stage: StageState) -> bool:
        with self._conn() as c:
            row = c.execute(
                """SELECT 1 FROM alerts WHERE symbol=? AND p1_open_time=?
                   AND p2_open_time=? AND stage=?""",
                (symbol, p1_open_time, p2_open_time, stage.value),
            ).fetchone()
        return row is not None

    def record_alert(self, t: Transition) -> bool:
        """발송 기록. 이미 있으면 False (중복), 신규면 True."""
        try:
            with self._conn() as c:
                c.execute(
                    """INSERT INTO alerts
                       (symbol, p1_open_time, p2_open_time, stage,
                        sent_ms, price, line_value)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (t.symbol, t.trendline.p1.open_time, t.trendline.p2.open_time,
                     t.to_state.value, int(time.time() * 1000), t.price, t.line_value),
                )
            return True
        except sqlite3.IntegrityError:
            return False
