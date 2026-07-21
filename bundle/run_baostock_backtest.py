"""
回测对比：baostock 拿价格，不依赖 Qlib
"""
import baostock as bs
import pandas as pd
import numpy as np
from pathlib import Path

INIT_CASH = 100000.0
STOCKS = ["600519", "000333", "300750", "600760", "601318", "600030"]
RESULTS_DIR = Path("outputs/backtests/baostock")

def get_price(stock_code: str, start: str, end: str) -> pd.DataFrame:
    """从 baostock 获取日线价格"""
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"baostock login failed: {lg.error_msg}")

    # 转换代码格式: 600519 -> sh.600519
    if stock_code.startswith(("6", "5")):
        bs_code = f"sh.{stock_code}"
    else:
        bs_code = f"sz.{stock_code}"

    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume",
        start_date=start, end_date=end,
        frequency="d", adjustflag="3"
    )
    bs.logout()

    if rs.error_code != '0':
        raise RuntimeError(f"baostock query failed: {rs.error_msg}")

    data = []
    while rs.next():
        data.append(rs.get_row_data())

    df = pd.DataFrame(data, columns=['date','open','high','low','close','volume'])
    df['date'] = pd.to_datetime(df['date'])
    df['close'] = df['close'].astype(float)
    df['open'] = df['open'].astype(float)
    return df

def backtest(prices_df: pd.DataFrame, actions_df: pd.DataFrame, init_cash=100000.0) -> dict:
    """
    简单多头/空仓策略回测
    action=买入 -> 满仓
    action=卖出 -> 空仓
    action=持有 -> 保持当前仓位
    """
    prices = prices_df.set_index("date")["close"].sort_index()
    actions = actions_df.set_index("date")["action"].sort_index()

    common = prices.index.intersection(actions.index)
    if len(common) < 2:
        return None

    prices = prices.loc[common]
    actions = actions.loc[common]

    cash = init_cash
    shares = 0.0
    values = []

    for date in common:
        price = prices.loc[date]
        if pd.isna(price) or price <= 0:
            values.append(cash + shares * 100)
            continue
        action = actions.loc[date]

        if action == "买入" and cash > price * 100 and shares == 0:
            buy_amount = int((cash * 0.95) / price / 100) * 100
            if buy_amount >= 100:
                cost = buy_amount * price * 1.0005
                cash -= cost
                shares += buy_amount
        elif action == "卖出" and shares > 0:
            revenue = shares * price * 0.9985
            cash += revenue
            shares = 0.0

        values.append(cash + shares * price)

    values = pd.Series(values, index=common)
    returns = values.pct_change().fillna(0)

    total_ret = values.iloc[-1] / init_cash - 1
    annual = (1 + total_ret) ** (252 / len(values)) - 1
    max_dd = ((values / values.cummax()) - 1).min()
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0.0

    return {
        "total_return": total_ret,
        "annual_return": annual,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "trading_days": len(values),
        "final_value": values.iloc[-1],
    }

def main():
    print("=" * 60)
    print("回测对比: 原始 TradingAgents vs 训练后模型")
    print("=" * 60)

    results = []
    start_date, end_date = "2024-01-17", "2024-01-31"

    # 预加载所有股票价格
    print("获取价格数据...")
    price_cache = {}
    for ticker in STOCKS:
        try:
            price_cache[ticker] = get_price(ticker, start_date, end_date)
            print(f"  {ticker}: {len(price_cache[ticker])} 个交易日")
        except Exception as e:
            print(f"  {ticker}: 价格获取失败 - {e}")
            price_cache[ticker] = None

    for ticker in STOCKS:
        print(f"\n--- {ticker} ---")

        baseline_csv = RESULTS_DIR / f"baseline_{ticker}.csv"
        trained_csv = RESULTS_DIR / f"trained_{ticker}.csv"

        if not baseline_csv.exists():
            print(f"  缺少原始信号")
            continue
        if not trained_csv.exists():
            print(f"  缺少训练后信号")
            continue

        prices = price_cache.get(ticker)
        if prices is None or prices.empty:
            print(f"  无价格数据")
            continue

        b_df = pd.read_csv(baseline_csv)
        b_df['date'] = pd.to_datetime(b_df['date'])
        t_df = pd.read_csv(trained_csv)
        t_df['date'] = pd.to_datetime(t_df['date'])

        b = backtest(prices, b_df)
        t = backtest(prices, t_df)

        b_ret = f"{b['total_return']:+.2%}" if b else "N/A"
        t_ret = f"{t['total_return']:+.2%}" if t else "N/A"
        b_s = f"{b['sharpe']:.2f}" if b else "N/A"
        t_s = f"{t['sharpe']:.2f}" if t else "N/A"
        b_d = f"{b['max_drawdown']:.2%}" if b else "N/A"
        t_d = f"{t['max_drawdown']:.2%}" if t else "N/A"
        b_v = f"{b['final_value']:.0f}" if b else "N/A"
        t_v = f"{t['final_value']:.0f}" if t else "N/A"

        print(f"  原始: 总收益={b_ret} 夏普={b_s} 最大回撤={b_d} 终值={b_v}")
        print(f"  训练后: 总收益={t_ret} 夏普={t_s} 最大回撤={t_d} 终值={t_v}")

        results.append({
            "ticker": ticker,
            "baseline_return": b["total_return"] if b else None,
            "trained_return": t["total_return"] if t else None,
            "baseline_sharpe": b["sharpe"] if b else None,
            "trained_sharpe": t["sharpe"] if t else None,
            "baseline_maxdd": b["max_drawdown"] if b else None,
            "trained_maxdd": t["max_drawdown"] if t else None,
        })

    if not results:
        print("无有效结果")
        return

    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"{'股票':<10} {'指标':<12} {'原始TradingAgents':<18} {'训练后模型':<18}")
    print("-" * 60)
    for s in results:
        b_r = f"{s['baseline_return']:+.2%}" if s['baseline_return'] is not None else "N/A"
        t_r = f"{s['trained_return']:+.2%}" if s['trained_return'] is not None else "N/A"
        b_sh = f"{s['baseline_sharpe']:.2f}" if s['baseline_sharpe'] is not None else "N/A"
        t_sh = f"{s['trained_sharpe']:.2f}" if s['trained_sharpe'] is not None else "N/A"
        b_d = f"{s['baseline_maxdd']:.2%}" if s['baseline_maxdd'] is not None else "N/A"
        t_d = f"{s['trained_maxdd']:.2%}" if s['trained_maxdd'] is not None else "N/A"
        print(f"{s['ticker']:<10} {'总收益率':<12} {b_r:<18} {t_r:<18}")
        print(f"{'':<10} {'夏普比率':<12} {b_sh:<18} {t_sh:<18}")
        print(f"{'':<10} {'最大回撤':<12} {b_d:<18} {t_d:<18}")
        print("-" * 60)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(RESULTS_DIR / "backtest_comparison_final.csv", index=False)
    print("\n汇总已保存: outputs/backtests/baostock/backtest_comparison_final.csv")

if __name__ == "__main__":
    main()
