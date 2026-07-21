import unittest

from tradingagents.graph.setup import resolve_graph_mode_edges


class GraphSetupModesTest(unittest.TestCase):
    def test_no_debate_routes_last_analyst_to_research_manager_and_trader_to_risk_judge(self):
        edges = resolve_graph_mode_edges(
            selected_analysts=["market", "fundamentals", "news", "social"],
            enable_investment_debate=False,
            enable_risk_debate=False,
        )

        self.assertEqual(edges["after_last_analyst"], "Research Manager")
        self.assertEqual(edges["after_trader"], "Risk Judge")

    def test_full_debate_keeps_research_and_risk_debate_entrypoints(self):
        edges = resolve_graph_mode_edges(
            selected_analysts=["market", "fundamentals", "news", "social"],
            enable_investment_debate=True,
            enable_risk_debate=True,
        )

        self.assertEqual(edges["after_last_analyst"], "Bull Researcher")
        self.assertEqual(edges["after_trader"], "Risky Analyst")


if __name__ == "__main__":
    unittest.main()
