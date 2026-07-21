import unittest

from build_minimal_qlib_provider import format_index_instrument, parse_csv_arg


class QlibProviderBuilderTest(unittest.TestCase):
    def test_parse_csv_arg(self):
        self.assertEqual(parse_csv_arg("300308, 300750,,601899"), ["300308", "300750", "601899"])

    def test_format_index_instrument(self):
        self.assertEqual(format_index_instrument("000300"), "SH000300")
        self.assertEqual(format_index_instrument("SH000905"), "SH000905")


if __name__ == "__main__":
    unittest.main()
