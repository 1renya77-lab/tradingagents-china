import unittest

from tradingagents.graph.trading_graph import TradingAgentsGraph


class TradingGraphPositionCalibrationTest(unittest.TestCase):
    def test_graph_uses_configured_position_calibration_mode(self):
        graph = object.__new__(TradingAgentsGraph)
        graph.config = {"position_calibration_mode": "evidence_weighted"}
        final_state = {
            "final_trade_decision": "target_position: 30%",
            "market_report": "强趋势向上，均线多头排列，放量突破。",
            "fundamentals_report": "基本面优秀，ROE改善。",
            "news_report": "订单催化明确。",
            "sentiment_report": "回撤可控，赔率大于2。",
        }
        decision = {
            "action": "持有",
            "target_position": 0.30,
            "reasoning": "强趋势向上，均线多头排列，放量突破，订单催化明确，回撤可控，赔率大于2。",
        }

        out = graph._apply_position_risk_gate(final_state, decision)

        self.assertAlmostEqual(out["target_position"], 0.80)
        self.assertEqual(out["position_calibration"]["mode"], "evidence_weighted")

    def test_graph_passes_structured_evidence_to_position_calibration(self):
        graph = object.__new__(TradingAgentsGraph)
        graph.config = {"position_calibration_mode": "evidence_weighted"}
        final_state = {
            "final_trade_decision": "target_position: 30%",
            "market_report": "文本不包含强趋势关键词。",
            "fundamentals_report": "",
            "news_report": "",
            "sentiment_report": "",
        }
        decision = {
            "action": "持有",
            "target_position": 0.30,
            "reasoning": "文本不包含强趋势关键词。",
            "evidence_scores": {
                "trend_strength": 5,
                "reward_risk_score": 4,
                "catalyst_strength": 4,
                "drawdown_risk": 1,
                "data_quality": 4,
                "recommended_position_floor": 0.80,
            },
        }

        out = graph._apply_position_risk_gate(final_state, decision)

        self.assertAlmostEqual(out["target_position"], 0.80)
        self.assertEqual(out["position_calibration"]["return_evidence"]["source"], "structured")

    def test_graph_raises_low_explicit_floor_when_structured_scores_imply_higher_participation(self):
        graph = object.__new__(TradingAgentsGraph)
        graph.config = {"position_calibration_mode": "evidence_weighted"}
        final_state = {
            "final_trade_decision": "target_position: 25%",
            "market_report": "强趋势向上。",
            "fundamentals_report": "基本面稳健。",
            "news_report": "催化明确。",
            "sentiment_report": "回撤可控。",
        }
        decision = {
            "action": "持有",
            "target_position": 0.25,
            "reasoning": "趋势、催化、赔率均支持提高参与度。",
            "evidence_scores": {
                "trend_strength": 4,
                "reward_risk_score": 4,
                "catalyst_strength": 3,
                "drawdown_risk": 2,
                "data_quality": 3,
                "recommended_position_floor": 0.35,
            },
        }

        out = graph._apply_position_risk_gate(final_state, decision)

        self.assertAlmostEqual(out["target_position"], 0.65)
        self.assertEqual(out["position_calibration"]["constraints"][0]["rule"], "structured_evidence_consistency_floor")


if __name__ == "__main__":
    unittest.main()
