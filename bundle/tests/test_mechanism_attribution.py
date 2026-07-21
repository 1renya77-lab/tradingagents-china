import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from build_mechanism_attribution import build_attribution_rows


class MechanismAttributionTest(unittest.TestCase):
    def test_mechanism_attribution_single_llm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            audit_dir = run_dir / "audit_reports"
            audit_dir.mkdir()
            (audit_dir / "audit_300308_2026-04-03.json").write_text(
                json.dumps(
                    {
                        "meta": {
                            "trade_date": "2026-04-03",
                            "company_of_interest": "300308",
                            "experiment_mode": "single_llm_direct",
                        },
                        "input_state": {
                            "market_report": "均线多头，MACD改善。",
                            "fundamentals_report": "ROE较高。",
                            "news_report": "暂无重大新闻。",
                            "sentiment_report": "情绪中性。",
                        },
                        "final_decision": {
                            "parsed_decision": {
                                "action": "持有",
                                "target_position": 0.35,
                                "reasoning": "引用了均线、ROE和新闻缺失。",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            rows = build_attribution_rows(run_dir, experiment_mode="single_llm_direct")

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["experiment_mode"], "single_llm_direct")
        self.assertEqual(row["final_position"], 0.35)
        self.assertEqual(row["analyst_reports_available"], "market,fundamentals,news,social")
        self.assertEqual(row["debate_changed_position"], False)
        self.assertGreaterEqual(row["explanation_quality"], 1)

    def test_mechanism_attribution_full_debate_with_feedback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            audit_dir = run_dir / "audit_reports"
            audit_dir.mkdir()
            (run_dir / "feedback_windows.csv").write_text(
                "signal_date,stock_return,agent_return,target_position,decision_quality_score,case_type\n"
                "2026-04-03,0.08,0.05,0.50,0.72,success_attack\n",
                encoding="utf-8",
            )
            (audit_dir / "audit_300308_2026-04-03.json").write_text(
                json.dumps(
                    {
                        "meta": {
                            "trade_date": "2026-04-03",
                            "company_of_interest": "300308",
                            "experiment_mode": "multi_agent_full_debate",
                        },
                        "input_state": {
                            "market_report": "市场报告",
                            "fundamentals_report": "基本面报告",
                            "news_report": "新闻报告",
                            "sentiment_report": "情绪报告",
                        },
                        "investment_debate": {
                            "bull_history": "Bull Analyst: 看涨，建议提高仓位。",
                            "bear_history": "Bear Analyst: 看跌，注意回撤。",
                            "judge_decision": "Research Manager: 采纳看涨方。",
                        },
                        "risk_debate": {
                            "risky_history": "Risky Analyst: aggressive bullish.",
                            "safe_history": "Safe Analyst: conservative bearish.",
                            "neutral_history": "Neutral Analyst: neutral.",
                            "judge_decision": "Risk Judge: target_position: 50%",
                        },
                        "final_decision": {
                            "parsed_decision": {
                                "action": "持有",
                                "target_position": 0.50,
                                "reasoning": "综合Bull和Risky观点。",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            rows = build_attribution_rows(run_dir, experiment_mode="multi_agent_full_debate")

        row = rows[0]
        self.assertEqual(row["bull_direction"], "bullish")
        self.assertEqual(row["bear_direction"], "bearish")
        self.assertEqual(row["risky_direction"], "bullish")
        self.assertEqual(row["safe_direction"], "bearish")
        self.assertEqual(row["winning_side"], "bullish")
        self.assertEqual(row["case_type"], "success_attack")


if __name__ == "__main__":
    unittest.main()
