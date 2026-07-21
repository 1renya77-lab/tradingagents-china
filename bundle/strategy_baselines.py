from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.local_prefetch_cache import load_market_data
from tradingagents.tools.analysis.indicators import boll, kdj, ma, macd, rsi


STRATEGY_LABELS = {
    "buy_hold_100": "B&H",
    "macd": "MACD",
    "kdj_rsi": "KDJ&RSI",
    "zmr": "ZMR",
    "sma": "SMA",
    "agent": "TradingAgents",
}


def format_instrument(ticker: str) -> str:
    raw = str(ticker).strip().upper()
    if raw.startswith(("SH", "SZ")):
        return raw
    if raw.endswith((".SH", ".SZ")):
        return raw[-2:] + raw[:-3]
    if raw.isdigit() and len(raw) == 6:
        return ("SH" if raw.startswith(("5", "6", "9")) else "SZ") + raw
    return raw


def _init_qlib(provider_uri: str) -> None:
    import qlib

    if not qlib.initialized():
        qlib.init(provider_uri=provider_uri, region="cn")


def _load_market_from_qlib(ticker: str, start: str, end: str, provider_uri: str, lookback_days: int) -> pd.DataFrame:
    from qlib.data import D

    _init_qlib(provider_uri)
    instrument = format_instrument(ticker)
    fetch_start = (pd.Timestamp(start) - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    df = D.features(
        [instrument],
        ["$open", "$high", "$low", "$close", "$volume"],
        start_time=fetch_start,
        end_time=end,
        freq="day",
    )
    if df.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df = df.reset_index()
    if "datetime" in df.columns:
        df = df.rename(columns={"datetime": "Date"})
    if "instrument" in df.columns:
        df = df.drop(columns=["instrument"])
    return df.rename(
        columns={
            "$open": "Open",
            "$high": "High",
            "$low": "Low",
            "$close": "Close",
            "$volume": "Volume",
        }
    )


def load_market_history(
    *,
    ticker: str,
    start: str,
    end: str,
    provider_uri: str,
    lookback_days: int = 180,
) -> pd.DataFrame:
    local = load_market_data(ticker)
    fetch_start = pd.Timestamp(start) - pd.Timedelta(days=lookback_days)
    if local is not None and not local.empty:
        local = local.copy()
        local["Date"] = pd.to_datetime(local["Date"])
        local = local[(local["Date"] >= fetch_start) & (local["Date"] <= pd.Timestamp(end))].copy()
        if not local.empty:
            return local.reset_index(drop=True)
    qdf = _load_market_from_qlib(ticker, start, end, provider_uri, lookback_days)
    qdf["Date"] = pd.to_datetime(qdf["Date"])
    qdf = qdf.dropna(subset=["Date", "Open", "High", "Low", "Close"]).sort_values("Date")
    return qdf.reset_index(drop=True)


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_values("Date").reset_index(drop=True)
    close = out["Close"].astype(float)
    high = out["High"].astype(float)
    low = out["Low"].astype(float)
    out["ma20"] = ma(close, 20)
    out["ma60"] = ma(close, 60)
    macd_df = macd(close)
    out["dif"] = macd_df["dif"]
    out["dea"] = macd_df["dea"]
    out["macd_hist"] = macd_df["macd_hist"]
    out["rsi6"] = rsi(close, 6, method="china")
    out["rsi12"] = rsi(close, 12, method="china")
    kdj_df = kdj(high, low, close, n=9, m1=3, m2=3)
    out["kdj_k"] = kdj_df["kdj_k"]
    out["kdj_d"] = kdj_df["kdj_d"]
    out["kdj_j"] = kdj_df["kdj_j"]
    boll_df = boll(close, 20, 2.0)
    out["boll_mid"] = boll_df["boll_mid"]
    out["boll_upper"] = boll_df["boll_upper"]
    out["boll_lower"] = boll_df["boll_lower"]
    out["std20"] = close.rolling(20, min_periods=1).std()
    out["zscore20"] = (close - out["ma20"]) / out["std20"].replace(0, pd.NA)
    return out


def _build_signal_frame_rows(
    *,
    signal_dates: list[pd.Timestamp],
    ticker: str,
    feature_df: pd.DataFrame,
    strategy: str,
) -> list[dict]:
    prev_position = 0.0
    rows: list[dict] = []
    for signal_date in signal_dates:
        hist = feature_df[feature_df["Date"] <= signal_date]
        if hist.empty:
            continue
        row = hist.iloc[-1]
        position = prev_position
        reasoning = ""

        if strategy == "sma":
            if row["Close"] > row["ma20"] and row["ma20"] > row["ma60"]:
                position = 1.0
                reasoning = f"SMA bullish: close>{row['ma20']:.2f}, MA20>{row['ma60']:.2f}"
            elif row["Close"] < row["ma20"] and row["ma20"] < row["ma60"]:
                position = 0.0
                reasoning = f"SMA bearish: close<{row['ma20']:.2f}, MA20<{row['ma60']:.2f}"
            else:
                reasoning = "SMA neutral: keep previous position"
        elif strategy == "macd":
            if row["dif"] > row["dea"] and row["macd_hist"] > 0:
                position = 1.0
                reasoning = f"MACD bullish crossover: DIF={row['dif']:.3f}, DEA={row['dea']:.3f}"
            elif row["dif"] < row["dea"] and row["macd_hist"] < 0:
                position = 0.0
                reasoning = f"MACD bearish crossover: DIF={row['dif']:.3f}, DEA={row['dea']:.3f}"
            else:
                reasoning = "MACD neutral: keep previous position"
        elif strategy == "kdj_rsi":
            if row["kdj_k"] > row["kdj_d"] and row["rsi6"] > 55 and row["rsi12"] > 50:
                position = 1.0
                reasoning = (
                    f"KDJ&RSI bullish: K={row['kdj_k']:.2f}>D={row['kdj_d']:.2f}, "
                    f"RSI6={row['rsi6']:.2f}, RSI12={row['rsi12']:.2f}"
                )
            elif row["kdj_k"] < row["kdj_d"] and row["rsi6"] < 45 and row["rsi12"] < 50:
                position = 0.0
                reasoning = (
                    f"KDJ&RSI bearish: K={row['kdj_k']:.2f}<D={row['kdj_d']:.2f}, "
                    f"RSI6={row['rsi6']:.2f}, RSI12={row['rsi12']:.2f}"
                )
            else:
                reasoning = "KDJ&RSI neutral: keep previous position"
        elif strategy == "zmr":
            z = row["zscore20"]
            if (not pd.isna(z) and z <= -1.0) or row["Close"] <= row["boll_lower"]:
                position = 1.0
                reasoning = f"ZMR long reversion: zscore20={z:.2f}, close near lower band"
            elif (not pd.isna(z) and z >= 1.0) or row["Close"] >= row["boll_upper"]:
                position = 0.0
                reasoning = f"ZMR exit: zscore20={z:.2f}, close near upper band"
            else:
                reasoning = "ZMR neutral: keep previous position"
        else:
            raise ValueError(f"unsupported rule baseline: {strategy}")

        prev_position = float(position)
        action = "持有"
        if position > 0 and prev_position == position:
            action = "买入" if len(rows) == 0 or rows[-1]["target_position"] == 0.0 else "持有"
        if position == 0.0 and rows and rows[-1]["target_position"] > 0.0:
            action = "卖出"
        rows.append(
            {
                "date": signal_date.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "status": "baseline",
                "error_message": "",
                "action": action,
                "target_position": float(position),
                "score": float(position),
                "action_score": float(position),
                "reasoning": f"{strategy}: {reasoning}",
            }
        )
    return rows


def build_rule_baseline_signals(
    *,
    source_signals: Path,
    ticker: str,
    provider_uri: str,
    output_dir: Path,
    strategies: list[str] | None = None,
    lookback_days: int = 180,
) -> dict[str, Path]:
    source_signals = source_signals.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    strategies = strategies or ["macd", "kdj_rsi", "zmr", "sma"]
    base_df = pd.read_csv(source_signals)
    if base_df.empty or "date" not in base_df.columns:
        raise ValueError("source_signals must contain at least one date")
    signal_dates = sorted(pd.to_datetime(base_df["date"]).dropna().unique())
    start = pd.Timestamp(min(signal_dates)).strftime("%Y-%m-%d")
    end = pd.Timestamp(max(signal_dates)).strftime("%Y-%m-%d")
    market_df = load_market_history(
        ticker=ticker,
        start=start,
        end=end,
        provider_uri=provider_uri,
        lookback_days=lookback_days,
    )
    feature_df = _compute_features(market_df)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}
    for strategy in strategies:
        rows = _build_signal_frame_rows(
            signal_dates=[pd.Timestamp(x) for x in signal_dates],
            ticker=ticker,
            feature_df=feature_df,
            strategy=strategy,
        )
        out_df = pd.DataFrame(rows)
        out_path = output_dir / f"signals_{ticker}_{start}_{end}_{strategy}.csv"
        out_df.to_csv(out_path, index=False, encoding="utf-8")
        outputs[strategy] = out_path
    return outputs


def pretty_strategy_name(strategy: str) -> str:
    return STRATEGY_LABELS.get(strategy, strategy)
