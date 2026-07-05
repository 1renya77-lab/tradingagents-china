import unittest

from signal_positioning import derive_target_position, execution_summary


class SignalPositioningTest(unittest.TestCase):
    def test_extracts_midpoint_from_hold_position_range(self):
        self.assertAlmostEqual(
            derive_target_position("持有", "建议持有40%-50%仓位，等待突破确认"),
            0.45,
        )

    def test_extracts_upper_bound_from_below_position(self):
        self.assertAlmostEqual(
            derive_target_position("卖出", "当前390-395元区间应逢高减持至30%以下，空仓者不建仓"),
            0.30,
        )

    def test_final_below_position_overrides_later_debate_range(self):
        self.assertAlmostEqual(
            derive_target_position(
                "卖出",
                "当前390-395元区间应逢高减持至30%以下，空仓者不建仓。\n"
                "| 中性 | 平衡仓位 | 30%-40% | 378元 |",
            ),
            0.30,
        )

    def test_extracts_probe_position_range(self):
        self.assertAlmostEqual(
            derive_target_position("持有", "空仓者可试探性建仓5-8%，等待放量突破"),
            0.065,
        )

    def test_reduce_by_range_maps_to_remaining_position(self):
        self.assertAlmostEqual(
            derive_target_position("卖出", "委员会最终裁决：卖出，建议减仓50%-70%"),
            0.40,
        )

    def test_action_default_is_used_when_no_position_text_exists(self):
        self.assertAlmostEqual(derive_target_position("买入", "趋势突破"), 0.80)
        self.assertAlmostEqual(derive_target_position("持有", "等待确认"), 0.50)
        self.assertAlmostEqual(derive_target_position("卖出", "风险较高"), 0.00)

    def test_execution_summary_explains_target_position_semantics(self):
        text = execution_summary("持有", 0.35)

        self.assertIn("原始操作=持有", text)
        self.assertIn("目标仓位=35.0%", text)
        self.assertIn("不是简单保持不动", text)


if __name__ == "__main__":
    unittest.main()
