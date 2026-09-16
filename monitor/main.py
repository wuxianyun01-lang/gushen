from __future__ import annotations

import argparse
import datetime as dt
import json
import threading
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import load_config, REPORT_DIR
from .data_providers import fetch_fund_history, fetch_global_news, fetch_guba_posts, fetch_history, fetch_sina_quotes, fetch_fund_snapshots
from .dashboard_server import start_dashboard
from .indicators import calculate_indicators
from .master_view import master_view
from .notifier import send_alert
from .predictor import predict_position
from .self_learning import SelfLearningMemory
from .signals import evaluate_signal
from .state import MonitorState


def _setup_logging() -> None:
    log_path = Path(__file__).resolve().parent / ".monitor.log"
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    def _excepthook(exc_type, exc_value, exc_tb):
        logging.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _excepthook


def build_positions(
    config: dict,
    news: list[dict[str, str]] | None = None,
    community: dict[str, list[dict]] | None = None,
    learning: Any | None = None,
) -> tuple[list[dict], dict]:
    holdings = config["holdings"]
    trade_codes = [h["code"] for h in holdings if h.get("type") != "fund"]
    fund_codes = [h["code"] for h in holdings if h.get("type") == "fund"]
    quotes = fetch_sina_quotes(trade_codes) if trade_codes else {}
    fund_snapshots = fetch_fund_snapshots(fund_codes) if fund_codes else {}
    positions = []
    for holding in holdings:
        code = holding["code"]
        kind = holding["type"]
        indicators = {}
        history = []
        prediction = {}
        quote = quotes.get(code)
        snapshot = fund_snapshots.get(code)
        community_posts = (community or {}).get(code, [])
        if kind == "fund":
            history = fetch_fund_history(code)
            current = float(holding.get("amount") or 0)
            cost = float(holding.get("cost_amount") or 0)
            nav = float(snapshot.get("nav") or 0) if snapshot else 0
            baseline = float(holding.get("baseline_amount") or current)
            target = round(baseline * 1.05, 2)
            signal = evaluate_signal(holding, snapshot, None, [])
            prediction = predict_position(holding, snapshot, None, history, news or [], config.get("prediction"))
            pnl = round(current - cost, 2)
            pnl_pct = round(pnl / cost * 100, 2) if cost else 0
            price_display = f"净值 {nav}" if nav else "暂无"
        else:
            history = fetch_history(code, holding.get("market", "sh"))
            price = float(quote.get("price") or holding.get("baseline_price") or 0)
            baseline = float(holding.get("baseline_price") or price)
            target = round(baseline * 1.05, 4)
            indicators = calculate_indicators(code, holding.get("market", "sh"), history)
            signal = evaluate_signal(holding, quote, indicators, [])
            prediction = predict_position(
                holding,
                quote,
                indicators,
                history,
                news or [],
                config.get("prediction"),
                community_posts,
                learning,
            )
            cost = float(holding.get("cost") or 0)
            shares = float(holding.get("shares") or 0)
            pnl = round((price - cost) * shares, 2)
            pnl_pct = round((price / cost - 1) * 100, 2) if cost else 0
            price_display = price
        distance = ((target / current - 1) * 100) if kind == "fund" and current else 0.0
        if kind != "fund":
            distance = ((target / price - 1) * 100) if price else 0.0
        view = master_view(holding, signal)
        positions.append({
            "code": code,
            "name": holding["name"],
            "type": kind,
            "price": price_display,
            "quote": quote,
            "fund": snapshot,
            "indicators": indicators,
            "cost": cost,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "baseline": baseline,
            "target": target,
            "distance_pct": round(distance, 2),
            "signal": signal["signal"],
            "action": signal["action"],
            "message": signal["message"],
            "severity": signal["severity"],
            "master": view,
            "prediction": prediction,
            "prediction_action": prediction.get("action", "预判观望"),
            "prediction_severity": prediction.get("severity", "info"),
        })
    return positions, quotes


def summarize(config: dict, state: MonitorState, memory: SelfLearningMemory) -> None:
    news = state.news or fetch_global_news(12)
    positions, _ = build_positions(config, news, state.community, memory)
    state.set_positions(positions)
    state.set_news(news)
    now = dt.datetime.now()
    for position in positions:
        memory.record_prediction(position, position["prediction"], now)
    memory.resolve_pending(positions, now)
    state.set_learning(memory.summary())
    _emit_alerts(config, state, positions)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "latest.json").write_text(json.dumps(state.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")


_STRONG_ACTIONS = ("预判减仓", "预判止盈", "预判低吸")


def _build_alert_body(position: dict, action: str) -> str:
    name = position["name"]
    kind = position["type"]
    pnl_pct = float(position.get("pnl_pct") or 0)
    prediction = position.get("prediction") or {}
    up = prediction.get("up_probability")
    exp = prediction.get("expected_return_pct")
    buy = prediction.get("trigger_buy")
    sell = prediction.get("trigger_sell")
    reason = prediction.get("reason", "")
    lines = [f"【{name}】{action}"]
    if kind == "fund":
        lines.append(f"{position.get('price') or '净值未知'}，当前盈亏 {pnl_pct:+.2f}%。")
    else:
        try:
            px = float(position.get("price") or 0)
        except (TypeError, ValueError):
            px = None
        if px is not None:
            lines.append(f"现价 {px:.3f}，当前盈亏 {pnl_pct:+.2f}%。")
    if action == "趋势转弱":
        lines.append("意思是：价格已经跌破你的防守线，趋势还在往下走，回本更难了。")
        lines.append("具体操作：")
        lines.append("1、不要补仓——还在下跌趋势里，摊平只会越套越深。")
        if sell is not None:
            lines.append(f"2、反弹减仓价：{sell}，反弹到这个价附近就先减一部分。")
        if buy is not None:
            lines.append(f"3、防守线：{buy}，再跌破这里说明还要跌，之后每次反弹都优先减，别再等更高价。")
    elif action == "预判减仓":
        if up is not None and exp is not None:
            lines.append(f"模型判断明天上涨概率只有 {up:.0%}，预期还要跌 {abs(exp):.2f}%，建议减仓。")
        lines.append("具体操作：")
        if sell is not None:
            lines.append(f"1、反弹到 {sell} 附近先减一部分。")
        if buy is not None:
            lines.append(f"2、防守线 {buy}，跌破就停止幻想，反弹就减。")
    elif action == "预判止盈":
        lines.append("已经进入 5% 目标兑现区，优先落袋锁住收益。")
        if sell is not None:
            lines.append(f"操作：达到或冲过 {sell} 先兑现一半，剩下让利润跑。")
    elif action == "预判低吸":
        lines.append("模型判断有机会低吸。")
        if buy is not None:
            lines.append(f"操作：回踩到 {buy} 附近、且没有放量跌破，再低吸。")
    else:
        if reason:
            lines.append(reason)
        if sell is not None:
            lines.append(f"操作：站上 {sell} 才右侧加仓，没站上之前不动。")
    return "\n".join(lines)


def _emit_alerts(config: dict, state: MonitorState, positions: list[dict]) -> None:
    for position in positions:
        prediction = position.get("prediction") or {}
        if position["severity"] in ("critical", "high"):
            action_key = f"{position['signal']}:{position['action']}"
            if state.emit_once(f"s:{position['code']}", action_key):
                body = _build_alert_body(position, position["action"])
                state.add_alert({
                    "code": position["code"],
                    "name": position["name"],
                    "signal": position["signal"],
                    "action": position["action"],
                    "message": body,
                    "severity": position["severity"],
                })
                _title = f"{position['name']} · {position['action']}"
                logging.info("告警 %s -> %s", _title, send_alert(_title, body, config, dry_run=False))
            continue
        pred_action = prediction.get("action")
        pred_severity = prediction.get("severity")
        if pred_action in _STRONG_ACTIONS and pred_severity in ("medium", "high"):
            if state.emit_once(f"p:{position['code']}", pred_action):
                body = _build_alert_body(position, pred_action)
                state.add_alert({
                    "code": position["code"],
                    "name": position["name"],
                    "signal": "prediction",
                    "action": pred_action,
                    "message": body,
                    "severity": pred_severity,
                })
                _title = f"{position['name']} · {pred_action}"
                logging.info("告警 %s -> %s", _title, send_alert(_title, body, config, dry_run=False))

def refresh_news(config: dict, state: MonitorState) -> None:
    state.set_news(fetch_global_news(12))
    community: dict[str, list[dict]] = {}
    for holding in config["holdings"]:
        if holding.get("type") == "fund":
            continue
        posts = fetch_guba_posts(holding["code"], 10)
        if posts:
            community[holding["code"]] = posts
    state.set_community(community)


def run_server(config: dict, state: MonitorState, port: int) -> None:
    server = start_dashboard(state, port)
    print(f"dashboard http://127.0.0.1:{port}", file=__import__("sys").stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    config = load_config()
    state = MonitorState(config)
    memory = SelfLearningMemory(REPORT_DIR / "memory")
    port = args.port or config["monitoring"]["dashboard_port"]
    thread = threading.Thread(target=run_server, args=(config, state, port), daemon=True)
    thread.start()
    send_alert("监控已启动", "持仓监控已启动，后续出现操作信号会通知你。", config)
    refresh_news(config, state)
    summarize(config, state, memory)
    if args.once:
        print(json.dumps(state.snapshot(), ensure_ascii=False, indent=2))
        return
    last_quote = 0
    last_news = 0
    try:
        while True:
            now = time.time()
            is_trading_time = _is_trading_time()
            if is_trading_time and now - last_quote >= config["monitoring"]["quote_interval_seconds"]:
                summarize(config, state, memory)
                last_quote = now
            if is_trading_time and now - last_news >= config["monitoring"]["news_interval_seconds"]:
                refresh_news(config, state)
                last_news = now
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.exception("监控主循环异常")


def _is_trading_time() -> bool:
    now = dt.datetime.now()
    if now.weekday() >= 5:
        return False
    hm = now.hour * 100 + now.minute
    return 915 <= hm <= 1510


if __name__ == "__main__":
    main()



