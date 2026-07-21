import unittest

from tradingagents.agents.managers.risk_manager import create_risk_manager
from tradingagents.agents.schemas import RiskDecision, ChinaTradeAction


class RiskManagerStructuredOutputTest(unittest.TestCase):
    def test_risk_manager_repairs_internally_inconsistent_low_position(self):
        class _StructuredLLM:
            def __init__(self):
                self.calls = 0

            def with_structured_output(self, schema):
                return self

            def invoke(self, prompt):
                self.calls += 1
                if self.calls == 1:
                    return RiskDecision(
                        action=ChinaTradeAction.HOLD,
                        executive_summary="趋势和催化都偏强，但先只给20%仓位。",
                        target_position=0.20,
                        target_price=1450.0,
                        confidence=0.76,
                        risk_score=0.40,
                        trend_strength=4,
                        reward_risk_score=3,
                        catalyst_strength=3,
                        drawdown_risk=2,
                        data_quality=3,
                        recommended_position_floor=0.20,
                        position_invalid_if="跌破MA20且放量。",
                        reasoning="趋势仍在，催化明确，回撤可控，但短期略热。",
                    )
                return RiskDecision(
                    action=ChinaTradeAction.HOLD,
                    executive_summary="趋势、催化和回撤控制支持提高到55%参与仓。",
                    target_position=0.55,
                    target_price=1450.0,
                    confidence=0.76,
                    risk_score=0.40,
                    trend_strength=4,
                    reward_risk_score=3,
                    catalyst_strength=3,
                    drawdown_risk=2,
                    data_quality=3,
                    recommended_position_floor=0.45,
                    position_invalid_if="跌破MA20且放量。",
                    reasoning="趋势仍在，催化明确，回撤可控，短期偏热但不足以压到低仓。"
                )

        node = create_risk_manager(_StructuredLLM(), memory=None, config={})
        state = {
            "company_of_interest": "300308",
            "market_report": "中期结构未坏。",
            "news_report": "行业催化仍在。",
            "fundamentals_report": "ROE高，盈利质量好。",
            "sentiment_report": "情绪分歧但未崩。",
            "investment_plan": "建议观察仓参与。",
            "risk_debate_state": {
                "history": "Risky Analyst: 应该至少40%-55%。",
                "risky_history": "Risky Analyst: 应该至少40%-55%。",
                "safe_history": "Safe Analyst: 短期承压。",
                "neutral_history": "Neutral Analyst: 观察仓。",
                "latest_speaker": "Neutral",
                "current_risky_response": "Risky Analyst: 应该至少40%-55%。",
                "current_risky_response_brief": "",
                "current_safe_response": "Safe Analyst: 短期承压。",
                "current_safe_response_brief": "",
                "current_neutral_response": "Neutral Analyst: 观察仓。",
                "current_neutral_response_brief": "",
                "count": 3,
            },
        }

        out = node(state)
        text = out["final_trade_decision"]
        self.assertIn("**Target Position**: 55.00%", text)
        self.assertIn("recommended_position_floor: 45.00%", text)

    def test_risk_manager_renders_structured_risk_decision(self):
        class _StructuredLLM:
            def with_structured_output(self, schema):
                return self

            def invoke(self, prompt):
                return RiskDecision(
                    action=ChinaTradeAction.HOLD,
                    executive_summary="保留35%探索性参与仓位，等待短期修复确认。",
                    target_position=0.35,
                    target_price=1350.0,
                    confidence=0.78,
                    risk_score=0.42,
                    trend_strength=3,
                    reward_risk_score=4,
                    catalyst_strength=3,
                    drawdown_risk=2,
                    data_quality=3,
                    recommended_position_floor=0.30,
                    position_invalid_if="跌破MA20且放量。",
                    reasoning=(
                        "中期结构未坏，旧融资时间戳只应降低置信度而非一票否决。"
                    ),
                )

        node = create_risk_manager(_StructuredLLM(), memory=None, config={})
        state = {
            "company_of_interest": "300308",
            "market_report": "中期结构未坏。",
            "news_report": "行业催化仍在。",
            "fundamentals_report": "ROE高，盈利质量好。",
            "sentiment_report": "情绪分歧但未崩。",
            "investment_plan": "建议观察仓参与。",
            "risk_debate_state": {
                "history": "Risky Analyst: 应该至少30%-40%。",
                "risky_history": "Risky Analyst: 应该至少30%-40%。",
                "safe_history": "Safe Analyst: 短期承压。",
                "neutral_history": "Neutral Analyst: 观察仓。",
                "latest_speaker": "Neutral",
                "current_risky_response": "Risky Analyst: 应该至少30%-40%。",
                "current_risky_response_brief": "",
                "current_safe_response": "Safe Analyst: 短期承压。",
                "current_safe_response_brief": "",
                "current_neutral_response": "Neutral Analyst: 观察仓。",
                "current_neutral_response_brief": "",
                "count": 3,
            },
        }

        out = node(state)
        text = out["final_trade_decision"]
        self.assertIn("**Action**: 持有", text)
        self.assertIn("**Target Position**: 35.00%", text)
        self.assertIn("**Evidence Scores**", text)
        self.assertIn("recommended_position_floor: 30.00%", text)
        self.assertIn("旧融资时间戳只应降低置信度", text)

    def test_risk_manager_repairs_lazy_mid_position_without_mid_justification(self):
        class _StructuredLLM:
            def __init__(self):
                self.calls = 0

            def with_structured_output(self, schema):
                return self

            def invoke(self, prompt):
                self.calls += 1
                if self.calls == 1:
                    return RiskDecision(
                        action=ChinaTradeAction.HOLD,
                        executive_summary="等待更清晰确认，先持有50%仓位。",
                        target_position=0.50,
                        target_price=680.0,
                        confidence=0.68,
                        risk_score=0.56,
                        trend_strength=2,
                        reward_risk_score=2,
                        catalyst_strength=1,
                        drawdown_risk=3,
                        data_quality=3,
                        recommended_position_floor=None,
                        position_invalid_if="跌破前低。",
                        reasoning="当前更像等待确认，空仓者不追高，反弹若无量可减仓。",
                    )
                return RiskDecision(
                    action=ChinaTradeAction.HOLD,
                    executive_summary="证据不支持中档仓位，改为30%观察仓等待确认。",
                    target_position=0.30,
                    target_price=660.0,
                    confidence=0.68,
                    risk_score=0.56,
                    trend_strength=2,
                    reward_risk_score=2,
                    catalyst_strength=1,
                    drawdown_risk=3,
                    data_quality=3,
                    recommended_position_floor=None,
                    position_invalid_if="跌破前低。",
                    reasoning="主要矛盾是等待确认而非均衡博弈，因此用30%观察仓保留 alpha 暴露更合适。",
                )

        node = create_risk_manager(_StructuredLLM(), memory=None, config={})
        state = {
            "company_of_interest": "300308",
            "market_report": "短期过热但趋势未明。",
            "news_report": "暂无明确新催化。",
            "fundamentals_report": "基本面尚可。",
            "sentiment_report": "情绪分歧。",
            "investment_plan": "建议等待确认。",
            "risk_debate_state": {
                "history": "Risky Analyst: 不应空仓。 Safe Analyst: 先等确认。 Neutral Analyst: 观察。",
                "risky_history": "Risky Analyst: 不应空仓。",
                "safe_history": "Safe Analyst: 先等确认。",
                "neutral_history": "Neutral Analyst: 观察。",
                "latest_speaker": "Neutral",
                "current_risky_response": "Risky Analyst: 不应空仓。",
                "current_risky_response_brief": "",
                "current_safe_response": "Safe Analyst: 先等确认。",
                "current_safe_response_brief": "",
                "current_neutral_response": "Neutral Analyst: 观察。",
                "current_neutral_response_brief": "",
                "count": 3,
            },
        }

        out = node(state)
        text = out["final_trade_decision"]
        self.assertIn("**Target Position**: 30.00%", text)
        self.assertNotIn("**Target Position**: 50.00%", text)

    def test_risk_manager_repairs_low_allocation_when_aggressive_anchor_is_supported(self):
        class _StructuredLLM:
            def __init__(self):
                self.calls = 0

            def with_structured_output(self, schema):
                return self

            def invoke(self, prompt):
                self.calls += 1
                if self.calls == 1:
                    return RiskDecision(
                        action=ChinaTradeAction.HOLD,
                        executive_summary="趋势和催化不错，但先只给35%仓位。",
                        target_position=0.35,
                        target_price=720.0,
                        confidence=0.73,
                        risk_score=0.43,
                        trend_strength=4,
                        reward_risk_score=3,
                        catalyst_strength=3,
                        drawdown_risk=2,
                        data_quality=3,
                        recommended_position_floor=0.35,
                        position_invalid_if="跌破MA20且放量。",
                        reasoning="趋势未坏，催化仍在，但我倾向先保守一些。",
                    )
                return RiskDecision(
                    action=ChinaTradeAction.HOLD,
                    executive_summary="激进观点中的趋势、催化和赔率并未被证伪，提升到55%更符合本周期 alpha 目标。",
                    target_position=0.55,
                    target_price=720.0,
                    confidence=0.73,
                    risk_score=0.43,
                    trend_strength=4,
                    reward_risk_score=3,
                    catalyst_strength=3,
                    drawdown_risk=2,
                    data_quality=3,
                    recommended_position_floor=0.45,
                    position_invalid_if="跌破MA20且放量。",
                    reasoning="激进分析师主张的60%-80%进攻区间部分成立，但考虑短期波动后，55%参与仓更平衡。"
                )

        node = create_risk_manager(_StructuredLLM(), memory=None, config={})
        state = {
            "company_of_interest": "300308",
            "market_report": "中期趋势向上，均线多头排列。",
            "news_report": "订单催化和行业景气延续。",
            "fundamentals_report": "ROE高，盈利质量好。",
            "sentiment_report": "情绪积极。",
            "investment_plan": "建议持有。",
            "risk_debate_state": {
                "history": "Risky Analyst: 当前至少应提高到60%-80%，跌破MA20再放弃进攻。",
                "risky_history": "Risky Analyst: 当前至少应提高到60%-80%，跌破MA20再放弃进攻。",
                "safe_history": "Safe Analyst: 警惕短期过热。",
                "neutral_history": "Neutral Analyst: 可保留参与仓。",
                "latest_speaker": "Neutral",
                "current_risky_response": "Risky Analyst: 当前至少应提高到60%-80%，跌破MA20再放弃进攻。",
                "current_risky_response_brief": "",
                "current_safe_response": "Safe Analyst: 警惕短期过热。",
                "current_safe_response_brief": "",
                "current_neutral_response": "Neutral Analyst: 可保留参与仓。",
                "current_neutral_response_brief": "",
                "count": 3,
            },
        }

        out = node(state)
        text = out["final_trade_decision"]
        self.assertIn("**Target Position**: 55.00%", text)
        self.assertIn("recommended_position_floor: 45.00%", text)

    def test_risk_manager_manual_json_binding_for_normalized_chat_anthropic(self):
        def _invoke(self, prompt):
            class _Resp:
                content = """{
  "action": "持有",
  "executive_summary": "保留35%探索性参与仓位，等待短期修复确认。",
  "target_position": 0.35,
  "target_price": 1350.0,
  "confidence": 0.78,
  "risk_score": 0.42,
  "trend_strength": 3,
  "reward_risk_score": 4,
  "catalyst_strength": 3,
  "drawdown_risk": 2,
  "data_quality": 3,
  "recommended_position_floor": 0.30,
  "position_invalid_if": "跌破MA20且放量。",
  "reasoning": "中期结构未坏，旧融资时间戳只应降低置信度而非一票否决。"
}"""

            return _Resp()

        NormalizedChatAnthropic = type(
            "NormalizedChatAnthropic",
            (),
            {"invoke": _invoke},
        )

        node = create_risk_manager(NormalizedChatAnthropic(), memory=None, config={})
        state = {
            "company_of_interest": "300308",
            "market_report": "中期结构未坏。",
            "news_report": "行业催化仍在。",
            "fundamentals_report": "ROE高，盈利质量好。",
            "sentiment_report": "情绪分歧但未崩。",
            "investment_plan": "建议观察仓参与。",
            "risk_debate_state": {
                "history": "Risky Analyst: 应该至少30%-40%。",
                "risky_history": "Risky Analyst: 应该至少30%-40%。",
                "safe_history": "Safe Analyst: 短期承压。",
                "neutral_history": "Neutral Analyst: 观察仓。",
                "latest_speaker": "Neutral",
                "current_risky_response": "Risky Analyst: 应该至少30%-40%。",
                "current_risky_response_brief": "",
                "current_safe_response": "Safe Analyst: 短期承压。",
                "current_safe_response_brief": "",
                "current_neutral_response": "Neutral Analyst: 观察仓。",
                "current_neutral_response_brief": "",
                "count": 3,
            },
        }

        out = node(state)
        text = out["final_trade_decision"]
        self.assertIn("**Action**: 持有", text)
        self.assertIn("**Target Position**: 35.00%", text)
        self.assertIn("position_invalid_if: 跌破MA20且放量。", text)
        self.assertIn("**Evidence Scores**", text)

    def test_signal_processor_extracts_structured_evidence_scores_from_rendered_risk_decision(self):
        from tradingagents.graph.signal_processing import SignalProcessor

        processor = SignalProcessor(quick_thinking_llm=None)
        text = """**Action**: 持有

**Executive Summary**: 保留35%探索性参与仓位。

**Target Position**: 35.00%

**Confidence**: 0.78
**Risk Score**: 0.42

**Evidence Scores**
- trend_strength: 3
- reward_risk_score: 4
- catalyst_strength: 3
- drawdown_risk: 2
- data_quality: 3
- recommended_position_floor: 30.00%
- position_invalid_if: 跌破MA20且放量。

**Reasoning**: 中期结构未坏。"""

        parsed = processor._parse_structured_decision(text)

        self.assertEqual(parsed["action"], "持有")
        self.assertAlmostEqual(parsed["target_position"], 0.35)
        self.assertEqual(parsed["evidence_scores"]["trend_strength"], 3.0)
        self.assertEqual(parsed["evidence_scores"]["reward_risk_score"], 4.0)
        self.assertAlmostEqual(parsed["evidence_scores"]["recommended_position_floor"], 0.30)
        self.assertEqual(parsed["evidence_scores"]["position_invalid_if"], "跌破MA20且放量。")


if __name__ == "__main__":
    unittest.main()
