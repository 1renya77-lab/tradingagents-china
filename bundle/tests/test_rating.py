import unittest

from tradingagents.agents.utils.rating import parse_rating


class ParseRatingTest(unittest.TestCase):
    def test_parses_chinese_sell_decision(self):
        text = "**决策结论：卖出。** 立即规避本金永久性损失风险。"
        self.assertEqual(parse_rating(text), "Sell")

    def test_parses_chinese_buy_and_hold_decisions(self):
        self.assertEqual(parse_rating("最终建议：买入，分批建仓。"), "Buy")
        self.assertEqual(parse_rating("建议：持有，等待更明确的信号。"), "Hold")


if __name__ == "__main__":
    unittest.main()
