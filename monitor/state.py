from __future__ import annotations

import datetime as dt
import threading
from typing import Any


class MonitorState:
    def __init__(self, config: dict):
        self.config = config
        self.lock = threading.RLock()
        self.positions: list[dict[str, Any]] = []
        self.news: list[dict[str, str]] = []
        self.community: dict[str, list[dict[str, Any]]] = {}
        self.learning: dict[str, Any] = {}
        self.last_quote_time: str | None = None
        self.last_fund_time: str | None = None
        self.last_news_time: str | None = None
        self.alerts: list[dict[str, Any]] = []
        self.emitted_actions: dict[str, str] = {}

    def set_positions(self, positions: list[dict[str, Any]]) -> None:
        with self.lock:
            self.positions = positions
            self.last_quote_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def set_news(self, news: list[dict[str, str]]) -> None:
        with self.lock:
            self.news = news
            self.last_news_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def set_community(self, community: dict[str, list[dict[str, Any]]]) -> None:
        with self.lock:
            self.community = community

    def set_learning(self, learning: dict[str, Any]) -> None:
        with self.lock:
            self.learning = learning

    def add_alert(self, alert: dict[str, Any]) -> bool:
        with self.lock:
            now = dt.datetime.now()
            alert["time"] = now.strftime("%Y-%m-%d %H:%M:%S")
            self.alerts.insert(0, alert)
            self.alerts = self.alerts[:50]
            return True

    def emit_once(self, code: str, action_key: str) -> bool:
        """同一标的同一动作只通知一次，动作变化后才再次通知。"""
        with self.lock:
            previous = self.emitted_actions.get(code)
            if previous == action_key:
                return False
            self.emitted_actions[code] = action_key
            return True

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "updated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "positions": self.positions,
                "news": self.news[:10],
                "community": {
                    code: posts[:6]
                    for code, posts in self.community.items()
                },
                "learning": self.learning,
                "alerts": self.alerts[:10],
                "last_quote_time": self.last_quote_time,
                "last_fund_time": self.last_fund_time,
                "last_news_time": self.last_news_time,
            }
