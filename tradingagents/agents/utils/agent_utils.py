from typing import Annotated
from langchain_core.messages import RemoveMessage, HumanMessage
from langchain_core.tools import tool

from tradingagents.default_config import DEFAULT_CONFIG


def create_msg_delete():
    def delete_messages(state):
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")
        return {"messages": removal_operations + [placeholder]}

    return delete_messages


class Toolkit:
    _config = DEFAULT_CONFIG.copy()

    @classmethod
    def update_config(cls, config):
        cls._config.update(config)

    @property
    def config(self):
        return self._config

    def __init__(self, config=None):
        if config:
            self.update_config(config)

    @staticmethod
    @tool
    def get_stock_market_data_unified(
        ticker: Annotated[str, "股票代码（支持A股、港股、美股）"],
        start_date: Annotated[str, "开始日期，格式：YYYY-MM-DD"],
        end_date: Annotated[str, "结束日期，格式：YYYY-MM-DD"],
    ) -> str:
        """
        统一的股票市场数据工具。
        自动识别股票类型（A股/港股/美股）并调用对应数据源，获取价格和技术指标。

        Args:
            ticker: 股票代码，如 000001、0700.HK、AAPL
            start_date: 开始日期，格式 YYYY-MM-DD
            end_date: 结束日期，格式 YYYY-MM-DD

        Returns:
            str: 市场数据和技术分析报告
        """
        from tradingagents.utils.stock_utils import StockUtils
        from tradingagents.dataflows.interface import get_china_stock_data_unified, get_hk_stock_data_unified

        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']

        try:
            if is_china:
                data = get_china_stock_data_unified(ticker, start_date, end_date)
                return f"## A股市场数据\n{data}"
            elif is_hk:
                data = get_hk_stock_data_unified(ticker, start_date, end_date)
                return f"## 港股市场数据\n{data}"
            else:
                from tradingagents.dataflows.providers.us.optimized import get_us_stock_data_cached
                data = get_us_stock_data_cached(ticker, start_date, end_date)
                return f"## 美股市场数据\n{data}"
        except Exception as e:
            return f"市场数据获取失败: {str(e)}"

    @staticmethod
    @tool
    def get_stock_fundamentals_unified(
        ticker: Annotated[str, "股票代码（支持A股、港股、美股）"],
        start_date: Annotated[str, "开始日期，格式：YYYY-MM-DD"] = None,
        end_date: Annotated[str, "结束日期，格式：YYYY-MM-DD"] = None,
        curr_date: Annotated[str, "当前日期，格式：YYYY-MM-DD"] = None,
    ) -> str:
        """
        统一的股票基本面分析工具。
        自动识别股票类型并调用对应数据源。

        Args:
            ticker: 股票代码
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            curr_date: 当前日期

        Returns:
            str: 基本面分析数据和报告
        """
        from tradingagents.utils.stock_utils import StockUtils
        from tradingagents.dataflows.interface import get_china_stock_data_unified
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
        from datetime import datetime, timedelta

        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']

        if not curr_date:
            curr_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = curr_date

        result_data = []

        try:
            if is_china:
                recent_end = curr_date
                recent_start = (datetime.strptime(curr_date, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d')
                price_data = get_china_stock_data_unified(ticker, recent_start, recent_end)
                result_data.append(f"## A股当前价格信息\n{price_data}")

                analyzer = OptimizedChinaDataProvider()
                fund_data = analyzer._generate_fundamentals_report(ticker, price_data, "standard", curr_date=curr_date)
                result_data.append(f"## A股基本面财务数据\n{fund_data}")

            elif is_hk:
                from tradingagents.dataflows.interface import get_hk_stock_data_unified as get_hk_data
                hk_data = get_hk_data(ticker, start_date, end_date)
                result_data.append(f"## 港股数据\n{hk_data}")

            else:
                from tradingagents.dataflows.interface import get_fundamentals_openai as get_us_fund
                us_data = get_us_fund(ticker, curr_date)
                result_data.append(f"## 美股基本面数据\n{us_data}")

        except Exception as e:
            result_data.append(f"数据获取失败: {str(e)}")

        return f"""# {ticker} 基本面分析数据

**股票类型**: {market_info['market_name']}
**货币**: {market_info['currency_name']} ({market_info['currency_symbol']})
**分析日期**: {curr_date}

{chr(10).join(result_data)}
"""

    @staticmethod
    @tool
    def get_stock_news_unified(
        ticker: Annotated[str, "股票代码（支持A股、港股、美股）"],
        curr_date: Annotated[str, "当前日期，格式：YYYY-MM-DD"],
    ) -> str:
        """
        统一的股票新闻工具。
        自动识别股票类型并调用对应新闻源。

        Args:
            ticker: 股票代码
            curr_date: 当前日期

        Returns:
            str: 新闻分析报告
        """
        from tradingagents.utils.stock_utils import StockUtils
        from tradingagents.dataflows.providers.china.akshare import AKShareProvider
        from datetime import datetime, timedelta

        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']

        end_dt = datetime.strptime(curr_date, '%Y-%m-%d')
        start_dt = end_dt - timedelta(days=7)
        start_str = start_dt.strftime('%Y-%m-%d')

        result_data = []

        try:
            if is_china or is_hk:
                clean_ticker = ticker.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                               .replace('.HK', '').replace('.XSHE', '').replace('.XSHG', '')

                provider = AKShareProvider()
                news_df = provider.get_stock_news_sync(symbol=clean_ticker)

                if news_df is not None and not news_df.empty:
                    items = []
                    for _, row in news_df.iterrows():
                        title = row.get('新闻标题', '') or row.get('标题', '')
                        time = row.get('发布时间', '') or row.get('时间', '')
                        url = row.get('新闻链接', '') or row.get('链接', '')
                        items.append(f"- **{title}** [{time}]({url})")
                    result_data.append(f"## 东方财富新闻\n" + "\n".join(items))

                from tradingagents.dataflows.interface import get_google_news
                query = f"{clean_ticker} 股票 公司 财报 新闻" if is_china else f"{ticker} 港股"
                google_news = get_google_news(query, curr_date)
                result_data.append(f"## Google新闻\n{google_news}")

            else:
                from tradingagents.dataflows.interface import get_finnhub_news
                news = get_finnhub_news(ticker, start_str, curr_date)
                result_data.append(f"## 美股新闻\n{news}")

        except Exception as e:
            result_data.append(f"新闻获取失败: {str(e)}")

        return f"""# {ticker} 新闻分析

**股票类型**: {market_info['market_name']}
**分析日期**: {curr_date}
**新闻时间范围**: {start_str} 至 {curr_date}

{chr(10).join(result_data)}
"""

    @staticmethod
    @tool
    def get_stock_sentiment_unified(
        ticker: Annotated[str, "股票代码（支持A股、港股、美股）"],
        curr_date: Annotated[str, "当前日期，格式：YYYY-MM-DD"],
    ) -> str:
        """
        统一的股票情绪分析工具。
        自动识别股票类型并调用对应情绪数据源。

        Args:
            ticker: 股票代码
            curr_date: 当前日期

        Returns:
            str: 情绪分析报告
        """
        from tradingagents.utils.stock_utils import StockUtils
        from tradingagents.dataflows.news.chinese_finance import get_chinese_social_sentiment
        from tradingagents.dataflows.interface import get_reddit_company_news

        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']

        result_data = []

        try:
            if is_china or is_hk:
                sentiment = get_chinese_social_sentiment(ticker, curr_date)
                result_data.append(sentiment)
            else:
                sentiment = get_reddit_company_news(ticker, curr_date, 7, 5)
                result_data.append(f"## 美股Reddit情绪\n{sentiment}")
        except Exception as e:
            result_data.append(f"情绪数据获取失败: {str(e)}")

        return f"""# {ticker} 情绪分析

**股票类型**: {market_info['market_name']}
**分析日期**: {curr_date}

{chr(10).join(result_data)}
"""
