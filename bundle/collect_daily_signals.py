"""
日频信号采集脚本
采集单只股票指定日期范围的 TradingAgents 决策信号
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# 相对路径（bundle根目录）
bundle_root = Path(__file__).parent


def load_local_env(bundle_root: Path) -> None:
    """Load bundle-local .env so users do not need to export API keys every run."""
    env_path = bundle_root / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_local_env(bundle_root)
sys.path.insert(0, str(bundle_root))

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.provider_keys import default_backend_url, env_key_for_provider
from tradingagents.utils.artifacts import resolve_artifact_dir
from signal_positioning import derive_target_position
import pandas as pd


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def decision_to_score(action: str, confidence, risk_score) -> tuple[float, float]:
    """Map an LLM action into a continuous long-only signal score."""
    action_score = {"买入": 1.0, "持有": 0.5, "卖出": 0.0}.get(action, 0.5)
    confidence = _clamp(_as_float(confidence, 0.5))
    risk_score = _clamp(_as_float(risk_score, 0.5))

    if action == "买入":
        strength = confidence * (1.0 - 0.5 * risk_score)
        score = 0.5 + 0.5 * strength
    elif action == "卖出":
        strength = confidence * (0.5 + 0.5 * risk_score)
        score = 0.5 - 0.5 * strength
    else:
        score = 0.5

    return round(_clamp(score), 4), action_score


def build_signal_dates(start_date: str, end_date: str, frequency: str = "daily") -> pd.DatetimeIndex:
    """Build signal dates for daily or weekly collection."""
    all_business_days = pd.date_range(start=start_date, end=end_date, freq="B")
    if frequency == "daily":
        return all_business_days
    if frequency == "weekly":
        # Pick the last business day inside each calendar week.
        return pd.DatetimeIndex(all_business_days.to_series().groupby(all_business_days.to_period("W")).tail(1))
    raise ValueError("frequency must be 'daily' or 'weekly'")


def build_signal_filename(ticker: str, start_date: str, end_date: str, frequency: str) -> str:
    return f"signals_{ticker}_{start_date}_{end_date}_{frequency}_position.csv"


def resolve_output_path(
    ticker: str,
    start_date: str,
    end_date: str,
    frequency: str,
    output_file: str = None,
    run_name: str = None,
) -> Path:
    outputs_dir = resolve_artifact_dir(bundle_root, "signals", run_name=run_name)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    if output_file:
        output_path = Path(output_file)
        if not output_path.is_absolute():
            output_path = bundle_root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path
    return outputs_dir / build_signal_filename(ticker, start_date, end_date, frequency)


def load_existing_success_dates(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    df = pd.read_csv(output_path)
    if "date" not in df.columns or "status" not in df.columns:
        return set()
    ok = df[df["status"] == "ok"]
    return set(ok["date"].astype(str))


def save_progress(output_path: Path, rows: list[dict]) -> pd.DataFrame:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    new_df = pd.DataFrame(rows)
    if output_path.exists():
        old_df = pd.read_csv(output_path)
        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df
    if not combined.empty and "date" in combined.columns:
        combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    combined.to_csv(output_path, index=False, encoding="utf-8")
    return combined


def build_horizon_config(frequency: str) -> dict[str, str]:
    """Translate sampling frequency into the decision horizon seen by agents."""
    if frequency == "daily":
        return {
            "signal_frequency": "daily",
            "decision_horizon": "next_trading_day",
            "horizon_label": "下一交易日",
            "horizon_instruction": (
                "本次信号是日频信号：请基于当前交易日收盘前后可获得的信息，"
                "判断下一交易日的可执行操作。不要把结论扩展为未来一周配置建议。"
            ),
        }
    if frequency == "weekly":
        return {
            "signal_frequency": "weekly",
            "decision_horizon": "next_5_trading_days",
            "horizon_label": "未来5个交易日/直到下一次周频再平衡",
            "horizon_instruction": (
                "本次信号是周频信号：请基于当前交易日收盘前后可获得的信息，"
                "判断未来5个交易日，或直到下一次周频信号生成前的持仓操作。"
                "不要只预测明天单日涨跌；重点评估一周级别的趋势延续、均值回归、"
                "事件风险、基本面催化和仓位风险。"
            ),
        }
    raise ValueError("frequency must be 'daily' or 'weekly'")


def collect_daily_signals(
    ticker: str,
    start_date: str,
    end_date: str,
    frequency: str = "daily",
    selected_analysts: list = None,
    llm_provider: str = "deepseek",
    model: str = "deepseek-v4-flash",
    quick_model: str = None,
    deep_model: str = None,
    backend_url: str = None,
    max_debate_rounds: int = 1,
    output_file: str = None,
    run_name: str = None,
    resume: bool = False,
) -> pd.DataFrame:
    if selected_analysts is None:
        selected_analysts = ["market", "news", "social", "fundamentals"]

    quick_model = quick_model or model
    deep_model = deep_model or model

    date_range = build_signal_dates(start_date, end_date, frequency)
    output_path = resolve_output_path(ticker, start_date, end_date, frequency, output_file, run_name)
    completed_dates = load_existing_success_dates(output_path) if resume else set()

    frequency_label = "日频" if frequency == "daily" else "周频"
    print(f"📅 将采集 {len(date_range)} 个{frequency_label}信号")
    print(f"📊 股票: {ticker}, 时间: {start_date} ~ {end_date}")
    print(f"🤖 LLM: {llm_provider}, quick={quick_model}, deep={deep_model}, 分析师: {selected_analysts}")
    if resume:
        print(f"🔁 断点续跑: 已有 {len(completed_dates)} 个成功信号，将跳过这些日期")
        print(f"💾 进度文件: {output_path}")
    print("-" * 50)

    config = DEFAULT_CONFIG.copy()
    config['project_dir'] = str(bundle_root)
    config['llm_provider'] = llm_provider
    config['backend_url'] = backend_url or default_backend_url(llm_provider)
    config['deep_think_llm'] = deep_model
    config['quick_think_llm'] = quick_model
    config['max_debate_rounds'] = max_debate_rounds
    config['max_risk_discuss_rounds'] = max_debate_rounds
    config['run_name'] = run_name
    config.update(build_horizon_config(frequency))

    env_key = env_key_for_provider(llm_provider)
    api_key = os.getenv(env_key, '') if env_key else ''
    if not api_key:
        print(f"❌ 请设置 {env_key or '对应模型供应商的 API Key'} 环境变量")
        sys.exit(1)
    config['api_key'] = api_key

    print("🔧 初始化 TradingAgentsGraph...")
    ta = TradingAgentsGraph(
        debug=False,
        config=config,
        selected_analysts=selected_analysts
    )

    results = []

    for i, date in enumerate(date_range):
        date_str = date.strftime("%Y-%m-%d")
        if date_str in completed_dates:
            print(f"\n[{i+1}/{len(date_range)}] 跳过 {ticker} @ {date_str} (已有成功信号)")
            continue

        print(f"\n[{i+1}/{len(date_range)}] 分析 {ticker} @ {date_str}...", end=" ", flush=True)

        try:
            _, decision = ta.propagate(
                ticker,
                date_str,
                progress_callback=lambda x: None
            )

            action = decision.get("action", "持有")
            confidence = decision.get("confidence", 0.5)
            risk_score = decision.get("risk_score", 0.5)
            target_price = decision.get("target_price")
            reasoning = decision.get("reasoning", "")
            score, action_score = decision_to_score(action, confidence, risk_score)
            target_position = derive_target_position(action, reasoning)

            row = {
                "date": date_str,
                "ticker": ticker,
                "status": "ok",
                "error_message": "",
                "action": action,
                "confidence": confidence,
                "risk_score": risk_score,
                "target_price": target_price,
                "action_score": action_score,
                "score": score,
                "target_position": target_position,
                "reasoning": reasoning[:200] if reasoning else "",
            }
            results.append(row)
            save_progress(output_path, [row])
            print(
                f"→ {action} "
                f"(置信度: {_as_float(confidence, 0.5):.2f}, "
                f"风险: {_as_float(risk_score, 0.5):.2f}, "
                f"分数: {score:.2f}, 目标仓位: {target_position:.1%})"
            )

        except Exception as e:
            print(f"⚠️ 失败: {e}")
            row = {
                "date": date_str,
                "ticker": ticker,
                "status": "error",
                "error_message": str(e)[:200],
                "action": "持有",
                "confidence": 0.0,
                "risk_score": 1.0,
                "target_price": None,
                "action_score": 0.5,
                "score": 0.5,
                "target_position": 0.0,
                "reasoning": f"Error: {str(e)[:100]}",
            }
            results.append(row)
            save_progress(output_path, [row])

    if output_path.exists():
        df = pd.read_csv(output_path)
    else:
        df = pd.DataFrame(results)
        save_progress(output_path, results)

    print("\n" + "=" * 50)
    print(f"✅ 完成！共 {len(df)} 条信号")
    print(f"💾 已保存到: {output_path}")
    print("=" * 50)
    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="批量信号采集")
    parser.add_argument("--ticker", default="000001", help="股票代码")
    parser.add_argument("--start", default="2025-07-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="2025-07-31", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--frequency", choices=["daily", "weekly"], default="daily",
                        help="信号频率：daily=工作日逐日信号；weekly=每周最后一个工作日信号")
    parser.add_argument("--analysts", type=str, nargs='+',
                        default=None, help="分析师组合")
    parser.add_argument("--max-debate-rounds", type=int, default=1)
    parser.add_argument("--provider", default="deepseek",
                        help="模型供应商，例如 deepseek/openai/qwen/openrouter/google")
    parser.add_argument("--model", default="deepseek-v4-flash",
                        help="同时设置 quick/deep 的模型；例如 deepseek-v4-flash/deepseek-v4-pro")
    parser.add_argument("--quick-model", default=None,
                        help="快速模型；不填则使用 --model")
    parser.add_argument("--deep-model", default=None,
                        help="深度模型；不填则使用 --model")
    parser.add_argument("--backend-url", default=None,
                        help="自定义模型 API 地址；不填则使用 provider 默认地址")
    parser.add_argument("--output-file", default=None,
                        help="输出CSV路径；相对路径会基于bundle目录解析")
    parser.add_argument("--run-name", default=None,
                        help="实验运行名；设置后报告/轨迹/审计/默认信号保存到 outputs/runs/{run-name}/")
    parser.add_argument("--resume", action="store_true",
                        help="断点续跑：读取已有CSV，跳过 status=ok 的日期，并逐条保存新结果")

    args = parser.parse_args()

    analysts = args.analysts or ["market", "news", "social", "fundamentals"]

    collect_daily_signals(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        frequency=args.frequency,
        selected_analysts=analysts,
        llm_provider=args.provider,
        model=args.model,
        quick_model=args.quick_model,
        deep_model=args.deep_model,
        backend_url=args.backend_url,
        max_debate_rounds=args.max_debate_rounds,
        output_file=args.output_file,
        run_name=args.run_name,
        resume=args.resume,
    )
