from __future__ import annotations

import datetime as dt
import math
import statistics
from typing import Any


POSITIVE_TERMS = [
    "上涨", "拉升", "涨停", "增长", "利好", "回暖", "反弹", "突破", "净流入",
    "创新高", "增持", "回购", "中标", "签约", "扩产", "超预期", "加速", "放量",
    "新纳入", "修复", "景气", "领涨", "底部反转",
]
NEGATIVE_TERMS = [
    "下跌", "跌停", "下滑", "下降", "利空", "减持", "亏损", "走弱", "跌破",
    "净流出", "退潮", "承压", "风险", "处罚", "调查", "下调", "低迷", "回落",
    "失守", "卖压", "恶化", "减仓", "资金流出",
]


def predict_position(
    holding: dict[str, Any],
    quote: dict[str, Any] | None,
    indicators: dict[str, Any] | None,
    history: list[dict[str, float | str]] | None,
    news: list[dict[str, str]],
    prediction_config: dict[str, Any] | None = None,
    community: list[dict[str, Any]] | None = None,
    learning: Any | None = None,
) -> dict[str, Any]:
    kind = holding.get("type")
    code = holding.get("code", "")
    if kind == "fund":
        return _predict_fund(holding, quote, history, news, prediction_config, learning)
    if not quote or not float(quote.get("price") or 0):
        return _unavailable("等待有效行情")

    price = float(quote["price"])
    closes = [float(row["close"]) for row in history or [] if float(row.get("close") or 0) > 0]
    volumes = [float(row.get("volume") or 0) for row in history or []]
    if len(closes) < 25:
        return _technical_fallback(holding, quote, indicators)

    support = float(holding.get("support") or price * 0.97)
    resistance = float(holding.get("resistance") or price * 1.03)
    target = float(holding.get("baseline_price") or price) * 1.05
    config = prediction_config or {}
    threshold = float(config.get("confidence_threshold", 0.62))
    series = _rolling_series(closes, volumes)
    current_features = series["features"][-1]
    if current_features is None:
        return _technical_fallback(holding, quote, indicators)

    model = _fit_model(series)
    model_probability = _apply_model(model, current_features)
    sentiment = _sentiment(holding, news, community)
    master = _master_adjustment(
        holding,
        price,
        indicators or {},
        current_features,
        sentiment["score"],
        support,
    )

    weights = (config or {}).get("weights") or {}
    trend_signal = _trend_signal(price, indicators or {}, current_features)
    ta_signal = _load_ta_signal(code)
    raw_probability = (
        model_probability
        + master["adjustment"] * float(weights.get("master", 1.0))
        + sentiment["score"] * float(weights.get("sentiment", 0.15))
        + trend_signal * float(weights.get("trend", 0.10))
        + (ta_signal or 0.0) * float(weights.get("ta", 0.10))
    )
    up_probability = max(0.05, min(0.95, raw_probability))
    expected_return = _expected_return(series["forward_returns"], up_probability)
    price_range = _price_range(price, series["forward_returns"])
    risk_reward = _risk_reward(price, support, resistance)
    confidence = _confidence(model, len(series["samples"]), sentiment["coverage"])
    if learning is not None:
        up_probability, confidence, expected_return = learning.apply_calibration(
            code,
            up_probability,
            confidence,
            expected_return,
        )
    pre_action = _decide_pre_action(
        price,
        support,
        resistance,
        target,
        up_probability,
        expected_return,
        master["score"],
        sentiment["score"],
        threshold,
        confidence,
    )

    return {
        "horizon": "T+1交易日",
        "up_probability": round(up_probability, 3),
        "down_probability": round(1 - up_probability, 3),
        "expected_return_pct": round(expected_return, 2),
        "risk_reward": round(risk_reward, 2),
        "volatility_pct": round(series["volatility"] * 100, 2),
        "price_range": price_range,
        "trigger_buy": round(min(support * 1.005, price * 0.99), 4),
        "trigger_sell": round(resistance, 4),
        "confidence": round(confidence, 3),
        "model_accuracy": round(model["accuracy"], 3),
        "method": model["method"],
        "sentiment": sentiment,
        "master": master,
        "action": pre_action["action"],
        "severity": pre_action["severity"],
        "trigger": pre_action["trigger"],
        "reason": pre_action["reason"],
    }


def _predict_fund(
    holding: dict[str, Any],
    snapshot: dict[str, Any] | None,
    history: list[dict[str, float | str]] | None,
    news: list[dict[str, str]],
    prediction_config: dict[str, Any] | None,
    learning: Any | None,
) -> dict[str, Any]:
    nav = float((snapshot or {}).get("nav") or 0)
    rows = history or []
    closes = [float(row["close"]) for row in rows if float(row.get("close") or 0) > 0]
    if nav and (not closes or abs(closes[-1] - nav) > 1e-6):
        closes.append(nav)
    if len(closes) < 25:
        change = float((snapshot or {}).get("nav_change_pct") or 0)
        up_probability = max(0.2, min(0.8, 0.5 + change / 10))
        return {
            "horizon": "下一净值日",
            "up_probability": round(up_probability, 3),
            "down_probability": round(1 - up_probability, 3),
            "expected_return_pct": round(change, 2),
            "risk_reward": 0.0,
            "volatility_pct": 0.0,
            "price_range": {"p25": None, "median": nav or None, "p75": None},
            "trigger_buy": None,
            "trigger_sell": None,
            "confidence": 0.45,
            "model_accuracy": 0.0,
            "method": "净值变化占位模型",
            "sentiment": _sentiment(holding, news),
            "master": {"score": 0.0, "stance": "中性", "notes": [], "adjustment": 0.0},
            "action": "预判观望",
            "severity": "info",
            "trigger": "净值站上5日均线后再加仓",
            "reason": "历史净值不足，仅用最新净值变化做占位判断",
        }

    volumes = [1.0] * len(closes)
    series = _rolling_series(closes, volumes, include_volume=False)
    current_features = series["features"][-1]
    if current_features is None:
        return _unavailable("基金历史样本不足")
    model = _fit_model(series)
    model_probability = _apply_model(model, current_features)
    sentiment = _sentiment(holding, news)
    master = _master_adjustment(holding, nav, {}, current_features, sentiment["score"], nav * 0.97)
    weights = (prediction_config or {}).get("weights") or {}
    trend_signal = _trend_signal(nav, {}, current_features)
    ta_signal = _load_ta_signal(holding.get("code", ""))
    up_probability = max(0.05, min(0.95,
        model_probability
        + master["adjustment"] * float(weights.get("master", 1.0))
        + sentiment["score"] * float(weights.get("sentiment", 0.15))
        + trend_signal * float(weights.get("trend", 0.10))
        + (ta_signal or 0.0) * float(weights.get("ta", 0.10))
    ))
    expected_return = _expected_return(series["forward_returns"], up_probability)
    price_range = _price_range(nav, series["forward_returns"])
    one_day_band = max(series["volatility"], 0.003)
    support = max(min(closes[-20:]) * 0.995, nav * (1 - one_day_band))
    resistance = min(max(closes[-20:]) * 1.005, nav * (1 + one_day_band))
    risk_reward = _risk_reward(nav, support, resistance)
    confidence = _confidence(model, len(series["samples"]), sentiment["coverage"])
    if learning is not None:
        up_probability, confidence, expected_return = learning.apply_calibration(
            holding.get("code", ""),
            up_probability,
            confidence,
            expected_return,
        )
    threshold = float((prediction_config or {}).get("confidence_threshold", 0.62))
    pre_action = _decide_pre_action(
        nav,
        support,
        resistance,
        nav * 1.05,
        up_probability,
        expected_return,
        master["score"],
        sentiment["score"],
        threshold,
        confidence,
    )
    return {
        "horizon": "下一净值日",
        "up_probability": round(up_probability, 3),
        "down_probability": round(1 - up_probability, 3),
        "expected_return_pct": round(expected_return, 2),
        "risk_reward": round(risk_reward, 2),
        "volatility_pct": round(series["volatility"] * 100, 2),
        "price_range": price_range,
        "trigger_buy": round(support, 4),
        "trigger_sell": round(resistance, 4),
        "confidence": round(confidence, 3),
        "model_accuracy": round(model["accuracy"], 3),
        "method": model["method"],
        "sentiment": sentiment,
        "master": master,
        "action": pre_action["action"],
        "severity": pre_action["severity"],
        "trigger": pre_action["trigger"],
        "reason": pre_action["reason"],
    }


def _rolling_series(closes: list[float], volumes: list[float], include_volume: bool = True) -> dict[str, Any]:
    returns = [0.0] + [
        closes[i] / closes[i - 1] - 1 if closes[i - 1] else 0.0
        for i in range(1, len(closes))
    ]
    ma5 = [None] * len(closes)
    ma20 = [None] * len(closes)
    rsi14 = [None] * len(closes)
    macd_hist = [None] * len(closes)
    volume_ratio = [None] * len(closes)
    volatility = [None] * len(closes)
    for i in range(1, len(closes)):
        if i >= 4:
            ma5[i] = statistics.fmean(closes[i - 4:i + 1])
        if i >= 19:
            ma20[i] = statistics.fmean(closes[i - 19:i + 1])
        if i >= 14:
            rsi14[i] = _rsi(closes[:i + 1], 14)
        if i >= 4:
            volatility[i] = statistics.pstdev(returns[max(0, i - 4):i + 1])
    if len(closes) >= 35:
        macd_hist = _macd_histogram(closes)
    if include_volume and len(volumes) == len(closes):
        for i in range(5, len(closes)):
            prior = [v for v in volumes[i - 5:i] if v > 0]
            average = statistics.fmean(prior) if prior else 0.0
            volume_ratio[i] = volumes[i] / average if average else 1.0

    features: list[list[float] | None] = [None] * len(closes)
    for i in range(20, len(closes)):
        if ma20[i] is None or rsi14[i] is None or macd_hist[i] is None:
            continue
        ret5 = closes[i] / closes[i - 5] - 1 if closes[i - 5] else 0.0
        distance_ma20 = closes[i] / ma20[i] - 1
        rsi_z = (rsi14[i] - 50) / 50
        macd_z = macd_hist[i] / closes[i] if closes[i] else 0.0
        volume_log = math.log(max(volume_ratio[i] or 0.1, 0.1))
        current_volatility = volatility[i] or 0.0
        trend_slope = ma5[i] / ma20[i] - 1
        features[i] = [
            ret5,
            distance_ma20,
            rsi_z,
            macd_z,
            volume_log,
            current_volatility,
            trend_slope,
        ]

    samples: list[list[float]] = []
    outcomes: list[int] = []
    forward_returns: list[float] = []
    for i in range(20, len(closes) - 1):
        if features[i] is None:
            continue
        samples.append(features[i])
        outcomes.append(1 if closes[i + 1] > closes[i] else 0)
        forward_returns.append(closes[i + 1] / closes[i] - 1 if closes[i] else 0.0)
    return {
        "features": features,
        "samples": samples,
        "outcomes": outcomes,
        "forward_returns": forward_returns,
        "volatility": statistics.pstdev(returns[-10:]) if len(returns) >= 10 else 0.01,
    }


def _fit_model(series: dict[str, Any]) -> dict[str, Any]:
    samples = series["samples"]
    outcomes = series["outcomes"]
    if len(samples) < 24 or sum(outcomes) < 5 or len(outcomes) - sum(outcomes) < 5:
        return {
            "weights": None,
            "means": [0.0] * len(samples[0]) if samples else [],
            "stds": [1.0] * len(samples[0]) if samples else [],
            "accuracy": 0.5,
            "method": "技术因子评分模型",
        }

    standardized, means, stds = _standardize(samples)
    split = max(20, int(len(samples) * 0.75))
    holdout_x = standardized[split:]
    holdout_y = outcomes[split:]
    holdout_weights = _logistic_fit(standardized[:split], outcomes[:split]) if split >= 20 else None
    holdout_accuracy = 0.5
    if holdout_weights is not None and holdout_x and len(set(holdout_y)) == 2:
        predictions = [1 if _logistic_probability(holdout_weights, row) >= 0.5 else 0 for row in holdout_x]
        holdout_accuracy = sum(a == b for a, b in zip(predictions, holdout_y)) / len(holdout_y)
    final_weights = _logistic_fit(standardized, outcomes)
    return {
        "weights": final_weights,
        "means": means,
        "stds": stds,
        "accuracy": holdout_accuracy if holdout_weights is not None else 0.5,
        "method": "L2逻辑回归+技术因子集成",
    }


def _logistic_fit(x: list[list[float]], y: list[int]) -> list[float] | None:
    if not x or len(set(y)) < 2:
        return None
    rows = [[1.0, *row] for row in x]
    weights = [0.0] * len(rows[0])
    learning_rate = 0.12
    l2 = 0.8
    for _ in range(350):
        gradients = [0.0] * len(weights)
        for row, target in zip(rows, y):
            probability = _logistic_probability(weights, row)
            error = probability - target
            for j, value in enumerate(row):
                gradients[j] += error * value
        for j in range(len(weights)):
            regularization = l2 * weights[j] if j else 0.0
            weights[j] -= learning_rate * (gradients[j] / len(rows) + regularization)
    return weights


def _apply_model(model: dict[str, Any], features: list[float]) -> float:
    if model.get("weights") is None:
        return 0.5 + 0.16 * (features[2] if len(features) > 2 else 0.0) + 0.12 * (features[1] if len(features) > 1 else 0.0)
    standardized: list[float] = []
    for index, value in enumerate(features):
        mean = model["means"][index]
        std = model["stds"][index]
        standardized.append(max(-4.0, min(4.0, (value - mean) / std)))
    return _logistic_probability(model["weights"], [1.0, *standardized])


def _logistic_probability(weights: list[float], row: list[float]) -> float:
    score = sum(weight * value for weight, value in zip(weights, row))
    if score >= 0:
        return 1.0 / (1.0 + math.exp(-score))
    exp_score = math.exp(score)
    return exp_score / (1.0 + exp_score)


def _standardize(samples: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    width = len(samples[0])
    means: list[float] = []
    stds: list[float] = []
    for j in range(width):
        values = [row[j] for row in samples]
        means.append(statistics.fmean(values))
        stds.append(statistics.pstdev(values) or 1.0)
    rows = [
        [max(-4.0, min(4.0, (row[j] - means[j]) / stds[j])) for j in range(width)]
        for row in samples
    ]
    return rows, means, stds


def _sentiment(
    holding: dict[str, Any],
    news: list[dict[str, str]],
    community: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    keywords = [str(keyword).strip() for keyword in holding.get("keywords", []) if keyword]
    matched: list[dict[str, Any]] = []
    for item in news or []:
        text = f"{item.get('title', '')} {item.get('digest', '')}"
        relevant = bool(keywords) and any(keyword in text for keyword in keywords)
        if not relevant:
            continue
        positives = sum(text.count(term) for term in POSITIVE_TERMS)
        negatives = sum(text.count(term) for term in NEGATIVE_TERMS)
        score = (positives - negatives) / max(1, positives + negatives)
        matched.append({
            "title": item.get("title", ""),
            "score": max(-1.0, min(1.0, score)),
            "time": item.get("time", ""),
            "url": item.get("url", ""),
            "weight": _freshness_weight(item.get("time", "")),
        })
    for post in community or []:
        text = f"{post.get('title', '')} {post.get('digest', '')}"
        positives = sum(text.count(term) for term in POSITIVE_TERMS)
        negatives = sum(text.count(term) for term in NEGATIVE_TERMS)
        score = (positives - negatives) / max(1, positives + negatives)
        engagement = float(post.get("read_count") or 0) + float(post.get("comment_count") or 0) * 10
        weight = min(1.2, 0.6 + math.log1p(max(engagement, 1)) / 12)
        matched.append({
            "title": post.get("title", ""),
            "score": max(-1.0, min(1.0, score)),
            "time": post.get("time", ""),
            "url": post.get("url", ""),
            "weight": weight,
        })
    if not matched:
        return {"score": 0.0, "coverage": 0.0, "positive": 0, "negative": 0, "items": []}
    weighted = sum(item["score"] * item.get("weight", 1.0) for item in matched)
    total_weight = sum(item.get("weight", 1.0) for item in matched)
    score = max(-1.0, min(1.0, weighted / max(total_weight, 1.0)))
    return {
        "score": round(score, 3),
        "coverage": round(min(1.0, len(matched) / 4), 2),
        "positive": sum(item["score"] > 0 for item in matched),
        "negative": sum(item["score"] < 0 for item in matched),
        "items": matched[:3],
    }


def _freshness_weight(value: str) -> float:
    try:
        stamp = dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            stamp = dt.datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            return 0.5
    age_hours = max(0.0, (dt.datetime.now() - stamp).total_seconds() / 3600)
    return 1.0 if age_hours <= 6 else 0.7 if age_hours <= 24 else 0.4


def _trend_signal(price: float, indicators: dict[str, Any], features: list[float]) -> float:
    """趋势规则量化：上升趋势=+1，下跌趋势=-1，横盘=0。"""
    ma5 = indicators.get("ma5")
    ma20 = indicators.get("ma20")
    if ma5 is not None and ma20 is not None:
        ma5 = float(ma5)
        ma20 = float(ma20)
        if price > ma5 > ma20:
            return 1.0
        if price < ma5 < ma20:
            return -1.0
        if ma5 > ma20:
            return 0.5
        if ma5 < ma20:
            return -0.5
        return 0.0
    slope = features[6] if len(features) > 6 else 0.0
    return max(-1.0, min(1.0, float(slope) * 20))


def _load_ta_signal(code: str) -> float | None:
    """读取 TradingAgents-CN 多智能体分析缓存的信号，无缓存返回 None。"""
    try:
        from .ta_bridge import load_signal
        return load_signal(code)
    except Exception:
        return None


def _master_adjustment(
    holding: dict[str, Any],
    price: float,
    indicators: dict[str, Any],
    features: list[float],
    sentiment: float,
    support: float,
) -> dict[str, Any]:
    masters = holding.get("masters", [])
    value_styles = {"buffett", "graham", "rossman", "sivy"}
    growth_styles = {"lynch", "friess", "oelschlager"}
    is_value = any(name in value_styles for name in masters)
    is_growth = any(name in growth_styles for name in masters)
    rsi = float(indicators.get("rsi14") or 50)
    macd_hist = float(indicators.get("macd_hist") or 0)
    distance_ma20 = features[1] if len(features) > 1 else 0.0
    adjustment = 0.0
    notes: list[str] = []
    if is_growth:
        if distance_ma20 > 0 and macd_hist > 0:
            adjustment += 0.05
            notes.append("林奇/佛莱斯：价格与动能同向，允许右侧确认")
        else:
            adjustment -= 0.08
            notes.append("林奇/佛莱斯：趋势未确认，不猜底")
    if is_value:
        if rsi < 32 and price > support and macd_hist > 0:
            adjustment += 0.04
            notes.append("巴菲特/格雷厄姆：超卖但开始修复，小仓试错")
        elif price <= support or sentiment <= -0.25:
            adjustment -= 0.04
            notes.append("巴菲特/格雷厄姆：下跌趋势不接飞刀")
    stance = "偏多确认" if adjustment > 0.03 else "偏防守" if adjustment < -0.03 else "中性"
    return {
        "score": round(max(-0.15, min(0.15, adjustment)), 3),
        "stance": stance,
        "notes": notes,
        "adjustment": max(-0.15, min(0.15, adjustment)),
    }


def _expected_return(forward_returns: list[float], up_probability: float) -> float:
    sample = forward_returns[-30:] if len(forward_returns) >= 10 else forward_returns
    gains = [value for value in sample if value > 0]
    losses = [value for value in sample if value < 0]
    average_gain = statistics.fmean(gains) * 100 if gains else 0.0
    average_loss = statistics.fmean(losses) * 100 if losses else 0.0
    return up_probability * average_gain + (1 - up_probability) * average_loss


def _price_range(price: float, forward_returns: list[float]) -> dict[str, float | None]:
    sample = sorted(forward_returns[-30:]) if forward_returns else []
    if len(sample) < 5:
        return {"p25": round(price * 0.985, 4), "median": round(price, 4), "p75": round(price * 1.015, 4)}
    q25 = _quantile(sample, 0.25)
    q50 = _quantile(sample, 0.50)
    q75 = _quantile(sample, 0.75)
    return {
        "p25": round(price * (1 + q25), 4),
        "median": round(price * (1 + q50), 4),
        "p75": round(price * (1 + q75), 4),
    }


def _quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def _risk_reward(price: float, support: float, resistance: float) -> float:
    if support <= 0 or resistance <= price:
        return 0.0
    downside = max(price - support, price * 0.005)
    upside = max(resistance - price, price * 0.01)
    return upside / downside


def _confidence(model: dict[str, Any], sample_count: int, sentiment_coverage: float) -> float:
    base = 0.5
    if model.get("weights") is not None:
        base += (model.get("accuracy", 0.5) - 0.5) * min(sample_count / 60, 1.0)
    base += 0.03 * min(sentiment_coverage, 1.0)
    return max(0.4, min(0.8, base))


def _decide_pre_action(
    price: float,
    support: float,
    resistance: float,
    target: float,
    up_probability: float,
    expected_return: float,
    master_score: float,
    sentiment: float,
    threshold: float,
    confidence: float,
) -> dict[str, str]:
    if up_probability >= threshold and expected_return >= 0.8 and sentiment >= -0.25 and master_score >= 0:
        severity = "high" if confidence >= 0.62 and expected_return >= 1.2 else "medium"
        return {
            "action": "预判低吸",
            "severity": severity,
            "trigger": f"回踩 {round(support * 1.005, 4)} 且不放量跌破 {round(support, 4)}",
            "reason": f"模型预计T+1上涨概率 {up_probability:.0%}，预期收益 {expected_return:.2f}%",
        }
    if up_probability <= 1 - threshold and (expected_return <= -0.4 or price <= support or sentiment <= -0.2):
        severity = "high" if confidence >= 0.62 and expected_return <= -0.8 else "medium"
        return {
            "action": "预判减仓",
            "severity": severity,
            "trigger": f"冲高 {round(resistance, 4)} 附近减仓，跌破 {round(support, 4)} 停止幻想",
            "reason": f"模型预计T+1上涨概率 {up_probability:.0%}，预期收益 {expected_return:.2f}%",
        }
    if price >= target * 0.985:
        return {
            "action": "预判止盈",
            "severity": "high",
            "trigger": f"达到或冲过 {round(target, 4)} 先兑现一半",
            "reason": "已经进入5%目标兑现区，优先锁住收益",
        }
    return {
        "action": "预判观望",
        "severity": "info",
        "trigger": f"站上 {round(resistance, 4)} 才右侧加仓",
        "reason": f"上涨概率 {up_probability:.0%} 处于中性区，等待价格与量能确认",
    }


def _technical_fallback(holding: dict[str, Any], quote: dict[str, Any], indicators: dict[str, Any] | None) -> dict[str, Any]:
    price = float(quote.get("price") or 0)
    support = float(holding.get("support") or price * 0.97)
    resistance = float(holding.get("resistance") or price * 1.03)
    rsi = float((indicators or {}).get("rsi14") or 50)
    up_probability = 0.62 if rsi < 32 and price > support else 0.42 if rsi > 72 else 0.5
    return {
        "horizon": "T+1交易日",
        "up_probability": round(up_probability, 3),
        "down_probability": round(1 - up_probability, 3),
        "expected_return_pct": 0.0,
        "risk_reward": round(_risk_reward(price, support, resistance), 2),
        "volatility_pct": 0.0,
        "price_range": {"p25": round(price * 0.985, 4), "median": round(price, 4), "p75": round(price * 1.015, 4)},
        "trigger_buy": round(support, 4),
        "trigger_sell": round(resistance, 4),
        "confidence": 0.45,
        "model_accuracy": 0.0,
        "method": "技术因子评分模型",
        "sentiment": {"score": 0.0, "coverage": 0.0, "positive": 0, "negative": 0, "items": []},
        "master": {"score": 0.0, "stance": "中性", "notes": [], "adjustment": 0.0},
        "action": "预判观望",
        "severity": "info",
        "trigger": f"站上 {round(resistance, 4)} 才右侧加仓",
        "reason": "历史样本不足，暂按技术评分给占位概率",
    }


def _unavailable(message: str) -> dict[str, Any]:
    return {
        "horizon": "暂无",
        "up_probability": 0.5,
        "down_probability": 0.5,
        "expected_return_pct": 0.0,
        "risk_reward": 0.0,
        "volatility_pct": 0.0,
        "price_range": {"p25": None, "median": None, "p75": None},
        "trigger_buy": None,
        "trigger_sell": None,
        "confidence": 0.4,
        "model_accuracy": 0.0,
        "method": "数据不足",
        "sentiment": {"score": 0.0, "coverage": 0.0, "positive": 0, "negative": 0, "items": []},
        "master": {"score": 0.0, "stance": "中性", "notes": [], "adjustment": 0.0},
        "action": "预判观望",
        "severity": "info",
        "trigger": message,
        "reason": message,
    }


def _rsi(prices: list[float], period: int = 14) -> float | None:
    if len(prices) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    average_gain = statistics.fmean(gains[-period:])
    average_loss = statistics.fmean(losses[-period:])
    if average_loss == 0:
        return 100.0
    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    factor = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * factor + result[-1] * (1 - factor))
    return result


def _macd_histogram(prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> list[float | None]:
    result: list[float | None] = [None] * len(prices)
    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)
    dif = [fast_value - slow_value for fast_value, slow_value in zip(ema_fast, ema_slow)]
    dea = _ema(dif, signal)
    for i in range(len(prices)):
        result[i] = (dif[i] - dea[i]) * 2
    return result
