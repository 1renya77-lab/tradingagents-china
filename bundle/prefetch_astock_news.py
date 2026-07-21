#!/usr/bin/env python3
"""Prefetch A-share news and announcements into a cutoff-safe local cache."""

from __future__ import annotations

import argparse
from pathlib import Path

from tradingagents.dataflows.astock_data_provider import (
    cninfo_announcements,
    eastmoney_stock_news,
    enrich_cninfo_announcement_texts,
)
from tradingagents.dataflows.local_prefetch_cache import (
    NEWS_SOURCE_CNINFO,
    NEWS_SOURCE_EASTMONEY,
    news_cache_path,
    save_news_items,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prefetch A-share news/announcement data for local reuse.")
    parser.add_argument("--ticker", required=True, help="A-share ticker, e.g. 300308")
    parser.add_argument("--end", required=True, help="Latest signal date YYYY-MM-DD; cache may include newer raw rows but agent filtering remains cutoff-safe")
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--announcement-text-limit", type=int, default=10,
                        help="Number of CNInfo PDF announcements to download and extract with pdftotext; 0 disables text extraction")
    parser.add_argument("--skip-eastmoney", action="store_true", help="Do not prefetch EastMoney stock news")
    parser.add_argument("--skip-cninfo", action="store_true", help="Do not prefetch CNInfo announcements")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fetched: list[tuple[str, int, Path]] = []

    if not args.skip_eastmoney:
        news = eastmoney_stock_news(
            args.ticker,
            page_size=args.page_size,
            cutoff_date=args.end,
            max_pages=args.max_pages,
        )
        path = save_news_items(args.ticker, NEWS_SOURCE_EASTMONEY, news, origin="eastmoney_prefetch")
        fetched.append(("eastmoney_news", len(news), path))

    if not args.skip_cninfo:
        announcements = cninfo_announcements(
            args.ticker,
            page_size=args.page_size,
            cutoff_date=args.end,
            max_pages=args.max_pages,
        )
        if args.announcement_text_limit > 0:
            announcements = enrich_cninfo_announcement_texts(
                announcements,
                max_items=args.announcement_text_limit,
            )
        path = save_news_items(args.ticker, NEWS_SOURCE_CNINFO, announcements, origin="cninfo_prefetch")
        fetched.append(("cninfo_announcements", len(announcements), path))

    print("A-stock news/announcement data prefetched")
    print(f"ticker      : {args.ticker}")
    print(f"end         : {args.end}")
    print(f"page_size   : {args.page_size}")
    print(f"max_pages   : {args.max_pages}")
    for name, rows, path in fetched:
        print(f"{name:<20}: rows={rows}, cache_path={path}")
    print(f"active_news : {news_cache_path(args.ticker, NEWS_SOURCE_EASTMONEY)}")
    print(f"active_cninfo: {news_cache_path(args.ticker, NEWS_SOURCE_CNINFO)}")
    print("cutoff_rule : later agent calls still receive only rows <= their signal cutoff time")


if __name__ == "__main__":
    main()
