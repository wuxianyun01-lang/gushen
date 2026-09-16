from __future__ import annotations

from typing import Any


def evaluate_signal(holding: dict[str, Any], quote: dict[str, Any] | None, indicators: dict[str, Any] | None, news: list[dict[str, str]]) -> dict[str, Any]:
    kind = holding.get("type")
    if kind == "fund":
        return _evaluate_fund(holding, quote)
    if not quote:
        return {"signal": "continue", "action": "继续持有", "message": "等待行情数据", "severity": "info"}
    price = float(quote.get("price", 0) or 0)
    if price <= 0:
        return {"signal": "continue", "action": "继续持有", "message": "等待有效行情数据", "severity": "info"}
    ind = indicators or {}
    prev = float(quote.get("prev_close") or price)
    change_pct = ((price / prev) - 1) * 100 if prev else 0.0
    baseline = float(holding.get("baseline_price") or price)
    target = round(baseline * 1.05, 4)
    distance = ((target / price) - 1) * 100 if price else 0.0
    support = float(holding.get("support") or 0)
    resistance = float(holding.get("resistance") or 0)
    rsi = ind.get("rsi14")
    volume_ratio = ind.get("volume_ratio")
    macd = ind.get("macd")
    macd_signal = ind.get("macd_signal")

    if distance <= 0.2:
        return {"signal": "take_profit", "action": "触发5%止盈", "message": f"当前价 {price} 已达到目标 {target}", "severity": "critical"}
    if price >= resistance and volume_ratio and volume_ratio >= 1.5:
        return {"signal": "breakout", "action": "放量突破", "message": f"价格 {price} 站上压力 {resistance}，量比 {volume_ratio}", "severity": "high"}
    if rsi is not None and rsi < 30 and price > support:
        return {"signal": "low_buy", "action": "低吸机会", "message": f"RSI {rsi} 超卖，价格仍在支撑 {support} 上方", "severity": "medium"}
    if rsi is not None and rsi > 75:
        return {"signal": "reduce", "action": "反弹减仓", "message": f"RSI {rsi} 超买，建议逢反弹减仓", "severity": "high"}
    if price < support:
        return {"signal": "weak", "action": "趋势转弱", "message": f"价格 {price} 跌破支撑 {support}，回本概率下降", "severity": "high"}
    if macd is not None and macd_signal is not None and macd < macd_signal and change_pct < -1:
        return {"signal": "weak", "action": "趋势转弱", "message": "MACD转弱且日内走低，暂不补仓", "severity": "medium"}
    if distance <= 2:
        return {"signal": "near_target", "action": "接近5%止盈", "message": f"距目标价 {target} 还有 {distance:.1f}%", "severity": "medium"}
    return {"signal": "continue", "action": "继续持有", "message": f"距目标价 {target} 还有 {distance:.1f}%", "severity": "info"}


def _evaluate_fund(holding: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    baseline = float(holding.get("baseline_amount") or 0)
    current = float(holding.get("amount") or 0)
    if not snapshot:
        return {"signal": "continue", "action": "继续持有", "message": "等待基金净值更新", "severity": "info"}
    nav_change = float(snapshot.get("nav_change_pct") or 0)
    target = round(baseline * 1.05, 2)
    distance = ((target / current) - 1) * 100 if current else 0.0
    if distance <= 0.5:
        return {"signal": "take_profit", "action": "触发5%止盈", "message": f"持仓金额 {current} 已接近目标 {target}", "severity": "critical"}
    if nav_change <= -2:
        return {"signal": "weak", "action": "趋势转弱", "message": f"基金日跌 {nav_change:.2f}%，暂不补仓", "severity": "medium"}
    return {"signal": "continue", "action": "继续持有", "message": f"距目标金额 {target} 还有 {distance:.1f}%", "severity": "info"}
