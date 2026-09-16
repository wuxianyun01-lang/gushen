from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = {
    "probability_bias": 0.0,
    "confidence_adjust": 0.0,
    "samples": 0,
    "correct": 0,
    "recent_errors": [],
    "last_error": None,
}


class SelfLearningMemory:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.prediction_path = self.root / "predictions.jsonl"
        self.lessons_path = self.root / "lessons.jsonl"
        self.profiles_path = self.root / "profiles.json"
        self.lock = threading.RLock()
        self.predictions = self._load_jsonl(self.prediction_path)
        self.lessons = self._load_jsonl(self.lessons_path)
        self.profiles = self._load_profiles()

    def apply_calibration(
        self,
        code: str,
        up_probability: float,
        confidence: float,
        expected_return_pct: float,
    ) -> tuple[float, float, float]:
        profile = self._profile(code)
        bias = float(profile.get("probability_bias") or 0.0)
        confidence_adjust = float(profile.get("confidence_adjust") or 0.0)
        calibrated_probability = max(0.05, min(0.95, up_probability + bias))
        calibrated_confidence = max(0.35, min(0.85, confidence + confidence_adjust))
        calibrated_expected = expected_return_pct + bias * max(2.0, abs(expected_return_pct))
        return calibrated_probability, calibrated_confidence, calibrated_expected

    def record_prediction(self, position: dict[str, Any], prediction: dict[str, Any], now: dt.datetime) -> bool:
        code = position["code"]
        target_date = _next_trading_day(now).strftime("%Y-%m-%d")
        with self.lock:
            if any(
                row.get("code") == code
                and row.get("target_date") == target_date
                and not row.get("resolved_at")
                for row in self.predictions
            ):
                return False
            record = {
                "id": uuid.uuid4().hex,
                "code": code,
                "name": position.get("name", ""),
                "type": position.get("type", ""),
                "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "target_date": target_date,
                "price_at": _price_from_position(position),
                "nav_date_at": _nav_date_from_position(position),
                "up_probability": float(prediction.get("up_probability") or 0.5),
                "expected_return_pct": float(prediction.get("expected_return_pct") or 0),
                "confidence": float(prediction.get("confidence") or 0.5),
                "model_accuracy": float(prediction.get("model_accuracy") or 0),
                "method": prediction.get("method", ""),
                "sentiment_score": float((prediction.get("sentiment") or {}).get("score") or 0),
                "master_stance": (prediction.get("master") or {}).get("stance", ""),
                "action": prediction.get("action", ""),
                "trigger": prediction.get("trigger", ""),
                "actual_price": None,
                "actual_nav_date": None,
                "actual_return_pct": None,
                "direction_correct": None,
                "prediction_error_pct": None,
                "brier_score": None,
                "resolved_at": None,
                "lesson": None,
            }
            self.predictions.append(record)
            self._append_jsonl(self.prediction_path, record)
            return True

    def resolve_pending(self, positions: list[dict[str, Any]], now: dt.datetime) -> int:
        by_code = {position["code"]: position for position in positions}
        resolved = 0
        today = now.date()
        with self.lock:
            for index, record in enumerate(self.predictions):
                if record.get("resolved_at") or record.get("target_date", "") > today.strftime("%Y-%m-%d"):
                    continue
                position = by_code.get(record.get("code"))
                if not position:
                    continue
                actual = _actual_value(position, record)
                if actual is None:
                    continue
                self._resolve_record(index, record, actual, position, now)
                resolved += 1
            if resolved:
                self._write_predictions()
                self._save_profiles()
            return resolved

    def _resolve_record(
        self,
        index: int,
        record: dict[str, Any],
        actual_value: float,
        position: dict[str, Any],
        now: dt.datetime,
    ) -> None:
        price_at = float(record.get("price_at") or 0)
        if price_at <= 0:
            actual_return = 0.0
        else:
            actual_return = (actual_value / price_at - 1) * 100
        actual_up = 1 if actual_return > 0 else 0
        predicted_up = float(record.get("up_probability") or 0.5)
        direction_correct = int((predicted_up >= 0.5) == (actual_up == 1))
        expected_return = float(record.get("expected_return_pct") or 0)
        brier = (predicted_up - actual_up) ** 2
        error = actual_up - predicted_up
        prediction_error = actual_return - expected_return

        record.update({
            "actual_price": round(actual_value, 6),
            "actual_nav_date": _nav_date_from_position(position),
            "actual_return_pct": round(actual_return, 4),
            "direction_correct": direction_correct,
            "prediction_error_pct": round(prediction_error, 4),
            "brier_score": round(brier, 6),
            "resolved_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        })

        profile = self._profile(record["code"])
        bias = float(profile.get("probability_bias") or 0.0)
        confidence_adjust = float(profile.get("confidence_adjust") or 0.0)
        profile["probability_bias"] = _clamp(0.9 * bias + 0.1 * error, -0.12, 0.12)
        profile["confidence_adjust"] = _clamp(confidence_adjust - 0.01 * (brier - 0.25), -0.08, 0.08)
        profile["samples"] = int(profile.get("samples") or 0) + 1
        profile["correct"] = int(profile.get("correct") or 0) + direction_correct
        profile["last_error"] = round(error, 4)
        errors = list(profile.get("recent_errors") or [])
        errors.append(round(error, 4))
        profile["recent_errors"] = errors[-20:]

        if not direction_correct and abs(predicted_up - 0.5) >= 0.15:
            self._add_lesson(record, actual_return, predicted_up)
        self.predictions[index] = record

    def _add_lesson(self, record: dict[str, Any], actual_return: float, predicted_up: float) -> None:
        mistake_type = "过度看多" if predicted_up >= 0.65 else "过度看空" if predicted_up <= 0.35 else "方向误判"
        recent = [
            lesson for lesson in self.lessons
            if lesson.get("code") == record["code"]
            and lesson.get("mistake_type") == mistake_type
        ]
        recurring = len(recent) + 1
        correction = (
            "下一次同类信号必须要求技术、舆情和大师判定至少两项交叉确认；"
            f"当前{record['code']}的同类错误已累计{recurring}次，自动降低该信号的绝对概率。"
        )
        lesson = {
            "id": uuid.uuid4().hex,
            "code": record["code"],
            "name": record.get("name", ""),
            "created_at": record.get("resolved_at") or dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "prediction_date": record.get("created_at", ""),
            "target_date": record.get("target_date", ""),
            "mistake_type": mistake_type,
            "predicted_up_probability": round(predicted_up, 3),
            "actual_return_pct": round(actual_return, 4),
            "summary": (
                f"{record['name']}在{record.get('target_date', '')}实际{('上涨' if actual_return > 0 else '下跌')} "
                f"{abs(actual_return):.2f}%，但模型当时给出{record.get('action', '')}、上涨概率{predicted_up:.0%}。"
            ),
            "correction": correction,
            "recurring_count": recurring,
        }
        self.lessons.insert(0, lesson)
        self.lessons = self.lessons[:50]
        self._append_jsonl(self.lessons_path, lesson)
        record["lesson"] = lesson["summary"]

    def summary(self) -> dict[str, Any]:
        with self.lock:
            resolved = [row for row in self.predictions if row.get("resolved_at")]
            pending = [row for row in self.predictions if not row.get("resolved_at")]
            direction_accuracy = (
                sum(int(row.get("direction_correct") or 0) for row in resolved) / len(resolved)
                if resolved else None
            )
            errors = [abs(float(row.get("prediction_error_pct") or 0)) for row in resolved]
            brier_scores = [float(row.get("brier_score") or 0) for row in resolved]
            return {
                "total_predictions": len(self.predictions),
                "resolved": len(resolved),
                "pending": len(pending),
                "direction_accuracy": round(direction_accuracy, 4) if direction_accuracy is not None else None,
                "mean_abs_error_pct": round(sum(errors) / len(errors), 3) if errors else None,
                "brier_score": round(sum(brier_scores) / len(brier_scores), 4) if brier_scores else None,
                "profiles": {code: self._profile(code) for code in self.profiles},
                "recent_lessons": self.lessons[:8],
                "recent_predictions": pending[-12:],
            }

    def _profile(self, code: str) -> dict[str, Any]:
        if code not in self.profiles:
            self.profiles[code] = dict(DEFAULT_PROFILE)
        return self.profiles[code]

    def _load_profiles(self) -> dict[str, Any]:
        if not self.profiles_path.exists():
            return {}
        try:
            data = json.loads(self.profiles_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_profiles(self) -> None:
        self.profiles_path.write_text(json.dumps(self.profiles, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_predictions(self) -> None:
        self.prediction_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in self.predictions) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _load_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    @staticmethod
    def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _next_trading_day(now: dt.datetime) -> dt.date:
    candidate = now.date() + dt.timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += dt.timedelta(days=1)
    return candidate


def _price_from_position(position: dict[str, Any]) -> float | None:
    kind = position.get("type")
    if kind == "fund":
        nav = float((position.get("fund") or {}).get("nav") or 0)
        return nav or None
    quote = position.get("quote") or {}
    price = float(quote.get("price") or 0)
    return price or None


def _nav_date_from_position(position: dict[str, Any]) -> str:
    return str((position.get("fund") or {}).get("nav_date") or "")


def _actual_value(position: dict[str, Any], record: dict[str, Any]) -> float | None:
    if position.get("type") == "fund":
        fund = position.get("fund") or {}
        nav = float(fund.get("nav") or 0)
        nav_date = str(fund.get("nav_date") or "")
        recorded_nav_date = str(record.get("nav_date_at") or "")
        if nav <= 0 or nav_date <= recorded_nav_date:
            return None
        return nav
    quote = position.get("quote") or {}
    price = float(quote.get("price") or 0)
    return price if price > 0 else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
