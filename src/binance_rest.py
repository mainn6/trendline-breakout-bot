import httpx
from src.models import Candle
from src.config import CFG


class BinanceRest:
    def __init__(self, base_url: str = CFG.REST_BASE):
        self.base = base_url

    def get_top_usdt_symbols(self, min_quote_volume: float) -> list[str]:
        r = httpx.get(f"{self.base}/fapi/v1/ticker/24hr", timeout=15)
        r.raise_for_status()
        data = r.json()
        eligible = [
            (d["symbol"], float(d["quoteVolume"]))
            for d in data
            if d["symbol"].endswith("USDT") and float(d["quoteVolume"]) >= min_quote_volume
        ]
        eligible.sort(key=lambda x: -x[1])
        return [s for s, _ in eligible]

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
