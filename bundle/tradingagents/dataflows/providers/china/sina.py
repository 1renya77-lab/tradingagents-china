# TradingAgents/dataflows/providers/china/sina.py

"""
新浪财经数据源 provider
使用新浪财经K线API作为主要数据源（已验证网络代理可用）
- K线: https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
- 行情: https://hq.sinajs.cn/list=sz300308
- 财务: https://vip.stock.finance.sina.com.cn
"""

import json
import time
import asyncio
import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import quote

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class SinaProvider:
    """新浪财经数据源 provider - 适用于有网络代理的环境"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.timeout = 10
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://finance.sina.com.cn/',
        })

    def _normalize_a_share_symbol(self, symbol: str) -> str:
        """标准化A股代码: 300308 -> sz300308"""
        code = str(symbol).strip().zfill(6)
        if code.startswith(('60', '68', '90')):
            return f"sh{code}"
        else:
            return f"sz{code}"

    def get_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """
        从新浪财经获取K线数据

        Args:
            symbol: 6位股票代码
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            period: daily/weekly/monthly

        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        try:
            full_symbol = self._normalize_a_share_symbol(symbol)

            # scale: 240=日K, 1680=周K, 7680=月K
            scale_map = {"daily": 240, "weekly": 1680, "monthly": 7680}
            scale = scale_map.get(period, 240)

            # 计算需要的K线数量（按30天/月计算）
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                days = max((end_dt - start_dt).days + 30, 60)
                datalen = min(days * 2, 500)  # 多取一些数据
            except Exception:
                datalen = 200

            url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
            params = {
                "symbol": full_symbol,
                "scale": scale,
                "ma": "no",
                "datalen": datalen
            }

            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code != 200:
                logger.error(f"❌ 新浪K线API错误: {response.status_code}")
                return None

            data = response.json()
            if not data or not isinstance(data, list):
                logger.warning(f"⚠️ 新浪K线数据为空: {symbol}")
                return None

            # 转换为DataFrame
            df = pd.DataFrame(data)
            df = df.rename(columns={
                "day": "date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume"
            })

            # 过滤日期
            df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()

            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            df = df.reset_index(drop=True)
            logger.info(f"✅ 新浪K线: {symbol} {len(df)}条 ({start_date} ~ {end_date})")
            return df

        except Exception as e:
            logger.error(f"❌ 新浪K线失败 {symbol}: {e}")
            return None

    def get_realtime_quote(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情（使用腾讯API更稳定）"""
        try:
            full_symbol = self._normalize_a_share_symbol(symbol)
            # 使用腾讯行情API
            url = f"https://qt.gtimg.cn/q={full_symbol}"
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code != 200:
                return {}

            text = response.text
            # 解析格式: v_sz300308="1~名称~代码~现价~昨收~今开~成交量~外盘~内盘..."
            match = re.search(r'"([^"]+)"', text)
            if not match:
                return {}

            parts = match.group(1).split('~')
            if len(parts) < 40:
                return {}

            # 腾讯行情字段顺序: [0]=类型, [1]=名称, [2]=代码, [3]=现价, [4]=昨收,
            # [5]=今开, [6]=成交量(手), [9]=成交额, [30]=日期, [31]=时间,
            # [32]=涨跌额, [33]=涨跌幅(%), [44]=最高, [45]=最低
            return {
                "name": parts[1] if len(parts) > 1 else "",
                "symbol": parts[2] if len(parts) > 2 else "",
                "price": float(parts[3] or 0),
                "pre_close": float(parts[4] or 0),
                "open": float(parts[5] or 0),
                "volume": int(float(parts[6] or 0) * 100),  # 手→股
                "amount": float(parts[9] or 0) * 10000,  # 万元→元
                "high": float(parts[44] or 0) if len(parts) > 44 else 0,
                "low": float(parts[45] or 0) if len(parts) > 45 else 0,
                "change": float(parts[32] or 0) if len(parts) > 32 else 0,
                "change_percent": float(parts[33] or 0) if len(parts) > 33 else 0,
                "date": parts[30] if len(parts) > 30 else "",
                "time": parts[31] if len(parts) > 31 else "",
            }
        except Exception as e:
            logger.error(f"❌ 腾讯行情失败 {symbol}: {e}")
            return {}

    def get_company_info(self, symbol: str) -> Dict[str, Any]:
        """从新浪获取公司基本信息"""
        try:
            url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCI_CorpInfo/stockid/{symbol}.phtml"
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code != 200:
                return {}

            text = response.text
            # 解析公司名称
            name_match = re.search(r'股票名称[：:]\s*<[^>]+>([^<]+)<', text)
            industry_match = re.search(r'所属行业[：:]\s*<[^>]+>([^<]+)<', text)

            return {
                "name": name_match.group(1) if name_match else "",
                "industry": industry_match.group(1) if industry_match else "",
            }
        except Exception as e:
            logger.error(f"❌ 新浪公司信息失败 {symbol}: {e}")
            return {}

    def test_connection(self) -> bool:
        """测试连接"""
        try:
            url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
            params = {"symbol": "sz300308", "scale": 240, "ma": "no", "datalen": 5}
            response = self.session.get(url, params=params, timeout=5)
            return response.status_code == 200 and len(response.text) > 10
        except Exception:
            return False


# 全局实例
_sina_provider = None

def get_sina_provider() -> SinaProvider:
    """获取新浪provider单例"""
    global _sina_provider
    if _sina_provider is None:
        _sina_provider = SinaProvider()
    return _sina_provider
