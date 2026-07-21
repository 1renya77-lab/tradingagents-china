"""
Backtest an existing TradingAgents signal CSV with Qlib.

The script is intentionally independent from the older local backtest scripts.
It reads a CSV like:

    date,ticker,action,confidence,risk_score,target_price,action_score,score,reasoning

and executes a single-stock long/cash strategy:

    If target_position exists:
        rebalance toward that target long exposure.

    Otherwise:
        score >= buy_threshold  -> scale into a long position by score strength
        score <= sell_threshold -> go to cash
        otherwise               -> keep current position

Signals are shifted by one trading step inside the Qlib strategy: a signal
observed on date T is used to trade during the next Qlib execution step. This
keeps the backtest from buying at the same close that produced the signal.
"""

from __future__ import annotations

import argparse
import math
import pickle
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import qlib
from qlib.backtest.decision import Order, OrderDir, TradeDecisionWO
from qlib.contrib.evaluate import backtest_daily
from qlib.contrib.strategy.signal_strategy import BaseSignalStrategy
from qlib.data import D


DEFAULT_PROVIDER_URI = "~/.qlib/qlib_data/cn_data"
DEFAULT_RESULT_DIR = Path("outputs/backtests/qlib")


class SingleStockSignalStrategy(BaseSignalStrategy):
    """A single-stock long/cash strategy driven by sparse TradingAgents scores."""

    def __init__(
        self,
        *,
        signal,
        buy_threshold: float = 0.7,
        sell_threshold: float = 0.3,
        target_position: float = 0.95,
        min_trade_value: float = 100.0,
        debug_decisions: bool = False,
        signal_is_target_position: bool = False,
        **kwargs,
    ):
        super().__init__(signal=signal, **kwargs)
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.target_position = target_position
        self.min_trade_value = min_trade_value
        self.debug_decisions = debug_decisions
        self.signal_is_target_position = signal_is_target_position

    def _target_exposure_from_score(self, score: float) -> float:
        """Convert a long-only score into target exposure."""
        if score < self.buy_threshold:
            return 0.0
        raw_exposure = (score - 0.5) * 2.0
        return float(np.clip(raw_exposure, 0.0, self.target_position))

    def generate_trade_decision(self, execute_result=None):
        trade_step = self.trade_calendar.get_trade_step()
        trade_start_time, trade_end_time = self.trade_calendar.get_step_time(trade_step)

        # Use the previous step's signal for today's trade to avoid same-close leakage.
        pred_start_time, pred_end_time = self.trade_calendar.get_step_time(trade_step, shift=1)
        pred_score = self.signal.get_signal(start_time=pred_start_time, end_time=pred_end_time)

        if pred_score is None or len(pred_score) == 0:
            if self.debug_decisions:
                print(f"[decision] {trade_start_time.date()} no signal in {pred_start_time.date()}->{pred_end_time.date()}")
            return TradeDecisionWO([], self)

        if isinstance(pred_score, pd.DataFrame):
            pred_score = pred_score.iloc[:, 0]

        pred_score = pred_score.dropna()
        if len(pred_score) == 0:
            return TradeDecisionWO([], self)

        stock_id = pred_score.index[0][0] if isinstance(pred_score.index, pd.MultiIndex) else pred_score.index[0]
        score = float(pred_score.iloc[0])
        if math.isnan(score):
            return TradeDecisionWO([], self)

        if not self.trade_exchange.is_stock_tradable(
            stock_id=stock_id,
            start_time=trade_start_time,
            end_time=trade_end_time,
        ):
            if self.debug_decisions:
                print(f"[decision] {trade_start_time.date()} {stock_id} score={score} not tradable")
            return TradeDecisionWO([], self)

        position = self.trade_position
        current_amount = position.get_stock_amount(stock_id) if stock_id in position.get_stock_list() else 0.0
        cash = position.get_cash()
        account_value = position.calculate_value()

        deal_price = self.trade_exchange.get_deal_price(
            stock_id=stock_id,
            start_time=trade_start_time,
            end_time=trade_end_time,
            direction=OrderDir.BUY if score >= self.buy_threshold else OrderDir.SELL,
        )
        if deal_price is None or deal_price <= 0:
            if self.debug_decisions:
                print(f"[decision] {trade_start_time.date()} {stock_id} score={score} invalid price={deal_price}")
            return TradeDecisionWO([], self)

        factor = self.trade_exchange.get_factor(
            stock_id=stock_id,
            start_time=trade_start_time,
            end_time=trade_end_time,
        )

        orders = []
        if self.signal_is_target_position:
            target_exposure = float(np.clip(score, 0.0, self.target_position))
            target_value = account_value * target_exposure
            current_value = current_amount * deal_price
            trade_value = target_value - current_value
            if abs(trade_value) >= self.min_trade_value:
                direction = OrderDir.BUY if trade_value > 0 else OrderDir.SELL
                if direction == OrderDir.BUY:
                    trade_value = min(cash, trade_value)
                amount = abs(trade_value) / deal_price
                amount = self.trade_exchange.round_amount_by_trade_unit(amount, factor)
                if amount > 0:
                    order = Order(
                        stock_id=stock_id,
                        amount=amount,
                        direction=direction,
                        start_time=trade_start_time,
                        end_time=trade_end_time,
                    )
                    if self.trade_exchange.check_order(order):
                        orders.append(order)
                    elif self.debug_decisions:
                        side = "BUY" if direction == OrderDir.BUY else "SELL"
                        print(f"[decision] {trade_start_time.date()} {side} rejected amount={amount} price={deal_price}")

        elif score >= self.buy_threshold:
            target_exposure = self._target_exposure_from_score(score)
            target_value = account_value * target_exposure
            current_value = current_amount * deal_price
            buy_value = min(cash, max(0.0, target_value - current_value))
            if buy_value >= self.min_trade_value:
                buy_amount = buy_value / deal_price
                buy_amount = self.trade_exchange.round_amount_by_trade_unit(buy_amount, factor)
                if buy_amount > 0:
                    order = Order(
                        stock_id=stock_id,
                        amount=buy_amount,
                        direction=OrderDir.BUY,
                        start_time=trade_start_time,
                        end_time=trade_end_time,
                    )
                    if self.trade_exchange.check_order(order):
                        orders.append(order)
                    elif self.debug_decisions:
                        print(f"[decision] {trade_start_time.date()} BUY rejected amount={buy_amount} price={deal_price}")

        elif score <= self.sell_threshold and current_amount > 0:
            order = Order(
                stock_id=stock_id,
                amount=current_amount,
                direction=OrderDir.SELL,
                start_time=trade_start_time,
                end_time=trade_end_time,
            )
            if self.trade_exchange.check_order(order):
                orders.append(order)
            elif self.debug_decisions:
                print(f"[decision] {trade_start_time.date()} SELL rejected amount={current_amount} price={deal_price}")

        if self.debug_decisions and (self.signal_is_target_position or score >= self.buy_threshold or score <= self.sell_threshold):
            target_exposure = float(np.clip(score, 0.0, self.target_position)) if self.signal_is_target_position else self._target_exposure_from_score(score)
            print(
                "[decision] "
                f"{trade_start_time.date()} {stock_id} score={score} price={deal_price} "
                f"cash={cash:.2f} current_amount={current_amount:.2f} "
                f"target_exposure={target_exposure:.2f} orders={len(orders)}"
            )

        return TradeDecisionWO(orders, self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use Qlib to backtest an existing TradingAgents signal CSV."
    )
    parser.add_argument("--signals", required=True, help="Path to signals_*.csv")
    parser.add_argument("--ticker", default=None, help="Stock code, e.g. 000001. Inferred from filename if omitted.")
    parser.add_argument("--start", default=None, help="Backtest start date. Inferred from signal dates if omitted.")
    parser.add_argument("--end", default=None, help="Backtest end date. Inferred from signal dates if omitted.")
    parser.add_argument("--provider-uri", default=DEFAULT_PROVIDER_URI, help="Qlib provider_uri")
    parser.add_argument("--output-dir", default=str(DEFAULT_RESULT_DIR), help="Directory for output CSV files")
    parser.add_argument("--init-cash", type=float, default=100000.0, help="Initial cash")
    parser.add_argument("--buy-threshold", type=float, default=0.7, help="Buy when score >= this value")
    parser.add_argument("--sell-threshold", type=float, default=0.3, help="Sell when score <= this value")
    parser.add_argument("--target-position", type=float, default=0.95, help="Target long exposure after a buy")
    parser.add_argument("--benchmark", default=None, help="Qlib benchmark, e.g. SH000300. None disables benchmark.")
    parser.add_argument("--deal-price", default="close", choices=["open", "close"], help="Execution price field")
    parser.add_argument("--open-cost", type=float, default=0.0005, help="Buy-side transaction cost")
    parser.add_argument("--close-cost", type=float, default=0.0015, help="Sell-side transaction cost")
    parser.add_argument("--min-cost", type=float, default=5.0, help="Minimum transaction cost")
    parser.add_argument("--debug-decisions", action="store_true", help="Print strategy decision diagnostics")
    return parser.parse_args()


def infer_from_filename(path: Path) -> tuple[Optional[str], Optional[str], Optional[str]]:
    match = re.search(r"signals_([^_]+)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$", path.name)
    if not match:
        return None, None, None
    return match.group(1), match.group(2), match.group(3)


def format_instrument(ticker: str) -> str:
    ticker = ticker.upper().strip()
    if ticker.startswith(("SH", "SZ")):
        return ticker
    if len(ticker) == 6 and ticker.isdigit():
        return f"SH{ticker}" if ticker.startswith(("5", "6", "9")) else f"SZ{ticker}"
    return ticker


def load_signal_csv(path: Path, ticker: str) -> pd.Series:
    df = pd.read_csv(path)
    value_column = "target_position" if "target_position" in df.columns else "score"
    required = {"date", value_column}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Signal file missing required columns: {sorted(missing)}")

    df = df.copy()
    df["datetime"] = pd.to_datetime(df["date"])
    df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    df = df.dropna(subset=["datetime", value_column]).sort_values("datetime")

    instrument = format_instrument(ticker)
    index = pd.MultiIndex.from_arrays(
        [[instrument] * len(df), df["datetime"]],
        names=["instrument", "datetime"],
    )
    return pd.Series(df[value_column].to_numpy(dtype=float), index=index, name=value_column)


def validate_qlib_coverage(instrument: str, start: str, end: str) -> None:
    prices = D.features(
        [instrument],
        ["$open", "$close"],
        start_time=start,
        end_time=end,
        freq="day",
    )
    valid_prices = prices.dropna(how="all")
    if valid_prices.empty:
        raise RuntimeError(
            "Qlib provider has no usable price data for "
            f"{instrument} during {start} -> {end}. "
            "Please pass a provider with matching A-share data via --provider-uri."
        )


def make_benchmark(benchmark: Optional[str], start: str, end: str):
    if benchmark:
        return benchmark
    calendar = pd.to_datetime(D.calendar(start_time=start, end_time=end, freq="day"))
    return pd.Series(0.0, index=calendar, name="zero_benchmark")


def resolve_execution_end(end: str) -> str:
    future_calendar = pd.to_datetime(D.calendar(start_time=end, freq="day"))
    if len(future_calendar) >= 2:
        return future_calendar[1].strftime("%Y-%m-%d")

    history_calendar = pd.to_datetime(D.calendar(end_time=end, freq="day"))
    if len(history_calendar) >= 2:
        print(
            f"[warning] Qlib calendar has no trading day after {end}. "
            "Backtest will stop at the last executable day, so the final signal "
            "cannot be executed under the built-in one-step delay."
        )
        return history_calendar[-2].strftime("%Y-%m-%d")

    raise RuntimeError(
        f"Qlib calendar has insufficient data around {end}. "
        "Please rebuild the provider with matching market data."
    )


def calculate_metrics(report: pd.DataFrame) -> dict:
    if report is None or report.empty:
        return {}

    account = report["account"].astype(float)
    daily_return = report["return"].fillna(0.0).astype(float)
    total_return = account.iloc[-1] / account.iloc[0] - 1
    annual_return = (1 + total_return) ** (252 / len(report)) - 1 if len(report) > 0 else np.nan
    drawdown = account / account.cummax() - 1
    volatility = daily_return.std() * np.sqrt(252)
    sharpe = daily_return.mean() / daily_return.std() * np.sqrt(252) if daily_return.std() > 0 else 0.0

    return {
        "start_account": account.iloc[0],
        "end_account": account.iloc[-1],
        "total_return": total_return,
        "annual_return": annual_return,
        "max_drawdown": drawdown.min(),
        "sharpe": sharpe,
        "volatility": volatility,
        "turnover_sum": report.get("turnover", pd.Series(dtype=float)).fillna(0.0).sum(),
        "cost_sum": report.get("cost", pd.Series(dtype=float)).fillna(0.0).sum(),
        "trading_days": len(report),
    }


def derive_trade_events(report: pd.DataFrame) -> pd.DataFrame:
    if report is None or report.empty:
        return pd.DataFrame()

    df = report.reset_index().rename(columns={"index": "datetime"}).copy()
    if "datetime" not in df.columns:
        df.insert(0, "datetime", report.index)

    for col in ["value", "cash", "turnover", "cost", "account"]:
        if col not in df.columns:
            df[col] = np.nan

    trades = df[df["turnover"].fillna(0.0) > 0].copy()
    trades["prev_value"] = trades["value"].shift(1).fillna(0.0)
    trades["side"] = np.where(trades["value"] > trades["prev_value"], "BUY", "SELL")
    return trades[["datetime", "side", "value", "cash", "turnover", "cost", "account"]]


def save_positions(positions, path: Path) -> Path:
    if isinstance(positions, pd.DataFrame):
        positions.to_csv(path)
        return path

    if isinstance(positions, dict):
        rows = []
        for dt, pos in positions.items():
            row = {"datetime": dt}
            if hasattr(pos, "get_cash"):
                row["cash"] = pos.get_cash()
            if hasattr(pos, "position"):
                for key, value in pos.position.items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            row[f"{key}.{sub_key}"] = sub_value
                    else:
                        row[str(key)] = value
            rows.append(row)
        if rows:
            pd.DataFrame(rows).to_csv(path, index=False)
            return path

    pickle_path = path.with_suffix(".pkl")
    with pickle_path.open("wb") as f:
        pickle.dump(positions, f)
    return pickle_path


def main() -> None:
    args = parse_args()
    signal_path = Path(args.signals).expanduser().resolve()
    if not signal_path.exists():
        raise FileNotFoundError(signal_path)

    inferred_ticker, inferred_start, inferred_end = infer_from_filename(signal_path)
    ticker = args.ticker or inferred_ticker
    if ticker is None:
        raise ValueError("Ticker was not provided and could not be inferred from the signal filename.")

    raw = pd.read_csv(signal_path)
    signal_dates = pd.to_datetime(raw["date"])
    start = args.start or inferred_start or signal_dates.min().strftime("%Y-%m-%d")
    end = args.end or inferred_end or signal_dates.max().strftime("%Y-%m-%d")

    qlib.init(provider_uri=args.provider_uri, region="cn")
    signals = load_signal_csv(signal_path, ticker)
    instrument = format_instrument(ticker)
    validate_qlib_coverage(instrument, start, end)
    execution_end = resolve_execution_end(end)

    strategy = SingleStockSignalStrategy(
        signal=signals,
        buy_threshold=args.buy_threshold,
        sell_threshold=args.sell_threshold,
        target_position=args.target_position,
        debug_decisions=args.debug_decisions,
        signal_is_target_position=signals.name == "target_position",
    )

    exchange_kwargs = {
        "freq": "day",
        "limit_threshold": 0.1,
        "deal_price": args.deal_price,
        "open_cost": args.open_cost,
        "close_cost": args.close_cost,
        "min_cost": args.min_cost,
    }

    report, positions = backtest_daily(
        start_time=start,
        end_time=execution_end,
        strategy=strategy,
        executor=None,
        account=args.init_cash,
        benchmark=make_benchmark(args.benchmark, start, execution_end),
        exchange_kwargs=exchange_kwargs,
    )

    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{ticker}_{start}_{end}"

    report_path = output_dir / f"qlib_signal_backtest_report_{stem}.csv"
    positions_path = output_dir / f"qlib_signal_backtest_positions_{stem}.csv"
    metrics_path = output_dir / f"qlib_signal_backtest_metrics_{stem}.csv"
    trades_path = output_dir / f"qlib_signal_backtest_trades_{stem}.csv"

    report.to_csv(report_path)
    saved_positions_path = save_positions(positions, positions_path)
    metrics = calculate_metrics(report)
    pd.DataFrame([metrics]).to_csv(metrics_path, index=False)
    derive_trade_events(report).to_csv(trades_path, index=False)

    print("Qlib signal backtest finished")
    print(f"signals      : {signal_path}")
    print(f"instrument   : {instrument}")
    print(f"period       : {start} -> {end}")
    print(f"execution_end: {execution_end}")
    print(f"provider_uri : {args.provider_uri}")
    print(f"report       : {report_path}")
    print(f"positions    : {saved_positions_path}")
    print(f"metrics      : {metrics_path}")
    print(f"trades       : {trades_path}")
    if metrics:
        print(f"total_return : {metrics['total_return']:.2%}")
        print(f"max_drawdown : {metrics['max_drawdown']:.2%}")
        print(f"sharpe       : {metrics['sharpe']:.2f}")


if __name__ == "__main__":
    main()
