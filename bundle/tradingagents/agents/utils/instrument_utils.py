def build_instrument_context(ticker: str) -> str:
    normalized_ticker = str(ticker).strip().upper()
    base_context = (
        f"当前分析标的的精确股票代码是 `{normalized_ticker}`。"
        "在所有工具调用、分析报告、交易建议和最终结论中，都必须使用这个完全一致的股票代码。"
        "如果代码带有交易所后缀，例如 `.HK`、`.TO`、`.L`、`.T`，必须原样保留，绝对不能省略、改写或替换。"
    )
    if len(normalized_ticker) == 6 and normalized_ticker.isdigit():
        return (
            base_context +
            "当前标的是中国A股。交易建议必须符合A股普通股票交易语境："
            "不能建议裸卖空、做空、建立空头仓位或使用美股式 short 操作；"
            "如果判断下跌风险，表达为卖出已有持仓、减仓、止损、观望或空仓等待。"
            "同时考虑A股T+1交易、涨跌停限制、流动性和交易成本约束。"
        )
    return base_context
