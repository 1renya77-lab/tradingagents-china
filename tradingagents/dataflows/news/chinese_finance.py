#!/usr/bin/env python3
"""
中国财经数据聚合工具
由于微博API申请困难且功能受限，采用多源数据聚合的方式
"""

import requests
import json
import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import re
from bs4 import BeautifulSoup
import pandas as pd


class ChineseFinanceDataAggregator:
    """中国财经数据聚合器"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _safe_import_akshare(self):
        try:
            import akshare as ak
            return ak
        except Exception:
            return None
    
    def get_stock_sentiment_summary(self, ticker: str, curr_date: str, days: int = 7) -> Dict:
        """
        获取股票情绪分析汇总
        整合多个可获取的中国财经数据源
        """
        try:
            # 1. 获取财经新闻情绪
            as_of_date = self._parse_datetime(curr_date)
            news_sentiment = self._get_finance_news_sentiment(ticker, days, as_of_date)
            
            # 2. 获取股吧讨论热度 (如果可以获取)
            forum_sentiment = self._get_stock_forum_sentiment(ticker, days, as_of_date)
            
            # 3. 获取财经媒体报道
            media_sentiment = self._get_media_coverage_sentiment(ticker, days, as_of_date)
            
            # 4. 综合分析
            overall_sentiment = self._calculate_overall_sentiment(
                news_sentiment, forum_sentiment, media_sentiment
            )
            
            return {
                'ticker': ticker,
                'analysis_period': f'{days} days',
                'overall_sentiment': overall_sentiment,
                'news_sentiment': news_sentiment,
                'forum_sentiment': forum_sentiment,
                'media_sentiment': media_sentiment,
                'summary': self._generate_sentiment_summary(overall_sentiment),
                'timestamp': datetime.now().isoformat(),
                'as_of_date': curr_date,
            }
            
        except Exception as e:
            return {
                'ticker': ticker,
                'error': f'数据获取失败: {str(e)}',
                'fallback_message': '由于中国社交媒体API限制，建议使用财经新闻和基本面分析作为主要参考',
                'timestamp': datetime.now().isoformat(),
                'as_of_date': curr_date,
            }
    
    def _get_finance_news_sentiment(self, ticker: str, days: int, as_of_date: Optional[datetime]) -> Dict:
        """获取财经新闻情绪分析"""
        try:
            news_items = self._search_finance_news(ticker, days, as_of_date)
            
            # 简单的情绪分析
            positive_count = 0
            negative_count = 0
            neutral_count = 0
            
            for item in news_items:
                sentiment = self._analyze_text_sentiment(item.get('title', '') + ' ' + item.get('content', ''))
                if sentiment > 0.1:
                    positive_count += 1
                elif sentiment < -0.1:
                    negative_count += 1
                else:
                    neutral_count += 1
            
            total = len(news_items)
            if total == 0:
                return {'sentiment_score': 0, 'confidence': 0, 'news_count': 0}
            
            sentiment_score = (positive_count - negative_count) / total
            
            return {
                'sentiment_score': sentiment_score,
                'positive_ratio': positive_count / total,
                'negative_ratio': negative_count / total,
                'neutral_ratio': neutral_count / total,
                'news_count': total,
                'confidence': min(total / 10, 1.0),
                'sample_titles': [item.get('title', '') for item in news_items[:5]],
            }
            
        except Exception as e:
            return {'error': str(e), 'sentiment_score': 0, 'confidence': 0}
    
    def _get_stock_forum_sentiment(self, ticker: str, days: int, as_of_date: Optional[datetime]) -> Dict:
        """获取股票论坛讨论情绪，优先使用公开可访问的股吧数据。"""
        ak = self._safe_import_akshare()
        if ak is None:
            return {
                'sentiment_score': 0,
                'discussion_count': 0,
                'hot_topics': [],
                'note': 'AKShare 不可用，未能获取股吧讨论数据',
                'confidence': 0,
            }

        try:
            discussions: List[Dict[str, Any]] = []
            forum_funcs = [
                getattr(ak, "stock_guba_em", None),
                getattr(ak, "stock_comment_em", None),
            ]
            for func in forum_funcs:
                if func is None:
                    continue
                try:
                    df = func(symbol=ticker)
                    if df is not None and not df.empty:
                        discussions = self._filter_records_by_as_of_date(
                            df.head(30).to_dict("records"),
                            ["time", "发布时间", "日期", "发帖时间", "更新时间"],
                            as_of_date,
                        )
                        break
                except Exception:
                    continue

            if not discussions:
                return {
                    'sentiment_score': 0,
                    'discussion_count': 0,
                    'hot_topics': [],
                    'note': '当前未抓取到股吧公开讨论数据',
                    'confidence': 0,
                }

            scores = []
            hot_topics = []
            for item in discussions:
                title = str(item.get('title') or item.get('帖子标题') or item.get('post_title') or '')
                summary = str(item.get('summary') or item.get('帖子内容') or item.get('post_content') or '')
                if title:
                    hot_topics.append(title[:40])
                scores.append(self._analyze_text_sentiment(f"{title} {summary}"))

            avg_score = sum(scores) / len(scores) if scores else 0
            return {
                'sentiment_score': avg_score,
                'discussion_count': len(discussions),
                'hot_topics': hot_topics[:5],
                'confidence': min(len(discussions) / 20, 1.0),
                'source': 'eastmoney_guba_public',
            }
        except Exception as e:
            return {
                'sentiment_score': 0,
                'discussion_count': 0,
                'hot_topics': [],
                'note': f'股吧公开数据获取失败: {e}',
                'confidence': 0,
            }
    
    def _get_media_coverage_sentiment(self, ticker: str, days: int, as_of_date: Optional[datetime]) -> Dict:
        """获取媒体报道情绪"""
        try:
            coverage_items = self._get_media_coverage(ticker, days, as_of_date)
            
            if not coverage_items:
                return {'sentiment_score': 0, 'coverage_count': 0, 'confidence': 0}
            
            # 分析媒体报道的情绪倾向
            sentiment_scores = []
            for item in coverage_items:
                score = self._analyze_text_sentiment(item.get('title', '') + ' ' + item.get('summary', ''))
                sentiment_scores.append(score)
            
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
            
            return {
                'sentiment_score': avg_sentiment,
                'coverage_count': len(coverage_items),
                'confidence': min(len(coverage_items) / 5, 1.0),
                'sample_titles': [item.get('title', '') for item in coverage_items[:5]],
            }
            
        except Exception as e:
            return {'error': str(e), 'sentiment_score': 0, 'confidence': 0}
    
    def _search_finance_news(self, search_term: str, days: int, as_of_date: Optional[datetime]) -> List[Dict]:
        """搜索财经新闻，优先用 AKShare 个股新闻公开接口。"""
        ak = self._safe_import_akshare()
        if ak is None:
            return []

        news_items: List[Dict[str, Any]] = []
        try:
            if re.fullmatch(r"\d{6}", search_term):
                df = ak.stock_news_em(symbol=search_term)
                if df is not None and not df.empty:
                    cutoff_anchor = as_of_date or datetime.now()
                    cutoff = cutoff_anchor - timedelta(days=days)
                    as_of_end = cutoff_anchor.replace(hour=23, minute=59, second=59)
                    for _, row in df.head(20).iterrows():
                        raw_time = row.get('发布时间') or row.get('时间') or ''
                        parsed_time = self._parse_datetime(raw_time)
                        if parsed_time and parsed_time < cutoff:
                            continue
                        if parsed_time and parsed_time > as_of_end:
                            continue
                        news_items.append({
                            'title': str(row.get('新闻标题') or row.get('标题') or ''),
                            'content': str(row.get('新闻内容') or row.get('内容') or row.get('新闻摘要') or row.get('摘要') or ''),
                            'source': str(row.get('文章来源') or row.get('来源') or '东方财富'),
                            'publish_time': parsed_time.isoformat() if parsed_time else str(raw_time),
                            'url': str(row.get('新闻链接') or row.get('链接') or ''),
                        })
        except Exception:
            return []
        return [item for item in news_items if item.get('title')]

    def _get_media_coverage(self, ticker: str, days: int, as_of_date: Optional[datetime]) -> List[Dict]:
        """获取媒体报道，补充公告/龙虎榜等高可信公开事件。"""
        ak = self._safe_import_akshare()
        if ak is None:
            return []

        coverage_items: List[Dict[str, Any]] = []
        try:
            if hasattr(ak, "stock_notice_report"):
                notice_df = ak.stock_notice_report(symbol=ticker)
                if notice_df is not None and not notice_df.empty:
                    for _, row in notice_df.head(10).iterrows():
                        coverage_items.append({
                            'title': str(row.get('公告标题') or row.get('title') or row.get('名称') or '公司公告'),
                            'summary': str(row.get('公告内容') or row.get('内容') or row.get('摘要') or ''),
                            'source': '公司公告',
                            'publish_time': str(row.get('公告日期') or row.get('日期') or ''),
                        })
        except Exception:
            pass

        try:
            if hasattr(ak, "stock_lhb_stock_detail_em"):
                lhb_df = ak.stock_lhb_stock_detail_em(symbol=ticker)
                if lhb_df is not None and not lhb_df.empty:
                    for _, row in lhb_df.head(5).iterrows():
                        coverage_items.append({
                            'title': f"龙虎榜 {ticker}",
                            'summary': str(row.to_dict()),
                            'source': '东方财富龙虎榜',
                            'publish_time': str(row.get('上榜日') or row.get('日期') or ''),
                        })
        except Exception:
            pass

        return self._filter_records_by_as_of_date(
            coverage_items,
            ["publish_time", "公告日期", "日期", "上榜日"],
            as_of_date,
        )

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _filter_records_by_as_of_date(
        self,
        records: List[Dict[str, Any]],
        candidate_keys: List[str],
        as_of_date: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        if as_of_date is None:
            return records
        as_of_end = as_of_date.replace(hour=23, minute=59, second=59)
        filtered: List[Dict[str, Any]] = []
        for record in records:
            parsed_time = None
            for key in candidate_keys:
                parsed_time = self._parse_datetime(record.get(key))
                if parsed_time:
                    break
            if parsed_time and parsed_time > as_of_end:
                continue
            filtered.append(record)
        return filtered
    
    def _analyze_text_sentiment(self, text: str) -> float:
        """简单的中文文本情绪分析"""
        if not text:
            return 0
        
        # 简单的关键词情绪分析
        positive_words = ['上涨', '增长', '利好', '看好', '买入', '推荐', '强势', '突破', '创新高']
        negative_words = ['下跌', '下降', '利空', '看空', '卖出', '风险', '跌破', '创新低', '亏损']
        
        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)
        
        if positive_count + negative_count == 0:
            return 0
        
        return (positive_count - negative_count) / (positive_count + negative_count)
    
    def _get_company_chinese_name(self, ticker: str) -> Optional[str]:
        """获取公司中文名称"""
        if re.fullmatch(r"\d{6}", ticker):
            try:
                from tradingagents.dataflows.interface import get_china_stock_info_unified
                stock_info = get_china_stock_info_unified(ticker)
                if stock_info and "股票名称:" in stock_info:
                    return stock_info.split("股票名称:")[1].split("\n")[0].strip()
            except Exception:
                pass

        name_mapping = {
            'AAPL': '苹果',
            'TSLA': '特斯拉',
            'NVDA': '英伟达',
            'MSFT': '微软',
            'GOOGL': '谷歌',
            'AMZN': '亚马逊'
        }
        return name_mapping.get(ticker.upper())
    
    def _calculate_overall_sentiment(self, news_sentiment: Dict, forum_sentiment: Dict, media_sentiment: Dict) -> Dict:
        """计算综合情绪分析"""
        # 根据各数据源的置信度加权计算
        news_weight = news_sentiment.get('confidence', 0)
        forum_weight = forum_sentiment.get('confidence', 0)
        media_weight = media_sentiment.get('confidence', 0)
        
        total_weight = news_weight + forum_weight + media_weight
        
        if total_weight == 0:
            return {'sentiment_score': 0, 'confidence': 0, 'level': 'neutral'}
        
        weighted_sentiment = (
            news_sentiment.get('sentiment_score', 0) * news_weight +
            forum_sentiment.get('sentiment_score', 0) * forum_weight +
            media_sentiment.get('sentiment_score', 0) * media_weight
        ) / total_weight
        
        # 确定情绪等级
        if weighted_sentiment > 0.3:
            level = 'very_positive'
        elif weighted_sentiment > 0.1:
            level = 'positive'
        elif weighted_sentiment > -0.1:
            level = 'neutral'
        elif weighted_sentiment > -0.3:
            level = 'negative'
        else:
            level = 'very_negative'
        
        return {
            'sentiment_score': weighted_sentiment,
            'confidence': total_weight / 3,  # 平均置信度
            'level': level
        }
    
    def _generate_sentiment_summary(self, overall_sentiment: Dict) -> str:
        """生成情绪分析摘要"""
        level = overall_sentiment.get('level', 'neutral')
        score = overall_sentiment.get('sentiment_score', 0)
        confidence = overall_sentiment.get('confidence', 0)
        
        level_descriptions = {
            'very_positive': '非常积极',
            'positive': '积极',
            'neutral': '中性',
            'negative': '消极',
            'very_negative': '非常消极'
        }
        
        description = level_descriptions.get(level, '中性')
        confidence_level = '高' if confidence > 0.7 else '中' if confidence > 0.3 else '低'
        
        return f"市场情绪: {description} (评分: {score:.2f}, 置信度: {confidence_level})"


def get_chinese_social_sentiment(ticker: str, curr_date: str) -> str:
    """
    获取中国社交媒体情绪分析的主要接口函数
    """
    aggregator = ChineseFinanceDataAggregator()
    
    try:
        # 获取情绪分析数据
        sentiment_data = aggregator.get_stock_sentiment_summary(ticker, curr_date=curr_date, days=7)
        
        # 格式化输出
        if 'error' in sentiment_data:
            return f"""
中国市场情绪分析报告 - {ticker}
分析日期: {curr_date}
数据截止日期: {curr_date} 23:59:59

⚠️ 数据获取限制说明:
{sentiment_data.get('fallback_message', '数据获取遇到技术限制')}

建议:
1. 重点关注财经新闻和基本面分析
2. 参考官方财报和业绩指导
3. 关注行业政策和监管动态
4. 考虑国际市场情绪对中概股的影响

注: 由于中国社交媒体平台API限制，当前主要依赖公开财经数据源进行分析。
"""
        
        overall = sentiment_data.get('overall_sentiment', {})
        news = sentiment_data.get('news_sentiment', {})
        forum = sentiment_data.get('forum_sentiment', {})
        media = sentiment_data.get('media_sentiment', {})
        
        return f"""
中国市场情绪分析报告 - {ticker}
分析日期: {curr_date}
数据截止日期: {curr_date} 23:59:59
分析周期: {sentiment_data.get('analysis_period', '7天')}

📊 综合情绪评估:
{sentiment_data.get('summary', '数据不足')}

📰 财经新闻情绪:
- 情绪评分: {news.get('sentiment_score', 0):.2f}
- 正面新闻比例: {news.get('positive_ratio', 0):.1%}
- 负面新闻比例: {news.get('negative_ratio', 0):.1%}
- 新闻数量: {news.get('news_count', 0)}条

💬 投资社区情绪:
- 情绪评分: {forum.get('sentiment_score', 0):.2f}
- 讨论数量: {forum.get('discussion_count', 0)}条
- 热门话题: {', '.join(forum.get('hot_topics', [])[:3]) or '暂无'}

📢 公告/事件情绪:
- 情绪评分: {media.get('sentiment_score', 0):.2f}
- 事件数量: {media.get('coverage_count', 0)}条
- 代表事件: {', '.join(media.get('sample_titles', [])[:3]) or '暂无'}

💡 投资建议:
基于当前可获取的中国市场数据，建议投资者:
1. 密切关注官方财经媒体报道
2. 重视基本面分析和财务数据
3. 考虑政策环境对股价的影响
4. 关注国际市场动态

⚠️ 数据说明:
本分析优先基于公开可访问的个股新闻、股吧讨论、公告/龙虎榜事件。
雪球、同花顺问财等需要进一步接入专门数据源时，可继续增强。

报告生成时间: {sentiment_data.get('timestamp', datetime.now().isoformat())}
分析截止日期: {sentiment_data.get('as_of_date', curr_date)} 23:59:59
"""
        
    except Exception as e:
        return f"""
中国市场情绪分析 - {ticker}
分析日期: {curr_date}

❌ 分析失败: {str(e)}

💡 替代建议:
1. 查看财经新闻网站的相关报道
2. 关注雪球、东方财富等投资社区讨论
3. 参考专业机构的研究报告
4. 重点分析基本面和技术面数据

注: 中国社交媒体数据获取存在技术限制，建议以基本面分析为主。
"""
