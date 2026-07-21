"""
TradingAgents 单股信号生成脚本
自定义股票、日期、分析师组合
"""
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# === 配置区 ===============================
STOCKS = {
    '002594': '比亚迪',
    '000001': '平安银行',
    '300269': '联建光电',
    '600036': '招商银行',
    '600519': '贵州茅台',
    '601318': '中国平安',
    '000858': '五粮液',
    '002415': '海康威视',
    '688525': '佰维存储',
    '301308': '江波龙',
    '603986': '兆易创新',
}

AVAILABLE_ANALYSTS = {
    'market':        '市场技术分析师',
    'fundamentals':  '基本面分析师',
    'news':          '新闻事件分析师',
    'social':        '社交媒体分析师',
}

DEFAULT_ANALYSTS = ['market', 'fundamentals', 'news', 'social']


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


# === 主程序 ===============================
def main():
    parser = argparse.ArgumentParser(description='TradingAgents 单股信号生成')
    parser.add_argument('--ticker', type=str, default='002594',
                        help=f'股票代码，默认 002594(比亚迪)，可选: {list(STOCKS.keys())}')
    parser.add_argument('--date', type=str, default=None,
                        help='交易日期 YYYY-MM-DD，默认今天')
    parser.add_argument('--analysts', type=str, nargs='+',
                        default=None,
                        help=f'分析师组合，默认 {" ".join(DEFAULT_ANALYSTS)}')
    parser.add_argument('--max-debate-rounds', type=int, default=1,
                        help='辩论轮数，默认 1')
    parser.add_argument('--max-risk-rounds', type=int, default=1,
                        help='风险讨论轮数，默认 1')
    parser.add_argument('--provider', type=str, default='deepseek',
                        help='模型供应商，例如 deepseek/openai/qwen/openrouter/google')
    parser.add_argument('--model', type=str, default='deepseek-v4-flash',
                        help='同时设置 quick/deep 的模型；例如 deepseek-v4-flash/deepseek-v4-pro')
    parser.add_argument('--quick-model', type=str, default=None,
                        help='快速模型；不填则使用 --model')
    parser.add_argument('--deep-model', type=str, default=None,
                        help='深度模型；不填则使用 --model')
    parser.add_argument('--backend-url', type=str, default=None,
                        help='自定义模型 API 地址；不填则使用 provider 默认地址')
    parser.add_argument('--debug', action='store_true',
                        help='开启 debug 日志')
    parser.add_argument('--save-result', type=str, default=None,
                        help='信号结果保存路径 (.json)')
    parser.add_argument('--run-name', type=str, default=None,
                        help='实验运行名；设置后报告/轨迹/审计/默认信号保存到 outputs/runs/{run-name}/')
    args = parser.parse_args()

    if args.ticker not in STOCKS:
        print(f"❌ 未知股票代码: {args.ticker}")
        print(f"   可选: {list(STOCKS.keys())}")
        sys.exit(1)

    analysts = args.analysts or DEFAULT_ANALYSTS
    for a in analysts:
        if a not in AVAILABLE_ANALYSTS:
            print(f"❌ 未知分析师: {a}")
            print(f"   可选: {list(AVAILABLE_ANALYSTS.keys())}")
            sys.exit(1)

    trade_date = args.date or datetime.now().strftime('%Y-%m-%d')

    # === 初始化（相对路径，兼容 bundle 移动）===
    bundle_root = Path(__file__).parent
    load_local_env(bundle_root)
    sys.path.insert(0, str(bundle_root))

    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients.provider_keys import default_backend_url, env_key_for_provider

    env_key = env_key_for_provider(args.provider)
    api_key = os.getenv(env_key, '') if env_key else ''
    if not api_key:
        print(f"❌ 请设置 {env_key or '对应模型供应商的 API Key'} 环境变量")
        if env_key:
            print(f"   export {env_key}='sk-...'")
        sys.exit(1)

    quick_model = args.quick_model or args.model
    deep_model = args.deep_model or args.model

    config = DEFAULT_CONFIG.copy()
    config.update({
        'project_dir': str(bundle_root),
        'llm_provider': args.provider,
        'deep_think_llm': deep_model,
        'quick_think_llm': quick_model,
        'backend_url': args.backend_url or default_backend_url(args.provider),
        'max_debate_rounds': args.max_debate_rounds,
        'max_risk_discuss_rounds': args.max_risk_rounds,
        'api_key': api_key,
        'run_name': args.run_name,
    })

    print(f"📊 [{STOCKS[args.ticker]}] {trade_date}")
    print(f"   分析师: {' + '.join(AVAILABLE_ANALYSTS[a] for a in analysts)}")
    print(f"   辩论/风险轮数: {args.max_debate_rounds}/{args.max_risk_rounds}")
    print(f"   API: {args.provider} (quick={quick_model}, deep={deep_model})")
    print()

    ta = TradingAgentsGraph(
        debug=args.debug,
        config=config,
        selected_analysts=analysts,
    )

    _, decision = ta.propagate(args.ticker, trade_date)

    print()
    print("=" * 60)
    print(f"📋 信号结果 [{STOCKS[args.ticker]} - {trade_date}]")
    print("=" * 60)
    print(f"  操作:       {decision.get('action', 'N/A')}")
    print(f"  置信度:     {decision.get('confidence', 'N/A')}")
    print(f"  目标价:     {decision.get('target_price', 'N/A')}")
    print(f"  风险得分:   {decision.get('risk_score', 'N/A')}")
    print(f"  理由:       {decision.get('reasoning', 'N/A')[:200]}")
    print("=" * 60)

    result = {
        'ticker': args.ticker,
        'name': STOCKS[args.ticker],
        'date': trade_date,
        'analysts': analysts,
        'decision': decision,
    }

    if args.run_name:
        from tradingagents.utils.artifacts import resolve_artifact_dir

        outputs_dir = resolve_artifact_dir(bundle_root, "signals", run_name=args.run_name)
        reports_dir = resolve_artifact_dir(bundle_root, "reports", run_name=args.run_name)
        trajectories_dir = resolve_artifact_dir(bundle_root, "trajectories", run_name=args.run_name)
        audit_dir = resolve_artifact_dir(bundle_root, "audit_reports", run_name=args.run_name)
    else:
        outputs_dir = bundle_root / "outputs" / "signals"
        reports_dir = bundle_root / "outputs" / "reports"
        trajectories_dir = bundle_root / "outputs" / "trajectories"
        audit_dir = bundle_root / "outputs" / "audit_reports"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    save_path = args.save_result
    if not save_path:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        save_path = str(outputs_dir / f'signal_{args.ticker}_{trade_date}_{ts}.json')

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n💾 结果已保存: {save_path}")
    print(f"📁 轨迹文件:   {trajectories_dir / f'trajectory_{args.ticker}_{trade_date}.json'}")
    print(f"📁 审计报告:   {audit_dir / f'audit_{args.ticker}_{trade_date}.json'}")
    print(f"📝 复盘报告:   {reports_dir / f'report_{args.ticker}_{trade_date}.md'}")

if __name__ == '__main__':
    main()
