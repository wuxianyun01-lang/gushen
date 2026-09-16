from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = PROJECT_ROOT / "reports" / "ta_signals.json"

_ACTION_MAP = {"买入": 1.0, "持有": 0.0, "卖出": -1.0, "加仓": 0.8, "减仓": -0.8, "观望": 0.0}


def build_config() -> dict[str, Any]:
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = DEFAULT_CONFIG.copy()
    cfg["llm_provider"] = "deepseek"
    cfg["deep_think_llm"] = "deepseek-chat"
    cfg["quick_think_llm"] = "deepseek-chat"
    cfg["backend_url"] = "https://api.deepseek.com"
    cfg["max_debate_rounds"] = 1
    cfg["max_risk_discuss_rounds"] = 1
    cfg["online_tools"] = False
    return cfg


def action_to_signal(action: str, confidence: float | None) -> float:
    base = 0.0
    for key, value in _ACTION_MAP.items():
        if key in str(action or ""):
            base = value
            break
    conf = max(0.0, min(1.0, float(confidence or 0.5)))
    return round(base * conf, 4)


def run_analysis(code: str, name: str, date: str) -> dict[str, Any]:
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ta = TradingAgentsGraph(debug=False, config=build_config())
    _final_state, decision = ta.propagate(code, date)
    action = str(decision.get("action") or "持有")
    record = {
        "code": code,
        "name": name,
        "date": date,
        "action": action,
        "confidence": decision.get("confidence"),
        "risk_score": decision.get("risk_score"),
        "target_price": decision.get("target_price"),
        "reasoning": decision.get("reasoning"),
        "signal": action_to_signal(action, decision.get("confidence")),
        "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save(code, record)
    return record


def _save(code: str, record: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, Any] = {}
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}
    cache[code] = record
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def load_signal(code: str) -> float | None:
    if not CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    record = cache.get(code)
    if not record:
        return None
    return float(record.get("signal") or 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="TradingAgents-CN 多智能体分析桥接")
    parser.add_argument("--code", required=True, help="股票代码，如 600905 或 600905.SH")
    parser.add_argument("--name", required=True, help="股票名称")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="分析日期 YYYY-MM-DD")
    args = parser.parse_args()
    record = run_analysis(args.code, args.name, args.date)
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
