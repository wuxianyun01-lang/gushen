import datetime as dt
import tempfile
import unittest
from pathlib import Path

from monitor.self_learning import SelfLearningMemory


class SelfLearningTests(unittest.TestCase):
    def test_record_and_resolve_extreme_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = SelfLearningMemory(Path(tmp))
            prediction = {
                "up_probability": 0.78,
                "expected_return_pct": 1.4,
                "confidence": 0.65,
                "model_accuracy": 0.55,
                "method": "test",
                "sentiment": {"score": 0.2},
                "master": {"stance": "偏多确认"},
                "action": "预判低吸",
                "trigger": "回踩10元",
            }
            position = {
                "code": "600000",
                "name": "测试股票",
                "type": "stock",
                "quote": {"price": 10.0},
            }
            created = dt.datetime(2026, 9, 8, 10, 0)
            self.assertTrue(memory.record_prediction(position, prediction, created))
            actual_position = {**position, "quote": {"price": 9.5}}
            self.assertEqual(memory.resolve_pending([actual_position], dt.datetime(2026, 9, 9, 10, 0)), 1)
            summary = memory.summary()
            self.assertEqual(summary["resolved"], 1)
            self.assertLess(summary["direction_accuracy"], 1)
            self.assertTrue(summary["recent_lessons"])
            self.assertLess(memory._profile("600000")["probability_bias"], 0)

    def test_calibration_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = SelfLearningMemory(Path(tmp))
            probability, confidence, expected = memory.apply_calibration("000001", 1.0, 1.0, 5.0)
            self.assertLessEqual(probability, 0.95)
            self.assertLessEqual(confidence, 0.85)
            self.assertGreater(expected, 0)


if __name__ == "__main__":
    unittest.main()
