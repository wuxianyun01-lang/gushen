from __future__ import annotations

import json

from .config import load_config, REPORT_DIR
from .main import build_positions, summarize
from .notifier import send_alert
from .state import MonitorState


def main() -> None:
    config = load_config()
    state = MonitorState(config)
    positions, _ = build_positions(config)
    state.set_positions(positions)
    lines = []
    for p in positions:
        lines.append(f"{p['name']} | {p['action']} | {p['message']}")
    body = "今日收盘复盘：\n\n" + "\n".join(lines)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "latest.json").write_text(json.dumps(state.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
    send_alert("今日收盘复盘", body, config)


if __name__ == "__main__":
    main()
