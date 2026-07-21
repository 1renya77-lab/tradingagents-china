import unittest

from tradingagents.graph.signal_processing import SignalProcessor


class SignalProcessingStructuredParseTest(unittest.TestCase):
    def test_process_signal_prefers_structured_markdown_fields(self):
        processor = SignalProcessor(quick_thinking_llm=None)
        signal = """**Action**: 持有

**Executive Summary**: 本周期建议维持观察仓，保留 alpha 暴露。

**Target Position**: 35.00%

**Target Price**: 1350

**Confidence**: 0.78
**Risk Score**: 0.42

**Forecast**
- p_up_5d: 0.62
- expected_return_5d: 0.035
- expected_excess_5d: 0.020
- downside_risk_5d: -0.025
- is_priced_in: medium
- forecast_reason: 上行证据存在，但部分被价格反映。

**Reasoning**: 中期结构未坏，短期承压但不应空仓。"""

        out = processor.process_signal(signal, "300308")

        self.assertEqual(out["action"], "持有")
        self.assertAlmostEqual(out["target_position"], 0.35)
        self.assertEqual(out["target_price"], 1350.0)
        self.assertAlmostEqual(out["confidence"], 0.78)
        self.assertAlmostEqual(out["risk_score"], 0.42)
        self.assertEqual(out["forecast"]["is_priced_in"], "medium")
        self.assertAlmostEqual(out["forecast"]["p_up_5d"], 0.62)
        self.assertAlmostEqual(out["forecast"]["expected_return_5d"], 0.035)
        self.assertAlmostEqual(out["forecast"]["expected_excess_5d"], 0.020)
        self.assertAlmostEqual(out["forecast"]["downside_risk_5d"], -0.025)
        self.assertIn("中期结构未坏", out["reasoning"])
        self.assertNotIn("p_up_5d", out["reasoning"])


if __name__ == "__main__":
    unittest.main()
