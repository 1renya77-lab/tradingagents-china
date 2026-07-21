import unittest

from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager


class PortfolioDecisionSchemaTest(unittest.TestCase):
    def test_portfolio_decision_renders_structured_evidence_scores(self):
        decision = PortfolioDecision(
            rating=PortfolioRating.OVERWEIGHT,
            executive_summary="目标仓位80%，强趋势但设好止损。",
            target_position=0.80,
            investment_thesis="强趋势、订单催化和高赔率共同支持提高仓位。",
            trend_strength=5,
            reward_risk_score=4,
            catalyst_strength=4,
            drawdown_risk=1,
            data_quality=4,
            recommended_position_floor=0.80,
            position_invalid_if="跌破20日均线且放量。",
        )

        rendered = render_pm_decision(decision)

        self.assertIn("**Evidence Scores**", rendered)
        self.assertIn("trend_strength: 5", rendered)
        self.assertIn("recommended_position_floor: 80.00%", rendered)
        self.assertIn("position_invalid_if: 跌破20日均线且放量。", rendered)

    def test_portfolio_manager_uses_current_risk_debate_state_keys(self):
        class _StructuredLLM:
            def with_structured_output(self, schema):
                return self

            def invoke(self, prompt):
                return PortfolioDecision(
                    rating=PortfolioRating.OVERWEIGHT,
                    executive_summary="目标仓位80%，顺势参与。",
                    target_position=0.80,
                    investment_thesis="趋势、赔率、催化共振。",
                    trend_strength=5,
                    reward_risk_score=4,
                    catalyst_strength=4,
                    drawdown_risk=2,
                    data_quality=4,
                    recommended_position_floor=0.80,
                    position_invalid_if="跌破20日均线。",
                )

        node = create_portfolio_manager(_StructuredLLM())
        state = {
            "company_of_interest": "300308",
            "investment_plan": "建议增配。",
            "trader_investment_plan": "建议买入。",
            "past_context": "",
            "risk_debate_state": {
                "history": "Risky Analyst: 建议提高仓位。",
                "risky_history": "Risky Analyst: 建议提高仓位。",
                "safe_history": "Safe Analyst: 风险仍在。",
                "neutral_history": "Neutral Analyst: 建议折中。",
                "latest_speaker": "Safe",
                "current_risky_response": "Risky Analyst: 建议提高仓位。",
                "current_safe_response": "Safe Analyst: 风险仍在。",
                "current_neutral_response": "Neutral Analyst: 建议折中。",
                "judge_decision": "",
                "count": 3,
            },
        }

        out = node(state)
        risk_state = out["risk_debate_state"]
        self.assertIn("risky_history", risk_state)
        self.assertIn("safe_history", risk_state)
        self.assertIn("current_risky_response", risk_state)
        self.assertIn("current_safe_response", risk_state)
        self.assertNotIn("aggressive_history", risk_state)
        self.assertNotIn("conservative_history", risk_state)


if __name__ == "__main__":
    unittest.main()
