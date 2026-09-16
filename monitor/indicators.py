from __future__ import annotations

import statistics
from typing import Any

from .data_providers import fetch_history


def calculate_indicators(code: str, market: str, history: list[dict[str, float | str]] | None = None) -> dict[str, Any]:
    history = history if history is not None else fetch_history(code, market)
    closes = [float(row["close"]) for row in history]
    volumes = [float(row["volume"]) for row in history]
    if len(closes) < 2:
        return {"ma5": None, "ma20": None, "rsi14": None, "macd": None, "macd_signal": None, "volume_ratio": None}
    ma5 = statistics.fmean(closes[-5:]) if len(closes) >= 5 else None
    ma20 = statistics.fmean(closes[-20:]) if len(closes) >= 20 else None
    rsi14 = _rsi(closes, 14)
    dif, dea, hist = _macd(closes)
    volume_ratio = volumes[-1] / (statistics.fmean(volumes[-6:-1]) if len(volumes) >= 6 and statistics.fmean(volumes[-6:-1]) else 1)
    return {
        "ma5": round(ma5, 4) if ma5 is not None else None,
        "ma20": round(ma20, 4) if ma20 is not None else None,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "macd": round(dif, 4),
        "macd_signal": round(dea, 4),
        "macd_hist": round(hist, 4),
        "volume_ratio": round(volume_ratio, 2),
    }


def _rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = statistics.fmean(gains[-period:])
    avg_loss = statistics.fmean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * k + result[-1] * (1 - k))
    return result


def _macd(prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float]:
    if len(prices) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)
    dif = [a - b for a, b in zip(ema_fast, ema_slow)]
    dea = _ema(dif, signal)
    hist = (dif[-1] - dea[-1]) * 2
    return dif[-1], dea[-1], hist
