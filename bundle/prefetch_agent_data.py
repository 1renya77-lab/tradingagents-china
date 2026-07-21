#!/usr/bin/env python3
"""Prefetch and preflight-check all A-share agent data before LLM execution."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from prefetch_market_data import build_prefetch_start, fetch_market_data
from tradingagents.dataflows.astock_data_provider import (
    _filter_temporal_items,
    cninfo_announcements,
    eastmoney_stock_info,
    eastmoney_stock_news,
    enrich_cninfo_announcement_texts,
    fetch_baostock_financial_indicators,
    get_astock_fundamentals_report,
    get_astock_news_report,
    sina_financial_report,
)
from tradingagents.dataflows.local_prefetch_cache import (
    NEWS_SOURCE_CNINFO,
    NEWS_SOURCE_EASTMONEY,
    load_market_slice,
    load_json_data,
    load_news_items,
    save_json_data,
    save_market_data,
    save_news_items,
)
from tradingagents.dataflows.news.chinese_finance import ChineseFinanceDataAggregator


ROOT = Path(__file__).resolve().parent


def _normalize_cached_news_snapshot(
    items: list[dict] | None,
    snapshot_date: str,
    time_keys: tuple[str, ...],
) -> list[dict]:
    return _filter_temporal_items(list(items or []), snapshot_date, time_keys, lookback_days=None)


def _is_valid_social_snapshot(payload: object, snapshot_date: str) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("as_of_date", "")).strip() != snapshot_date:
        return False
    data_quality = payload.get("data_quality")
    return isinstance(data_quality, dict) and str(data_quality.get("cutoff_date", "")).startswith(snapshot_date)


def _social_snapshot_stats(payload: object) -> dict[str, int | bool]:
    if not isinstance(payload, dict):
        return {
            "discussion_rows": 0,
            "event_rows": 0,
            "forum_rows": 0,
            "xueqiu_rows": 0,
            "irm_rows": 0,
            "news_rows": 0,
            "cninfo_event_rows": 0,
            "cached": False,
        }
    forum = payload.get("forum_sentiment", {}) if isinstance(payload.get("forum_sentiment"), dict) else {}
    xueqiu = payload.get("xueqiu_sentiment", {}) if isinstance(payload.get("xueqiu_sentiment"), dict) else {}
    irm = payload.get("irm_sentiment", {}) if isinstance(payload.get("irm_sentiment"), dict) else {}
    news = payload.get("news_sentiment", {}) if isinstance(payload.get("news_sentiment"), dict) else {}
    cninfo = payload.get("cninfo_sentiment", {}) if isinstance(payload.get("cninfo_sentiment"), dict) else {}
    forum_rows = int(forum.get("discussion_count", 0) or 0)
    xueqiu_rows = int(xueqiu.get("post_count", 0) or 0)
    irm_rows = int(irm.get("irm_count", 0) or 0)
    news_rows = int(news.get("news_count", 0) or 0)
    cninfo_event_rows = int(cninfo.get("event_count", 0) or 0)
    return {
        "discussion_rows": forum_rows + xueqiu_rows + irm_rows,
        "event_rows": news_rows + cninfo_event_rows,
        "forum_rows": forum_rows,
        "xueqiu_rows": xueqiu_rows,
        "irm_rows": irm_rows,
        "news_rows": news_rows,
        "cninfo_event_rows": cninfo_event_rows,
        "cached": True,
    }


def build_signal_dates(start_date: str, end_date: str, frequency: str) -> list[str]:
    days = pd.date_range(start=start_date, end=end_date, freq="B")
    if frequency == "daily":
        return [d.strftime("%Y-%m-%d") for d in days]
    if frequency == "weekly":
        return [
            d.strftime("%Y-%m-%d")
            for d in pd.DatetimeIndex(days.to_series().groupby(days.to_period("W")).tail(1))
        ]
    raise ValueError("frequency must be daily or weekly")


def build_snapshot_dates(start_date: str, end_date: str, frequency: str, mode: str) -> list[str]:
    if mode == "signal_dates":
        return build_signal_dates(start_date, end_date, frequency)
    if mode == "daily":
        return [d.strftime("%Y-%m-%d") for d in pd.date_range(start=start_date, end=end_date, freq="B")]
    raise ValueError("snapshot mode must be signal_dates or daily")


def parse_headers(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in str(text or "").splitlines():
        match = re.match(r"^(DATA_QUALITY|DATA_SOURCE|DATA_VENDOR|ROWS|CUTOFF_DATE|WARNING):\s*(.*)$", line.strip())
        if match:
            headers[match.group(1)] = match.group(2)
    return headers


def prefetch_market(ticker: str, start: str, end: str, lookback_days: int, source: str) -> dict:
    fetch_start = build_prefetch_start(start, lookback_days)
    df, used_source = fetch_market_data(ticker, fetch_start, end, source)
    path = save_market_data(ticker, df, source=used_source)
    return {
        "source": used_source,
        "rows": int(len(df)),
        "fetch_start": fetch_start,
        "first_date": df["Date"].min().strftime("%Y-%m-%d") if not df.empty else "",
        "last_date": df["Date"].max().strftime("%Y-%m-%d") if not df.empty else "",
        "cache_path": str(path),
    }


def prefetch_news(
    ticker: str,
    snapshot_dates: list[str],
    page_size: int,
    max_pages: int,
    announcement_text_limit: int,
    workers: int = 4,
) -> dict:
    def _prefetch_news_snapshot(snapshot_date: str) -> dict:
        errors: list[str] = []
        news_path = None
        cninfo_path = None
        news_rows = 0
        announcement_rows = 0
        cninfo_text_rows = 0
        eastmoney_cached = False
        cninfo_cached = False

        cached_news = load_news_items(ticker, NEWS_SOURCE_EASTMONEY, snapshot_date=snapshot_date)
        if cached_news is not None:
            news = _normalize_cached_news_snapshot(cached_news, snapshot_date, ("time", "publish_time", "date"))
            news_path = save_news_items(
                ticker,
                NEWS_SOURCE_EASTMONEY,
                news,
                origin="agent_preflight",
                snapshot_date=snapshot_date,
                replace=True,
            )
            news_rows = len(news)
            eastmoney_cached = True
        else:
            try:
                news = eastmoney_stock_news(ticker, page_size=page_size, cutoff_date=snapshot_date, max_pages=max_pages)
                news = _filter_temporal_items(
                    news,
                    snapshot_date,
                    ("time", "publish_time", "date"),
                    lookback_days=None,
                )
                news_path = save_news_items(
                    ticker,
                    NEWS_SOURCE_EASTMONEY,
                    news,
                    origin="agent_preflight",
                    snapshot_date=snapshot_date,
                    replace=True,
                )
                news_rows = len(news)
            except Exception as exc:
                errors.append(f"eastmoney_news[{snapshot_date}]: {exc}")

        cached_announcements = load_news_items(ticker, NEWS_SOURCE_CNINFO, snapshot_date=snapshot_date)
        if cached_announcements is not None:
            announcements = _normalize_cached_news_snapshot(cached_announcements, snapshot_date, ("date", "publish_time"))
            cninfo_path = save_news_items(
                ticker,
                NEWS_SOURCE_CNINFO,
                announcements,
                origin="agent_preflight",
                snapshot_date=snapshot_date,
                replace=True,
            )
            announcement_rows = len(announcements)
            cninfo_text_rows = sum(1 for item in announcements if str(item.get("text_excerpt", "")).strip())
            cninfo_cached = True
        else:
            try:
                announcements = cninfo_announcements(ticker, page_size=page_size, cutoff_date=snapshot_date, max_pages=max_pages)
                announcements = _filter_temporal_items(
                    announcements,
                    snapshot_date,
                    ("date", "publish_time"),
                    lookback_days=None,
                )
                if announcement_text_limit > 0:
                    announcements = enrich_cninfo_announcement_texts(
                        announcements,
                        max_items=announcement_text_limit,
                    )
                cninfo_path = save_news_items(
                    ticker,
                    NEWS_SOURCE_CNINFO,
                    announcements,
                    origin="agent_preflight",
                    snapshot_date=snapshot_date,
                    replace=True,
                )
                announcement_rows = len(announcements)
                cninfo_text_rows = sum(1 for item in announcements if str(item.get("text_excerpt", "")).strip())
            except Exception as exc:
                errors.append(f"cninfo_announcements[{snapshot_date}]: {exc}")

        return {
            "snapshot_date": snapshot_date,
            "eastmoney_rows": news_rows,
            "cninfo_rows": announcement_rows,
            "cninfo_text_rows": cninfo_text_rows,
            "eastmoney_cached": eastmoney_cached,
            "cninfo_cached": cninfo_cached,
            "eastmoney_cache_path": str(news_path) if news_path else "",
            "cninfo_cache_path": str(cninfo_path) if cninfo_path else "",
            "errors": errors,
        }

    if not snapshot_dates:
        return {
            "eastmoney_rows": 0,
            "cninfo_rows": 0,
            "cninfo_text_rows": 0,
            "eastmoney_cached_dates": 0,
            "cninfo_cached_dates": 0,
            "eastmoney_cache_paths": [],
            "cninfo_cache_paths": [],
            "snapshot_dates": 0,
            "errors": [],
        }

    max_workers = max(1, min(int(workers or 1), len(snapshot_dates)))
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_prefetch_news_snapshot, snapshot_date): snapshot_date for snapshot_date in snapshot_dates
        }
        for future in as_completed(future_map):
            snapshot_date = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "snapshot_date": snapshot_date,
                        "eastmoney_rows": 0,
                        "cninfo_rows": 0,
                        "cninfo_text_rows": 0,
                        "eastmoney_cached": False,
                        "cninfo_cached": False,
                        "eastmoney_cache_path": "",
                        "cninfo_cache_path": "",
                        "errors": [f"prefetch_news_snapshot[{snapshot_date}]: {exc}"],
                    }
                )

    results.sort(key=lambda item: item["snapshot_date"])

    return {
        "eastmoney_rows": sum(item["eastmoney_rows"] for item in results),
        "cninfo_rows": sum(item["cninfo_rows"] for item in results),
        "cninfo_text_rows": sum(item["cninfo_text_rows"] for item in results),
        "eastmoney_cached_dates": sum(1 for item in results if item["eastmoney_cached"]),
        "cninfo_cached_dates": sum(1 for item in results if item["cninfo_cached"]),
        "eastmoney_cache_paths": [item["eastmoney_cache_path"] for item in results if item["eastmoney_cache_path"]],
        "cninfo_cache_paths": [item["cninfo_cache_path"] for item in results if item["cninfo_cache_path"]],
        "snapshot_dates": len(snapshot_dates),
        "errors": [err for item in results for err in item["errors"]],
    }


def prefetch_fundamentals(ticker: str) -> dict:
    errors: list[str] = []
    company_info = {}
    company_path = None
    try:
        company_info = eastmoney_stock_info(ticker)
        company_path = save_json_data(ticker, "fundamentals", "eastmoney_company_info", company_info)
    except Exception as exc:
        errors.append(f"eastmoney_company_info: {exc}")

    statements = {}
    for name, report_type in [
        ("income_statement", "lrb"),
        ("balance_sheet", "fzb"),
        ("cashflow", "llb"),
    ]:
        try:
            statements[name] = sina_financial_report(ticker, report_type)
        except Exception as exc:
            errors.append(f"sina_{name}: {exc}")
            statements[name] = []
    statements_path = save_json_data(ticker, "fundamentals", "sina_statements", statements)
    baostock_financials = {}
    baostock_path = None
    try:
        baostock_financials = fetch_baostock_financial_indicators(ticker)
        baostock_path = save_json_data(
            ticker,
            "fundamentals",
            "baostock_financial_indicators",
            baostock_financials,
        )
    except Exception as exc:
        errors.append(f"baostock_financial_indicators: {exc}")
    return {
        "company_info_ok": bool(company_info),
        "statement_rows": sum(len(v) for v in statements.values()),
        "baostock_financial_rows": sum(len(v) for v in baostock_financials.values()),
        "company_cache_path": str(company_path or ""),
        "statements_cache_path": str(statements_path),
        "baostock_financial_cache_path": str(baostock_path or ""),
        "errors": errors,
    }


def prefetch_social(ticker: str, signal_dates: list[str]) -> dict:
    aggregator = ChineseFinanceDataAggregator()
    paths: list[str] = []
    cached_dates = 0
    discussion_rows = 0
    event_rows = 0
    for date in signal_dates:
        payload = load_json_data(ticker, "social", f"sentiment_{date}")
        if _is_valid_social_snapshot(payload, date):
            cached_dates += 1
        else:
            try:
                payload = aggregator.get_stock_sentiment_summary(ticker, curr_date=date, days=7)
            except Exception as exc:
                payload = {"ticker": ticker, "as_of_date": date, "error": str(exc)}
        path = save_json_data(ticker, "social", f"sentiment_{date}", payload)
        paths.append(str(path))
        stats = _social_snapshot_stats(payload)
        discussion_rows += int(stats["discussion_rows"])
        event_rows += int(stats["event_rows"])
    return {
        "dates": len(signal_dates),
        "cache_paths": paths,
        "cached_dates": cached_dates,
        "discussion_rows": discussion_rows,
        "event_rows": event_rows,
    }


def build_preflight_rows(ticker: str, signal_dates: list[str], lookback_days: int) -> list[dict]:
    rows: list[dict] = []
    for date in signal_dates:
        market_start = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        market_df = load_market_slice(ticker, market_start, date)
        market_rows = 0 if market_df is None else len(market_df)

        news_report = get_astock_news_report(ticker, date)
        news_headers = parse_headers(news_report)

        fundamentals_report = get_astock_fundamentals_report(ticker, date)
        fundamentals_headers = parse_headers(fundamentals_report)

        social_payload = load_json_data(ticker, "social", f"sentiment_{date}") or {}
        social_stats = _social_snapshot_stats(social_payload)
        social_discussion_rows = int(social_stats["discussion_rows"])
        social_event_rows = int(social_stats["event_rows"])

        row = {
            "ticker": ticker,
            "signal_date": date,
            "market_ok": market_rows >= 20,
            "market_rows": market_rows,
            "news_ok": news_headers.get("DATA_QUALITY") == "ok=true",
            "news_rows": int(news_headers.get("ROWS") or 0),
            "fundamentals_ok": fundamentals_headers.get("DATA_QUALITY") == "ok=true",
            "fundamentals_rows": int(fundamentals_headers.get("ROWS") or 0),
            "social_discussion_ok": social_discussion_rows > 0,
            "social_discussion_rows": social_discussion_rows,
            "social_event_rows": social_event_rows,
            "social_forum_rows": int(social_stats["forum_rows"]),
            "social_xueqiu_rows": int(social_stats["xueqiu_rows"]),
            "social_irm_rows": int(social_stats["irm_rows"]),
            "social_news_rows": int(social_stats["news_rows"]),
            "social_cninfo_event_rows": int(social_stats["cninfo_event_rows"]),
            "social_snapshot_cached": bool(social_stats["cached"]),
            "news_warning": news_headers.get("WARNING", ""),
            "fundamentals_warning": fundamentals_headers.get("WARNING", ""),
        }
        row["all_core_ok"] = bool(row["market_ok"] and row["fundamentals_ok"])
        rows.append(row)
    return rows


def write_outputs(rows: list[dict], output_dir: Path, metadata: dict) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "preflight_data_quality.csv"
    json_path = output_dir / "preflight_data_quality.json"
    md_path = output_dir / "preflight_data_quality.md"

    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    payload = {"metadata": metadata, "rows": rows}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    df = pd.DataFrame(rows)
    lines = [
        "# Agent Data Preflight",
        "",
        f"- ticker: `{metadata['ticker']}`",
        f"- period: `{metadata['start']}` to `{metadata['end']}`",
        f"- frequency: `{metadata['frequency']}`",
        f"- signal_dates: `{len(rows)}`",
        f"- news_snapshot_mode: `{metadata['news_snapshot_mode']}`",
        f"- news_snapshot_dates: `{metadata['news_snapshot_dates']}`",
        f"- news_cached_dates: `eastmoney={metadata['news'].get('eastmoney_cached_dates', 0)}` / `cninfo={metadata['news'].get('cninfo_cached_dates', 0)}`",
        f"- social_cached_dates: `{metadata.get('social_summary', {}).get('cached_dates', 0)}`",
        "",
        "## Summary",
        "",
    ]
    if not df.empty:
        for col in ["market_ok", "news_ok", "fundamentals_ok", "social_discussion_ok", "all_core_ok"]:
            lines.append(f"- {col}: {int(df[col].sum())}/{len(df)}")
        lines.extend(["", "## Details", "", df.to_markdown(index=False)])
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {"csv": str(csv_path), "json": str(json_path), "md": str(md_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prefetch and preflight-check all data used by A-share agents.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--benchmark", default="SH000905")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--frequency", choices=["daily", "weekly"], default="weekly")
    parser.add_argument("--lookback-days", type=int, default=320)
    parser.add_argument("--market-source", choices=["auto", "akshare", "baostock"], default="auto")
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument(
        "--news-snapshot-mode",
        choices=["signal_dates", "daily"],
        default="signal_dates",
        help="Prefetch news/announcements only for signal dates, or for every business day in the range.",
    )
    parser.add_argument(
        "--skip-news-prefetch",
        action="store_true",
        help="Do not prefetch news/announcements during preflight.",
    )
    parser.add_argument("--announcement-text-limit", type=int, default=10,
                        help="Number of CNInfo PDF announcements to download and extract with pdftotext; 0 disables text extraction")
    parser.add_argument(
        "--news-prefetch-workers",
        type=int,
        default=4,
        help="Max concurrent workers for per-snapshot news/announcement prefetch.",
    )
    parser.add_argument("--run-name", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--fail-on-missing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    signal_dates = build_signal_dates(args.start, args.end, args.frequency)
    news_snapshot_dates = build_snapshot_dates(args.start, args.end, args.frequency, args.news_snapshot_mode)
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else ROOT / "outputs" / "runs" / (args.run_name or f"{args.ticker}_data_preflight") / "data_preflight"
    )

    print("Step 1/5: prefetching market data...")
    market = prefetch_market(args.ticker, args.start, args.end, args.lookback_days, args.market_source)
    print(f"  market rows={market['rows']} source={market['source']}")
    benchmark_market = None
    if args.benchmark:
        print("Step 1b/5: prefetching benchmark market data...")
        benchmark_market = prefetch_market(args.benchmark, args.start, args.end, args.lookback_days, args.market_source)
        print(
            f"  benchmark={args.benchmark} rows={benchmark_market['rows']} source={benchmark_market['source']}"
        )

    print("Step 2/5: prefetching news and announcements...")
    if args.skip_news_prefetch:
        news = {
            "skipped": True,
            "eastmoney_rows": 0,
            "cninfo_rows": 0,
            "cninfo_text_rows": 0,
            "eastmoney_cache_paths": [],
            "cninfo_cache_paths": [],
            "snapshot_dates": 0,
            "errors": [],
        }
        print("  skipped news/announcements prefetch by flag")
    else:
        news = prefetch_news(
            args.ticker,
            news_snapshot_dates,
            args.page_size,
            args.max_pages,
            args.announcement_text_limit,
            workers=args.news_prefetch_workers,
        )
        print(
            f"  eastmoney rows={news['eastmoney_rows']} "
            f"cninfo rows={news['cninfo_rows']} cninfo_text_rows={news['cninfo_text_rows']} "
            f"eastmoney_cached_dates={news['eastmoney_cached_dates']} cninfo_cached_dates={news['cninfo_cached_dates']} "
            f"snapshot_mode={args.news_snapshot_mode} snapshot_dates={len(news_snapshot_dates)} "
            f"workers={args.news_prefetch_workers}"
        )

    print("Step 3/5: prefetching fundamentals...")
    fundamentals = prefetch_fundamentals(args.ticker)
    print(f"  company_info={fundamentals['company_info_ok']} statement_rows={fundamentals['statement_rows']}")

    print("Step 4/5: prefetching social/sentiment summaries...")
    social = prefetch_social(args.ticker, signal_dates)
    print(
        f"  social dates={social['dates']} cached_dates={social['cached_dates']} "
        f"discussion_rows={social['discussion_rows']} event_rows={social['event_rows']}"
    )

    print("Step 5/5: building data quality report...")
    rows = build_preflight_rows(args.ticker, signal_dates, args.lookback_days)
    outputs = write_outputs(
        rows,
        output_dir,
        {
            "ticker": args.ticker,
            "start": args.start,
            "end": args.end,
            "frequency": args.frequency,
            "news_snapshot_mode": args.news_snapshot_mode,
            "news_snapshot_dates": 0 if args.skip_news_prefetch else len(news_snapshot_dates),
            "news_prefetch_workers": args.news_prefetch_workers,
            "skip_news_prefetch": args.skip_news_prefetch,
            "lookback_days": args.lookback_days,
            "market": market,
            "benchmark_market": benchmark_market,
            "news": news,
            "fundamentals": fundamentals,
            "social": {"dates": social["dates"]},
            "social_summary": {
                "cached_dates": social["cached_dates"],
                "discussion_rows": social["discussion_rows"],
                "event_rows": social["event_rows"],
            },
        },
    )

    missing = [row for row in rows if not row["all_core_ok"]]
    print("Agent data preflight complete")
    print(f"output_csv : {outputs['csv']}")
    print(f"output_md  : {outputs['md']}")
    print(f"core_ok    : {len(rows) - len(missing)}/{len(rows)}")
    print("note       : social_discussion_ok counts EastMoney Guba, Xueqiu, and CNInfo IRM; CNInfo announcement events are not true social discussion.")

    if args.fail_on_missing and missing:
        print(f"ERROR: {len(missing)} signal dates have missing core data; LLM run should not start.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
