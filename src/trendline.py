from src.models import Trendline, SwingHigh, Candle


FLAT_THRESHOLD = 1e-4


def build_trendline(symbol: str, p1: SwingHigh, p2: SwingHigh, current_idx: int) -> Trendline:
    if p2.idx == p1.idx:
        raise ValueError("두 swing high의 idx가 같음")
    slope = (p2.high - p1.high) / (p2.idx - p1.idx)
    slope_pct = slope / p1.high
    return Trendline(
        symbol=symbol, p1=p1, p2=p2,
        slope=slope, slope_pct=slope_pct,
        created_at_idx=current_idx,
    )


def line_value_at(line: Trendline, idx: int) -> float:
    return line.p1.high + line.slope * (idx - line.p1.idx)


def classify(line: Trendline) -> str:
    if line.slope_pct < -FLAT_THRESHOLD:
        return "🔥 다운트렌드 돌파 (추세 반전)"
    if abs(line.slope_pct) <= FLAT_THRESHOLD:
        return "📦 박스권 돌파"
    return "⚡ 상승 저항 돌파"


def classify_en(line: Trendline) -> str:
    if line.slope_pct < -FLAT_THRESHOLD:
        return "Downtrend Break"
    if abs(line.slope_pct) <= FLAT_THRESHOLD:
        return "Range Break"
    return "Rising Resistance Break"


STAGE_LABEL_EN = {
    "attempt": "ATTEMPT",
    "holding": "HOLDING",
    "confirmed": "CONFIRMED",
}
