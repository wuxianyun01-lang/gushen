import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from monitor.indicators import _rsi
from monitor.predictor import _decide_pre_action, _logistic_probability, _quantile, _sentiment
from monitor.signals import evaluate_signal


class SignalTests(unittest.TestCase):
    def test_target_reached(self):
        holding = {"type": "etf", "baseline_price": 1.0, "support": 0.9, "resistance": 1.2}
        quote = {"price": 1.05, "prev_close": 1.0}
        signal = evaluate_signal(holding, quote, {}, [])
        self.assertEqual(signal["signal"], "take_profit")

    def test_below_support(self):
        holding = {"type": "etf", "baseline_price": 1.0, "support": 0.9, "resistance": 1.2}
        quote = {"price": 0.89, "prev_close": 1.0}
        signal = evaluate_signal(holding, quote, {}, [])
        self.assertEqual(signal["signal"], "weak")

    def test_rsi_calculation(self):
        rsi = _rsi(list(range(1, 30)), 14)
        self.assertIsNotNone(rsi)
        self.assertGreater(rsi, 50)

    def test_logistic_probability_is_bounded(self):
        probability = _logistic_probability([0.5, 1.0, -1.0], [1.0, 0.8, -0.2])
        self.assertGreaterEqual(probability, 0.0)
        self.assertLessEqual(probability, 1.0)

    def test_quantile(self):
        self.assertEqual(_quantile([1.0, 2.0, 3.0, 4.0], 0.5), 2.5)

    def test_positive_community_sentiment(self):
        sentiment = _sentiment(
            {"keywords": ["上涨"]},
            [{"title": "板块上涨 资金净流入", "digest": "", "time": "2026-09-07 14:00:00", "url": ""}],
            [],
        )
        self.assertGreater(sentiment["score"], 0)

    def test_high_confidence_pre_buy(self):
        action = _decide_pre_action(10.0, 9.5, 11.0, 10.5, 0.72, 1.8, 0.1, 0.1, 0.62, 0.7)
        self.assertEqual(action["action"], "预判低吸")
        self.assertEqual(action["severity"], "high")

    def test_high_confidence_pre_reduce(self):
        action = _decide_pre_action(10.0, 9.5, 11.0, 10.5, 0.28, -1.2, -0.1, -0.1, 0.62, 0.7)
        self.assertEqual(action["action"], "预判减仓")
        self.assertEqual(action["severity"], "high")


if __name__ == "__main__":
    unittest.main()
