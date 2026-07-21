from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import functools
from datetime import datetime

import pandas as pd

from .baostock_provider import get_industryClassification, get_stock_fundamentals, get_stock_info
from .data_quality import data_quality_header


def _require_akshare():
    import akshare as ak

    return ak


AKSHARE_TIMEOUT_SECONDS = 12


def _run_with_timeout(func, *args, timeout: int = AKSHARE_TIMEOUT_SECONDS, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            raise TimeoutError(f"{func.__name__} timed out after {timeout}s") from exc


@functools.lru_cache(maxsize=1)
def _load_a_share_spot_snapshot() -> pd.DataFrame:
    ak = _require_akshare()
    df = _run_with_timeout(ak.stock_zh_a_spot_em)
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["代码"] = out["代码"].astype(str).str.strip()
    out["名称"] = out["名称"].astype(str).str.strip()
    return out


def _resolve_symbol_from_name(name: str) -> str | None:
    query = str(name).strip()
    if not query:
        return None

    spot = _load_a_share_spot_snapshot()
    if spot.empty or "名称" not in spot.columns or "代码" not in spot.columns:
        return None

    exact = spot[spot["名称"] == query]
    if not exact.empty:
        return str(exact.iloc[0]["代码"])

    partial = spot[spot["名称"].str.contains(query, na=False)]
    if len(partial) == 1:
        return str(partial.iloc[0]["代码"])

    return None


def _normalize_symbol(symbol: str) -> str:
    raw = str(symbol).strip().upper()
    if raw.endswith(".SH") or raw.startswith("SH"):
        return raw.replace(".SH", "").replace("SH", "", 1)
    if raw.endswith(".SZ") or raw.startswith("SZ"):
        return raw.replace(".SZ", "").replace("SZ", "", 1)
    if raw.isdigit() and len(raw) == 6:
        return raw
    resolved = _resolve_symbol_from_name(str(symbol).strip())
    if resolved:
        return resolved
    raise ValueError(f"Unsupported A-share symbol: {symbol}")


def _safe_float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if pd.isna(out):
            return None
        return out
    except Exception:
        return None


def _find_date_column(df: pd.DataFrame) -> str | None:
    for col in ["报告日", "REPORT_DATE", "REPORT_DATE_NAME", "公告日期", "发布日期", "日期", "时间"]:
        if col in df.columns:
            return col
    return None


def _filter_by_date(df: pd.DataFrame, curr_date: str, keep_rows: int = 8) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    date_col = _find_date_column(out)
    if date_col is None:
        return out.head(keep_rows)
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    cutoff = pd.to_datetime(curr_date)
    out = out[out[date_col].notna() & (out[date_col] <= cutoff)].sort_values(date_col, ascending=False)
    return out.head(keep_rows)


def _latest_spot_snapshot(symbol: str, curr_date: str) -> dict:
    code = _normalize_symbol(symbol)
    try:
        spot = _load_a_share_spot_snapshot()
        if spot.empty:
            return {}
        row = spot[spot["代码"] == code]
        if row.empty:
            return {}
        item = row.iloc[0]
        return {
            "trade_date": curr_date,
            "name": item.get("名称"),
            "price": _safe_float(item.get("最新价")),
            "change_pct": _safe_float(item.get("涨跌幅")),
            "turnover_rate": _safe_float(item.get("换手率")),
            "volume_ratio": _safe_float(item.get("量比")),
            "pe": _safe_float(item.get("市盈率-动态")),
            "pb": _safe_float(item.get("市净率")),
            "total_mv": _safe_float(item.get("总市值")),
            "circ_mv": _safe_float(item.get("流通市值")),
        }
    except Exception:
        return {}


def _financial_abstract(symbol: str, curr_date: str) -> pd.DataFrame:
    code = _normalize_symbol(symbol)
    ak = _require_akshare()
    df = _run_with_timeout(ak.stock_financial_abstract, symbol=code)
    return _filter_by_date(df, curr_date, keep_rows=6)


def _profit_snapshot_baostock(symbol: str, curr_date: str, max_rows: int = 4) -> pd.DataFrame:
    code = _normalize_symbol(symbol)
    cutoff = pd.to_datetime(curr_date)
    rows = []
    for year in range(cutoff.year, max(cutoff.year - 3, 2006), -1):
        for quarter in (4, 3, 2, 1):
            df = get_stock_fundamentals(code, year, quarter)
            if df is None or df.empty:
                continue
            rows.append(df)
            if len(rows) >= max_rows:
                return pd.concat(rows, ignore_index=True).head(max_rows)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).head(max_rows)


def get_china_fundamentals(symbol: str, curr_date: str | None = None) -> str:
    code = _normalize_symbol(symbol)
    curr_date = curr_date or datetime.now().strftime("%Y-%m-%d")
    stock_info = get_stock_info(code) or {}
    industry = get_industryClassification(code)
    spot = _latest_spot_snapshot(code, curr_date)

    try:
        abstract = _financial_abstract(code, curr_date)
    except Exception:
        abstract = pd.DataFrame()

    bs_profit = _profit_snapshot_baostock(code, curr_date)

    data_rows = (1 if spot else 0) + (0 if abstract is None or abstract.empty else len(abstract)) + (0 if bs_profit.empty else len(bs_profit))
    warnings = []
    if not spot:
        warnings.append("latest spot snapshot unavailable")
    if (abstract is None or abstract.empty) and bs_profit.empty:
        warnings.append("financial snapshot unavailable from AkShare and BaoStock")

    lines = [
        data_quality_header(
            ok=data_rows > 0,
            source="AkShare/BaoStock",
            rows=data_rows,
            cutoff_date=curr_date,
            warning="; ".join(warnings) if warnings else None,
        ),
        "",
        f"# China A-share fundamentals for {code}",
        f"# Cutoff date: {curr_date}",
        f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Name: {spot.get('name') or stock_info.get('code_name') or code}",
        f"Exchange: {'SSE' if code.startswith(('5', '6', '9')) else 'SZSE'}",
        f"Industry: {industry or 'N/A'}",
        f"IPO Date: {stock_info.get('ipoDate') or 'N/A'}",
        f"Status: {stock_info.get('status') or 'N/A'}",
    ]
    if spot:
        lines.extend(
            [
                f"Trade Date: {spot.get('trade_date')}",
                f"Latest Price: {spot.get('price')}",
                f"Change Percent: {spot.get('change_pct')}",
                f"Turnover Rate: {spot.get('turnover_rate')}",
                f"Volume Ratio: {spot.get('volume_ratio')}",
                f"PE: {spot.get('pe')}",
                f"PB: {spot.get('pb')}",
                f"Total Market Cap: {spot.get('total_mv')}",
                f"Circulating Market Cap: {spot.get('circ_mv')}",
            ]
        )
    if abstract is not None and not abstract.empty:
        lines.extend(["", "## financial_abstract", abstract.to_csv(index=False)])
    elif not bs_profit.empty:
        lines.extend(["", "## baostock_profit_snapshot", bs_profit.to_csv(index=False)])
    else:
        lines.extend(["", "Fundamental snapshot unavailable from AkShare and BaoStock. Do not fabricate missing financial values."])
    return "\n".join(lines)


def _statement_csv(symbol: str, curr_date: str, statement: str) -> str:
    code = _normalize_symbol(symbol)
    ak = _require_akshare()
    title_map = {
        "balance_sheet": "Balance Sheet",
        "cashflow": "Cash Flow",
        "income_statement": "Income Statement",
    }
    fetchers = {
        "balance_sheet": ak.stock_balance_sheet_by_report_em,
        "cashflow": ak.stock_cash_flow_sheet_by_report_em,
        "income_statement": ak.stock_profit_sheet_by_report_em,
    }
    try:
        df = _run_with_timeout(fetchers[statement], symbol=code)
        df = _filter_by_date(df, curr_date, keep_rows=8)
        if not df.empty:
            header = [
                data_quality_header(
                    ok=True,
                    source="AkShare",
                    rows=len(df),
                    cutoff_date=curr_date,
                ),
                "",
                f"# {title_map[statement]} data for {code}",
                f"# Cutoff date: {curr_date}",
                f"# Source: AkShare",
                f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]
            return "\n".join(header) + df.to_csv(index=False)
    except Exception:
        pass

    return (
        data_quality_header(
            ok=False,
            source="AkShare/BaoStock",
            rows=0,
            cutoff_date=curr_date,
            warning=f"{title_map[statement]} data unavailable",
        )
        + "\n\n"
        f"{title_map[statement]} data unavailable from AkShare/BaoStock for {code} "
        f"on or before {curr_date}. Do not fabricate statement values."
    )


def get_china_balance_sheet(symbol: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    del freq
    return _statement_csv(symbol, curr_date or datetime.now().strftime("%Y-%m-%d"), "balance_sheet")


def get_china_cashflow(symbol: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    del freq
    return _statement_csv(symbol, curr_date or datetime.now().strftime("%Y-%m-%d"), "cashflow")


def get_china_income_statement(symbol: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    del freq
    return _statement_csv(symbol, curr_date or datetime.now().strftime("%Y-%m-%d"), "income_statement")


def get_china_news(symbol: str, start_date: str, end_date: str) -> str:
    code = _normalize_symbol(symbol)
    try:
        ak = _require_akshare()
        df = _run_with_timeout(ak.stock_news_em, symbol=code)
        if df is not None and not df.empty:
            title_col = "新闻标题" if "新闻标题" in df.columns else ("标题" if "标题" in df.columns else None)
            content_col = "新闻内容" if "新闻内容" in df.columns else ("内容" if "内容" in df.columns else None)
            source_col = "文章来源" if "文章来源" in df.columns else ("来源" if "来源" in df.columns else None)
            link_col = "新闻链接" if "新闻链接" in df.columns else ("链接" if "链接" in df.columns else None)
            time_col = _find_date_column(df)
            if time_col and title_col:
                out = df.copy()
                out[time_col] = pd.to_datetime(out[time_col], errors="coerce")
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1)
                out = out[out[time_col].notna() & (out[time_col] >= start_dt) & (out[time_col] < end_dt)]
                out = out.sort_values(time_col, ascending=False).head(20)
                if not out.empty:
                    sections = [
                        data_quality_header(
                            ok=True,
                            source="AkShare.stock_news_em",
                            rows=len(out),
                            cutoff_date=end_date,
                        ),
                        "",
                        f"## {code} News, from {start_date} to {end_date}:",
                        "",
                    ]
                    for _, row in out.iterrows():
                        sections.append(f"### {row.get(title_col, 'No title')} (source: {row.get(source_col, 'Unknown')})")
                        sections.append(f"Published: {pd.Timestamp(row[time_col]).strftime('%Y-%m-%d %H:%M:%S')}")
                        if content_col and row.get(content_col):
                            sections.append(str(row.get(content_col)))
                        if link_col and row.get(link_col):
                            sections.append(f"Link: {row.get(link_col)}")
                        sections.append("")
                    return "\n".join(sections)
    except Exception:
        pass

    return (
        data_quality_header(
            ok=False,
            source="AkShare.stock_news_em",
            rows=0,
            cutoff_date=end_date,
            warning=f"No news rows found between {start_date} and {end_date}",
        )
        + "\n\n"
        f"No news found for {code} between {start_date} and {end_date}"
    )


def get_china_global_news(curr_date: str, look_back_days: int | None = None, limit: int | None = None) -> str:
    look_back_days = look_back_days or 7
    limit = limit or 10
    start_dt = pd.to_datetime(curr_date) - pd.Timedelta(days=look_back_days)
    try:
        ak = _require_akshare()
        df = _run_with_timeout(ak.news_cctv)
        if df is not None and not df.empty:
            title_col = "title" if "title" in df.columns else ("标题" if "标题" in df.columns else None)
            content_col = "content" if "content" in df.columns else ("内容" if "内容" in df.columns else None)
            time_col = _find_date_column(df)
            if title_col and time_col:
                out = df.copy()
                out[time_col] = pd.to_datetime(out[time_col], errors="coerce")
                cutoff = pd.to_datetime(curr_date) + pd.Timedelta(days=1)
                out = out[out[time_col].notna() & (out[time_col] >= start_dt) & (out[time_col] < cutoff)]
                out = out.sort_values(time_col, ascending=False).head(limit)
                if not out.empty:
                    sections = [
                        data_quality_header(
                            ok=True,
                            source="AkShare.news_cctv",
                            rows=len(out),
                            cutoff_date=curr_date,
                        ),
                        "",
                        f"## China Market News, from {start_dt.strftime('%Y-%m-%d')} to {curr_date}:",
                        "",
                    ]
                    for _, row in out.iterrows():
                        sections.append(f"### {row.get(title_col, 'No title')} (source: CCTV News)")
                        sections.append(f"Published: {pd.Timestamp(row[time_col]).strftime('%Y-%m-%d %H:%M:%S')}")
                        if content_col and row.get(content_col):
                            sections.append(str(row.get(content_col)))
                        sections.append("")
                    return "\n".join(sections)
    except Exception:
        pass

    return (
        data_quality_header(
            ok=False,
            source="AkShare.news_cctv",
            rows=0,
            cutoff_date=curr_date,
            warning=f"No global news rows found since {start_dt.strftime('%Y-%m-%d')}",
        )
        + "\n\n"
        f"No global news found between {start_dt.strftime('%Y-%m-%d')} and {curr_date}"
    )


def get_china_insider_transactions(symbol: str) -> str:
    code = _normalize_symbol(symbol)
    return (
        data_quality_header(
            ok=False,
            source="AkShare/BaoStock",
            rows=0,
            warning="No standardized insider-transactions feed is configured",
        )
        + "\n\n"
        f"No standardized insider-transactions feed is available from AkShare/BaoStock for {code}. "
        "Do not infer insider trading data."
    )
