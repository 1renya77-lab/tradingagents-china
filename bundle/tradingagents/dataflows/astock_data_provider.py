from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .baostock_provider import (
    _run_query,
    format_stock_code,
    get_industryClassification,
    get_stock_info,
)
from .local_prefetch_cache import (
    NEWS_SOURCE_CNINFO,
    NEWS_SOURCE_EASTMONEY,
    load_json_data,
    load_news_items,
)
import baostock as bs


SIGNAL_GENERATION_TIME = "20:00"
DATA_CUTOFF_TIME = "19:30"
NEWS_LOOKBACK_DAYS = 14
CNINFO_BASE_URL = "https://www.cninfo.com.cn"
CNINFO_STATIC_BASE_URL = "https://static.cninfo.com.cn"


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _normalize_symbol(symbol: str) -> str:
    raw = str(symbol).strip().upper()
    if raw.endswith(".SH") or raw.startswith("SH"):
        return raw.replace(".SH", "").replace("SH", "", 1)
    if raw.endswith(".SZ") or raw.startswith("SZ"):
        return raw.replace(".SZ", "").replace("SZ", "", 1)
    if raw.isdigit() and len(raw) == 6:
        return raw
    raise ValueError(f"Unsupported A-share symbol: {symbol}")


def _cutoff_ts(curr_date: str) -> pd.Timestamp:
    return pd.to_datetime(f"{curr_date} {DATA_CUTOFF_TIME}:00")


def _parse_time(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed


def _has_intraday_time(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(re.search(r"\d{1,2}:\d{2}", text))


def _filter_temporal_items(
    items: list[dict[str, Any]],
    curr_date: str,
    time_keys: tuple[str, ...],
    *,
    lookback_days: int | None = None,
) -> list[dict[str, Any]]:
    cutoff = _cutoff_ts(curr_date)
    lower_bound = cutoff - pd.Timedelta(days=int(lookback_days)) if lookback_days is not None else None
    out: list[dict[str, Any]] = []
    for item in items or []:
        parsed = None
        raw_value = None
        for key in time_keys:
            raw_value = item.get(key)
            parsed = _parse_time(raw_value)
            if parsed is not None:
                break
        if parsed is None or parsed > cutoff:
            continue
        if lower_bound is not None and parsed < lower_bound:
            continue
        if not _has_intraday_time(raw_value) and parsed.normalize() == cutoff.normalize():
            # A same-day date without a clock time may have been disclosed
            # after the 19:30 information cutoff, so keep it for the next run.
            continue
        enriched = dict(item)
        enriched["_audit_time"] = parsed.strftime("%Y-%m-%d %H:%M:%S")
        out.append(enriched)
    return out


def _header(ok: bool, source: str, rows: int, cutoff_date: str, warning: str | None = None) -> str:
    lines = [
        f"DATA_QUALITY: ok={str(ok).lower()}",
        "DATA_SOURCE: a-stock-data",
        f"DATA_VENDOR: {source}",
        f"ROWS: {rows}",
        f"CUTOFF_DATE: {cutoff_date} {DATA_CUTOFF_TIME}:00",
        f"SIGNAL_GENERATION_TIME: {cutoff_date} {SIGNAL_GENERATION_TIME}:00",
        "EXECUTION_RULE: signal generated after close on T; rebalance at T+1 open.",
        "TEMPORAL_RULE: only publish_time/disclosure_date <= cutoff_time are used; undated rows and same-day date-only rows are excluded.",
    ]
    if warning:
        lines.append(f"WARNING: {warning}")
    return "\n".join(lines)


BAOSTOCK_FINANCIAL_QUERIES = {
    "profit": bs.query_profit_data,
    "operation": bs.query_operation_data,
    "growth": bs.query_growth_data,
    "balance": bs.query_balance_data,
    "cash_flow": bs.query_cash_flow_data,
    "dupont": bs.query_dupont_data,
}


def fetch_baostock_financial_indicators(
    symbol: str,
    *,
    end_year: int | None = None,
    lookback_years: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch BaoStock financial indicator tables with publication dates."""
    code = format_stock_code(_normalize_symbol(symbol))
    end_year = int(end_year or datetime.now().year)
    start_year = end_year - max(int(lookback_years), 1) + 1
    out: dict[str, list[dict[str, Any]]] = {name: [] for name in BAOSTOCK_FINANCIAL_QUERIES}

    for year in range(end_year, start_year - 1, -1):
        for quarter in (4, 3, 2, 1):
            for name, query_fn in BAOSTOCK_FINANCIAL_QUERIES.items():
                rs = _run_query(query_fn, code=code, year=year, quarter=quarter)
                while rs.next():
                    out[name].append(dict(zip(rs.fields, rs.get_row_data())))
    return out


def filter_baostock_financial_indicators(
    indicators: dict[str, list[dict[str, Any]]] | None,
    curr_date: str,
    *,
    max_rows_per_table: int = 6,
) -> dict[str, list[dict[str, Any]]]:
    """Keep only BaoStock financial rows publicly disclosed before cutoff."""
    cutoff = _cutoff_ts(curr_date)
    filtered: dict[str, list[dict[str, Any]]] = {}
    for name, rows in (indicators or {}).items():
        kept: list[dict[str, Any]] = []
        for row in rows or []:
            parsed = _parse_time(row.get("pubDate"))
            if parsed is None:
                continue
            # BaoStock pubDate is a date-only disclosure date. Treat it as
            # public by the signal cutoff date only after that calendar date
            # has arrived.
            if parsed.normalize() > cutoff.normalize():
                continue
            kept.append(dict(row))
        kept.sort(
            key=lambda item: (
                str(item.get("pubDate", "")),
                str(item.get("statDate", "")),
            ),
            reverse=True,
        )
        filtered[name] = kept[:max_rows_per_table]
    return filtered


def count_baostock_financial_rows(
    indicators: dict[str, list[dict[str, Any]]] | None,
    curr_date: str,
) -> int:
    filtered = filter_baostock_financial_indicators(indicators, curr_date)
    return sum(len(rows) for rows in filtered.values())


def eastmoney_stock_info(symbol: str) -> dict[str, Any]:
    code = _normalize_symbol(symbol)
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
        "secid": f"{market_code}.{code}",
    }
    response = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=10)
    response.raise_for_status()
    data = response.json().get("data") or {}
    return {
        "code": data.get("f57", code),
        "name": data.get("f58", ""),
        "industry": data.get("f127", ""),
        "total_shares": data.get("f84", ""),
        "float_shares": data.get("f85", ""),
        "mcap": data.get("f116", ""),
        "float_mcap": data.get("f117", ""),
        "list_date": str(data.get("f189", "")),
        "price": data.get("f43", ""),
    }


def eastmoney_stock_news(
    symbol: str,
    page_size: int = 20,
    cutoff_date: str | None = None,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    code = _normalize_symbol(symbol)
    callback = "jQuery_news"
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    cutoff = _cutoff_ts(cutoff_date) if cutoff_date else None
    rows: list[dict[str, Any]] = []

    for page_index in range(1, max_pages + 1):
        inner_params = json.dumps(
            {
                "uid": "",
                "keyword": code,
                "type": ["cmsArticleWebOld"],
                "client": "web",
                "clientType": "web",
                "clientVersion": "curr",
                "param": {
                    "cmsArticleWebOld": {
                        "searchScope": "default",
                        "sort": "default",
                        "pageIndex": page_index,
                        "pageSize": page_size,
                        "preTag": "",
                        "postTag": "",
                    }
                },
            },
            separators=(",", ":"),
        )
        response = requests.get(
            url,
            params={"cb": callback, "param": inner_params},
            headers={"User-Agent": UA, "Referer": "https://so.eastmoney.com/"},
            timeout=15,
        )
        response.raise_for_status()
        text = response.text
        json_text = text[text.index("(") + 1 : text.rindex(")")]
        data = json.loads(json_text)
        articles = data.get("result", {}).get("cmsArticleWebOld", []) or []
        if not articles:
            break

        page_rows: list[dict[str, Any]] = []
        page_has_cutoff_hit = False
        for article in articles:
            item = {
                "title": re.sub(r"<[^>]+>", "", article.get("title", "")),
                "content": re.sub(r"<[^>]+>", "", article.get("content", ""))[:300],
                "time": article.get("date", ""),
                "source": article.get("mediaName", ""),
                "url": article.get("url", ""),
            }
            page_rows.append(item)
            if cutoff is not None:
                parsed = _parse_time(item.get("time"))
                if parsed is not None and parsed <= cutoff:
                    page_has_cutoff_hit = True
        rows.extend(page_rows)
        if cutoff is None:
            break
        if page_has_cutoff_hit:
            # We only need enough backfill to include the first page that reaches the cutoff.
            break

    return rows


_CNINFO_ORGID_MAP: dict[str, str] = {}
_CNINFO_STOCK_PROFILE_MAP: dict[str, dict[str, Any]] = {}


def _cninfo_orgid(symbol: str) -> str:
    code = _normalize_symbol(symbol)
    _load_cninfo_stock_map()
    org = _CNINFO_ORGID_MAP.get(code)
    if org:
        return org
    if code.startswith("6"):
        return f"gssh0{code}"
    if code.startswith(("8", "4")):
        return f"gsbj0{code}"
    return f"gssz0{code}"


def _load_cninfo_stock_map() -> None:
    global _CNINFO_ORGID_MAP, _CNINFO_STOCK_PROFILE_MAP
    if _CNINFO_ORGID_MAP and _CNINFO_STOCK_PROFILE_MAP:
        return
    response = requests.get(
        "http://www.cninfo.com.cn/new/data/szse_stock.json",
        headers={"User-Agent": UA},
        timeout=15,
    )
    response.raise_for_status()
    stock_list = response.json().get("stockList", [])
    _CNINFO_ORGID_MAP = {item["code"]: item["orgId"] for item in stock_list}
    _CNINFO_STOCK_PROFILE_MAP = {
        item["code"]: {
            "code": item.get("code", ""),
            "name": item.get("zwjc", ""),
            "org_id": item.get("orgId", ""),
            "exchange": "SZSE",
            "category": item.get("category", ""),
            "pinyin": item.get("pinyin", ""),
        }
        for item in stock_list
    }


def cninfo_stock_profile(symbol: str) -> dict[str, Any]:
    code = _normalize_symbol(symbol)
    _load_cninfo_stock_map()
    return dict(_CNINFO_STOCK_PROFILE_MAP.get(code, {}))


def baostock_stock_profile(symbol: str) -> dict[str, Any]:
    code = _normalize_symbol(symbol)
    info = get_stock_info(code) or {}
    industry = get_industryClassification(code)
    if not info and not industry:
        return {}
    return {
        "code": code,
        "name": info.get("code_name", ""),
        "industry": industry or "",
        "list_date": info.get("ipoDate", ""),
        "status": info.get("status", ""),
        "type": info.get("type", ""),
        "source": "baostock",
    }


def fallback_company_profile(symbol: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    try:
        profile = baostock_stock_profile(symbol)
        if profile:
            return profile, warnings
    except Exception as exc:
        warnings.append(f"BaoStock company profile unavailable: {exc}")

    try:
        profile = cninfo_stock_profile(symbol)
        if profile:
            return profile, warnings
    except Exception as exc:
        warnings.append(f"CNInfo stock profile unavailable: {exc}")

    return {}, warnings


def _cninfo_ts_to_datetime(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d %H:%M:%S")
    return str(value) if value else ""


def cninfo_irm(
    symbol: str,
    page_size: int = 30,
    cutoff_date: str | None = None,
    max_pages: int = 3,
) -> list[dict[str, Any]]:
    """Fetch CNInfo IRM investor Q&A rows with cutoff-safe filtering."""
    code = _normalize_symbol(symbol)
    rows: list[dict[str, Any]] = []

    lookup = requests.post(
        "https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo",
        data={"keyWord": code},
        headers={"User-Agent": UA, "Referer": "https://irm.cninfo.com.cn/"},
        timeout=10,
    )
    lookup.raise_for_status()
    candidates = lookup.json().get("data") or []
    if not candidates:
        return []
    org_id = candidates[0].get("secid") or candidates[0].get("orgId") or _cninfo_orgid(code)

    for page_num in range(1, max(1, int(max_pages)) + 1):
        response = requests.post(
            "https://irm.cninfo.com.cn/newircs/company/question",
            params={
                "_t": 1,
                "stockcode": code,
                "orgId": org_id,
                "pageSize": int(page_size),
                "pageNum": page_num,
                "keyWord": "",
                "startDay": "",
                "endDay": "",
            },
            headers={"User-Agent": UA, "Referer": "https://irm.cninfo.com.cn/"},
            timeout=15,
        )
        response.raise_for_status()
        page_rows = response.json().get("rows") or []
        if not page_rows:
            break
        for item in page_rows:
            question_time = _cninfo_ts_to_datetime(
                item.get("pubDate") or item.get("questionTime") or item.get("createTime")
            )
            answer_time = _cninfo_ts_to_datetime(
                item.get("attachedPubDate") or item.get("answerTime") or item.get("replyTime")
            )
            rows.append(
                {
                    "code": item.get("stockCode") or code,
                    "company": item.get("companyShortName") or item.get("companyName") or "",
                    "question": item.get("mainContent") or item.get("questionContent") or "",
                    "answer": item.get("attachedContent") or item.get("answerContent") or "",
                    "answerer": item.get("attachedAuthor") or item.get("answerer") or "",
                    "question_time": question_time,
                    "answer_time": answer_time,
                    "source": "CNInfo IRM",
                    "url": f"https://irm.cninfo.com.cn/newircs/index/search?keyWord={code}",
                }
            )
    if cutoff_date:
        rows = _filter_temporal_items(
            rows,
            cutoff_date,
            ("answer_time", "question_time"),
            lookback_days=NEWS_LOOKBACK_DAYS,
        )
    return rows


def cninfo_download_url(adjunct_url: str | None) -> str:
    if not adjunct_url:
        return ""
    return f"{CNINFO_STATIC_BASE_URL}/{str(adjunct_url).lstrip('/')}"


def cninfo_announcements(
    symbol: str,
    page_size: int = 30,
    cutoff_date: str | None = None,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    code = _normalize_symbol(symbol)
    org_id = _cninfo_orgid(code)
    rows: list[dict[str, Any]] = []
    cutoff = _cutoff_ts(cutoff_date) if cutoff_date else None

    for page_num in range(1, max_pages + 1):
        response = requests.post(
            "https://www.cninfo.com.cn/new/hisAnnouncement/query",
            data={
                "stock": f"{code},{org_id}",
                "tabName": "fulltext",
                "pageSize": str(page_size),
                "pageNum": str(page_num),
                "column": "",
                "category": "",
                "plate": "",
                "seDate": "",
                "searchkey": "",
                "secid": "",
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            },
            headers={
                "User-Agent": UA,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://www.cninfo.com.cn/new/disclosure",
                "Origin": "https://www.cninfo.com.cn",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        announcements = data.get("announcements", []) or []
        if not announcements:
            break

        page_has_cutoff_hit = False
        for item in announcements:
            row = {
                "title": item.get("announcementTitle", ""),
                "type": item.get("announcementTypeName", ""),
                "date": _cninfo_ts_to_datetime(item.get("announcementTime")),
                "url": "https://www.cninfo.com.cn/new/disclosure/detail?annoId="
                f"{item.get('announcementId', '')}",
                "announcement_id": str(item.get("announcementId", "")),
                "adjunct_url": item.get("adjunctUrl", ""),
                "download_url": cninfo_download_url(item.get("adjunctUrl")),
                "adjunct_type": item.get("adjunctType", ""),
                "adjunct_size_kb": item.get("adjunctSize", ""),
            }
            rows.append(row)
            if cutoff is not None:
                parsed = _parse_time(row.get("date"))
                if parsed is not None and parsed <= cutoff:
                    page_has_cutoff_hit = True
        if cutoff is None:
            break
        if page_has_cutoff_hit:
            break
    return rows


def extract_cninfo_announcement_text(item: dict[str, Any], max_chars: int = 4000) -> str:
    """Download a CNInfo PDF announcement and extract text with local pdftotext."""
    download_url = item.get("download_url") or cninfo_download_url(item.get("adjunct_url"))
    if not download_url:
        return ""
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise RuntimeError("pdftotext command is not installed")

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "announcement.pdf"
        txt_path = Path(tmpdir) / "announcement.txt"
        response = requests.get(
            download_url,
            headers={"User-Agent": UA, "Referer": "https://www.cninfo.com.cn/new/disclosure"},
            timeout=20,
        )
        response.raise_for_status()
        pdf_path.write_bytes(response.content)
        subprocess.run(
            [pdftotext, "-layout", str(pdf_path), str(txt_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        text = txt_path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars]


def enrich_cninfo_announcement_texts(
    announcements: list[dict[str, Any]],
    *,
    max_items: int = 10,
    max_chars: int = 4000,
) -> list[dict[str, Any]]:
    enriched_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    extracted = 0
    candidates = sorted(
        [dict(item) for item in announcements or []],
        key=lambda row: _parse_time(row.get("date")) or pd.Timestamp.max,
    )
    for row in candidates:
        key = (str(row.get("title", "")), str(row.get("date", "")))
        has_download = bool(row.get("download_url") or row.get("adjunct_url"))
        if extracted < max_items and has_download:
            try:
                text = extract_cninfo_announcement_text(row, max_chars=max_chars)
                row["text_excerpt"] = text
                row["text_status"] = "ok" if text else "empty"
            except Exception as exc:
                row["text_excerpt"] = ""
                row["text_status"] = f"error: {exc}"
            extracted += 1
        enriched_by_key[key] = row

    for item in announcements or []:
        row = dict(item)
        key = (str(row.get("title", "")), str(row.get("date", "")))
        if key not in enriched_by_key:
            enriched_by_key[key] = row
    return list(enriched_by_key.values())


def sina_financial_report(symbol: str, report_type: str = "lrb", num: int = 8) -> list[dict[str, Any]]:
    code = _normalize_symbol(symbol)
    prefix = "sh" if code.startswith("6") else "sz"
    response = requests.get(
        "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022",
        params={
            "paperCode": f"{prefix}{code}",
            "source": report_type,
            "type": "0",
            "page": "1",
            "num": str(num),
        },
        headers={"User-Agent": UA},
        timeout=15,
    )
    response.raise_for_status()
    report_list = response.json().get("result", {}).get("data", {}).get("report_list", {}) or {}
    rows: list[dict[str, Any]] = []
    for period in sorted(report_list.keys(), reverse=True)[:num]:
        item = report_list[period]
        rec: dict[str, Any] = {"报告期": f"{period[:4]}-{period[4:6]}-{period[6:8]}"}
        for row in item.get("data", []) or []:
            title = row.get("item_title", "")
            if not title or row.get("item_value") is None:
                continue
            rec[title] = row.get("item_value")
            yoy = row.get("item_tongbi")
            if yoy not in (None, ""):
                rec[f"{title}_同比"] = yoy
        rows.append(rec)
    return rows


def _infer_statement_period_from_title(title: str) -> str | None:
    match = re.search(r"(20\d{2})", str(title or ""))
    if not match:
        return None
    year = match.group(1)
    if any(key in title for key in ("第一季度", "一季度", "1季度", "一季报")):
        return f"{year}-03-31"
    if any(key in title for key in ("半年度", "半年报", "中期报告")):
        return f"{year}-06-30"
    if any(key in title for key in ("第三季度", "三季度", "3季度", "三季报")):
        return f"{year}-09-30"
    if any(key in title for key in ("年度报告", "年报")):
        return f"{year}-12-31"
    return None


def _audited_statement_periods(notices: list[dict[str, Any]]) -> set[str]:
    periods: set[str] = set()
    for notice in notices or []:
        period = _infer_statement_period_from_title(str(notice.get("title", "")))
        if period:
            periods.add(period)
    return periods


def _filter_statement_periods(
    rows: list[dict[str, Any]],
    curr_date: str,
    audited_periods: set[str],
) -> list[dict[str, Any]]:
    cutoff = pd.to_datetime(curr_date)
    out = []
    for row in rows or []:
        period = _parse_time(row.get("报告期"))
        if period is None or period > cutoff:
            continue
        period_str = period.strftime("%Y-%m-%d")
        if period_str not in audited_periods:
            continue
        out.append(row)
    return out


def format_astock_news_report(
    symbol: str,
    curr_date: str,
    news_items: list[dict[str, Any]],
    announcements: list[dict[str, Any]],
    warnings: list[str] | None = None,
    lookback_days: int = NEWS_LOOKBACK_DAYS,
) -> str:
    code = _normalize_symbol(symbol)
    news = _filter_temporal_items(news_items, curr_date, ("time", "publish_time", "date"), lookback_days=lookback_days)
    notices = _filter_temporal_items(announcements, curr_date, ("date", "publish_time"), lookback_days=lookback_days)
    rows = len(news) + len(notices)
    warning_parts = list(warnings or [])
    warning_parts.append(f"news_agent_recent_window_days={lookback_days}")
    lines = [
        _header(
            ok=rows > 0,
            source="EastMoney stock news + CNInfo announcements",
            rows=rows,
            cutoff_date=curr_date,
            warning="; ".join(warning_parts)
            if warning_parts
            else (None if rows else "No audited recent news or announcements before cutoff"),
        ),
        "",
        f"# {code} A-share audited news and announcements",
        "",
        "## Stock News",
    ]
    if news:
        for item in news[:10]:
            lines.extend(
                [
                    f"### {item.get('title', 'No title')}",
                    f"- Published: {item.get('_audit_time')}",
                    f"- Source: {item.get('source', 'Unknown')}",
                    f"- URL: {item.get('url', '')}",
                    str(item.get("content", "")).strip(),
                    "",
                ]
            )
    else:
        lines.append(f"No audited stock news in the recent {lookback_days}-day window before cutoff.")

    lines.extend(["", "## Company Announcements"])
    if notices:
        for item in notices[:10]:
            lines.extend(
                [
                    f"### {item.get('title', 'No title')}",
                    f"- Disclosure Date: {item.get('_audit_time')[:10]}",
                    f"- Type: {item.get('type', '')}",
                    f"- URL: {item.get('url', '')}",
                    f"- Download URL: {item.get('download_url', '')}",
                    f"- Text Status: {item.get('text_status', '')}",
                    (
                        "Excerpt:\n"
                        + str(item.get("text_excerpt", "")).strip()[:1200]
                        if str(item.get("text_excerpt", "")).strip()
                        else ""
                    ),
                    "",
                ]
            )
    else:
        lines.append(f"No audited company announcements in the recent {lookback_days}-day window before cutoff.")
    return "\n".join(lines)


def format_astock_fundamentals_report(
    symbol: str,
    curr_date: str,
    company_info: dict[str, Any],
    statements: dict[str, list[dict[str, Any]]],
    announcements: list[dict[str, Any]],
    baostock_financials: dict[str, list[dict[str, Any]]] | None = None,
    warnings: list[str] | None = None,
) -> str:
    code = _normalize_symbol(symbol)

    def _has_meaningful_company_info(info: dict[str, Any]) -> bool:
        if not info:
            return False
        value_keys = ("price", "mcap", "float_mcap", "total_shares", "float_shares", "pe", "pb")
        return any(str(info.get(key, "")).strip() not in {"", "None", "nan"} for key in value_keys)

    notices = _filter_temporal_items(announcements, curr_date, ("date", "publish_time"))
    audited_periods = _audited_statement_periods(notices)
    filtered_statements = {
        name: _filter_statement_periods(rows, curr_date, audited_periods)
        for name, rows in (statements or {}).items()
    }
    statement_rows = sum(len(rows) for rows in filtered_statements.values())
    filtered_baostock_financials = filter_baostock_financial_indicators(baostock_financials, curr_date)
    baostock_financial_rows = sum(len(rows) for rows in filtered_baostock_financials.values())
    company_rows = 1 if _has_meaningful_company_info(company_info) else 0
    core_rows = company_rows + statement_rows + baostock_financial_rows
    lines = [
        _header(
            ok=core_rows > 0,
            source="BaoStock financial indicators + EastMoney stock info + Sina statements + CNInfo announcements",
            rows=core_rows,
            cutoff_date=curr_date,
            warning="; ".join(
                (warnings or [])
                + [
                    f"CNInfo announcements are supplementary evidence only; announcement_rows={len(notices)}.",
                    "Sina statements expose report_period_only, not disclosure_date; "
                    "use audited announcements to verify actual disclosure timing."
                ]
            ),
        ),
        "",
        f"# {code} A-share fundamentals enriched by a-stock-data",
        "",
        "## Company Profile",
    ]
    if company_info:
        base_keys = ["name", "industry", "price", "mcap", "float_mcap", "total_shares", "float_shares", "list_date"]
        extra_keys = [key for key in ["org_id", "exchange", "category", "source", "status", "type"] if key in company_info]
        for key in base_keys + extra_keys:
            lines.append(f"- {key}: {company_info.get(key, '')}")
    else:
        lines.append("Company profile unavailable from EastMoney stock info.")

    lines.extend(["", "## Audited Announcements"])
    if notices:
        for item in notices[:10]:
            lines.append(
                f"- {item.get('_audit_time')[:10]} | {item.get('type', '')} | {item.get('title', '')}"
            )
            excerpt = str(item.get("text_excerpt", "")).strip()
            if excerpt:
                lines.append(f"  摘录: {excerpt[:500]}")
    else:
        lines.append("No audited announcements on or before cutoff.")

    lines.extend(["", "## Financial Statements"])
    for name, rows_for_statement in filtered_statements.items():
        lines.append(f"### {name} (report_period_only)")
        if rows_for_statement:
            lines.append(pd.DataFrame(rows_for_statement).head(6).to_csv(index=False))
        else:
            lines.append("No statement rows with report period on or before cutoff.")

    lines.extend(["", "## BaoStock Financial Indicators"])
    if baostock_financial_rows:
        for name, rows_for_indicator in filtered_baostock_financials.items():
            lines.append(f"### {name} (pubDate audited)")
            if rows_for_indicator:
                lines.append(pd.DataFrame(rows_for_indicator).head(6).to_csv(index=False))
            else:
                lines.append("No BaoStock rows disclosed on or before cutoff.")
    else:
        lines.append("No BaoStock financial indicator rows disclosed on or before cutoff.")
    return "\n".join(lines)


def get_astock_news_report(symbol: str, curr_date: str, max_items: int = 20) -> str:
    code = _normalize_symbol(symbol)
    warnings: list[str] = []
    news: list[dict[str, Any]] = []
    announcements: list[dict[str, Any]] = []
    cached_news = load_news_items(code, NEWS_SOURCE_EASTMONEY, snapshot_date=curr_date)
    cached_announcements = load_news_items(code, NEWS_SOURCE_CNINFO, snapshot_date=curr_date)

    if cached_news is not None:
        news = cached_news
        warnings.append(f"EastMoney stock news loaded from signal-date snapshot cache: {curr_date}")
    else:
        warnings.append(f"EastMoney stock news signal-date snapshot cache missing: {curr_date}")

    if cached_announcements is not None:
        announcements = cached_announcements
        warnings.append(f"CNInfo announcements loaded from signal-date snapshot cache: {curr_date}")
    else:
        warnings.append(f"CNInfo announcements signal-date snapshot cache missing: {curr_date}")
    return format_astock_news_report(code, curr_date, news, announcements, warnings=warnings)


def get_astock_fundamentals_report(symbol: str, curr_date: str) -> str:
    code = _normalize_symbol(symbol)
    warnings: list[str] = []
    company_info: dict[str, Any] = {}
    announcements: list[dict[str, Any]] = []
    statements: dict[str, list[dict[str, Any]]] = {
        "income_statement": [],
        "balance_sheet": [],
        "cashflow": [],
    }
    baostock_financials: dict[str, list[dict[str, Any]]] = {}
    cached_company = load_json_data(code, "fundamentals", "eastmoney_company_info")
    cached_statements = load_json_data(code, "fundamentals", "sina_statements")
    cached_baostock_financials = load_json_data(code, "fundamentals", "baostock_financial_indicators")
    cached_announcements = load_news_items(code, NEWS_SOURCE_CNINFO, snapshot_date=curr_date)
    if cached_announcements is None:
        cached_announcements = load_news_items(code, NEWS_SOURCE_CNINFO)

    if isinstance(cached_company, dict):
        company_info = cached_company
        warnings.append("EastMoney company profile loaded from local prefetch cache")
    else:
        try:
            company_info = eastmoney_stock_info(code)
        except Exception as exc:
            warnings.append(f"EastMoney company profile unavailable: {exc}")
            fallback_info, fallback_warnings = fallback_company_profile(code)
            if fallback_info:
                company_info = fallback_info
            warnings.extend(fallback_warnings)

    if cached_announcements is not None:
        announcements = cached_announcements
        warnings.append("CNInfo announcements loaded from local prefetch cache")
    else:
        try:
            announcements = cninfo_announcements(code, page_size=20, cutoff_date=curr_date)
        except Exception as exc:
            warnings.append(f"CNInfo announcements unavailable: {exc}")

    if isinstance(cached_baostock_financials, dict):
        baostock_financials = {
            name: rows if isinstance(rows, list) else []
            for name, rows in cached_baostock_financials.items()
        }
        warnings.append("BaoStock financial indicators loaded from local prefetch cache")
    else:
        try:
            baostock_financials = fetch_baostock_financial_indicators(
                code,
                end_year=pd.to_datetime(curr_date).year,
            )
        except Exception as exc:
            warnings.append(f"BaoStock financial indicators unavailable: {exc}")

    if isinstance(cached_statements, dict):
        for name in statements:
            value = cached_statements.get(name)
            if isinstance(value, list):
                statements[name] = value
        warnings.append("Sina financial statements loaded from local prefetch cache")
        return format_astock_fundamentals_report(
            code,
            curr_date,
            company_info,
            statements,
            announcements,
            baostock_financials=baostock_financials,
            warnings=warnings,
        )

    for name, report_type in [
        ("income_statement", "lrb"),
        ("balance_sheet", "fzb"),
        ("cashflow", "llb"),
    ]:
        try:
            statements[name] = sina_financial_report(code, report_type)
        except Exception as exc:
            warnings.append(f"Sina {name} unavailable: {exc}")
    return format_astock_fundamentals_report(
        code,
        curr_date,
        company_info,
        statements,
        announcements,
        baostock_financials=baostock_financials,
        warnings=warnings,
    )
