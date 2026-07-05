"""
因果追踪器
追踪决策过程中的因果链
"""

import json
import logging
from pathlib import Path
from typing import Any

from .causal_tracking import CausalChain, CausalNode

logger = logging.getLogger(__name__)


class CausalTracker:
    """
    在图执行过程中追踪因果链

    用法:
        tracker = CausalTracker()
        node_id = tracker.record_decision(
            agent_id="Portfolio_Manager",
            content="决定买入",
            confidence=0.8,
            evidence_refs=["conservative_1", "market_1"]
        )
        tracker.set_final_decision(node_id)
        report = tracker.get_credit_report()
    """

    def __init__(self, results_dir: str = "./results"):
        self.chain = CausalChain()
        self._node_counter = 0
        self._current_ticker: str | None = None
        self._current_date: str | None = None
        self.results_dir = Path(results_dir)

    def reset(self) -> None:
        """重置追踪器"""
        self.chain = CausalChain()
        self._node_counter = 0
        self._current_ticker = None
        self._current_date = None

    def create_node_id(self, agent_id: str) -> str:
        """生成唯一节点ID"""
        self._node_counter += 1
        return f"{agent_id}_{self._node_counter}"

    def record_decision(
        self,
        agent_id: str,
        content: str,
        confidence: float = 0.5,
        evidence_refs: list[str] | None = None,
    ) -> str:
        """
        记录一个决策节点

        Returns:
            node_id: 创建的节点ID
        """
        node_id = self.create_node_id(agent_id)
        self.chain.add_node(
            node_id=node_id,
            agent_id=agent_id,
            content=content,
            confidence=confidence,
            evidence_refs=evidence_refs or [],
        )
        logger.debug(f"Recorded node: {node_id} by {agent_id} with confidence {confidence}")
        return node_id

    def set_final_decision(self, node_id: str) -> None:
        """设置最终决策节点并执行信用传播"""
        self.chain.final_decision = node_id
        self.chain.final_credit = 1.0
        self.chain.propagate_credit()
        logger.info(f"Final decision set: {node_id}")

    def get_credit_report(self) -> dict:
        """获取信用分配报告"""
        return self.chain.to_dict()

    def get_top_contributors(self, n: int = 5) -> list[dict]:
        """获取贡献最大的n个节点"""
        ranking = self.chain.get_credit_ranking()[:n]
        return [
            {
                "node_id": node_id,
                "agent_id": agent_id,
                "credit": round(credit, 4),
            }
            for node_id, credit, agent_id in ranking
        ]

    def save_report(self, ticker: str, trade_date: str) -> Path:
        """保存因果报告到文件"""
        self._current_ticker = ticker
        self._current_date = trade_date

        report = {
            "ticker": ticker,
            "trade_date": trade_date,
            "causal_chain": self.get_credit_report(),
            "top_contributors": self.get_top_contributors(),
        }

        safe_ticker = "".join(c if c.isalnum() else "_" for c in ticker)
        directory = self.results_dir / safe_ticker / "causal_reports"
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / f"causal_report_{trade_date}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Causal report saved to {filepath}")
        return filepath

    def get_agent_credits(self) -> dict[str, float]:
        """获取每个agent的总信用"""
        agent_credits: dict[str, float] = {}
        for node in self.chain.nodes.values():
            if node.agent_id not in agent_credits:
                agent_credits[node.agent_id] = 0.0
            agent_credits[node.agent_id] += node.credit
        return agent_credits


class CausalReflection:
    """
    基于因果链的反思机制
    根据决策结果更新节点置信度
    """

    def __init__(self):
        self.node_confidence_history: dict[str, list[float]] = {}
        self.default_confidence: float = 0.5

    def record_outcome(
        self,
        causal_chain: CausalChain,
        actual_return: float,
        holding_days: int = 5,
    ) -> dict[str, float]:
        """
        记录决策结果，更新节点置信度

        Args:
            causal_chain: 因果链
            actual_return: 实际收益率 (正数=盈利, 负数=亏损)
            holding_days: 持仓天数

        Returns:
            更新后的置信度变化 {node_id: delta}
        """
        changes = {}
        is_profitable = actual_return > 0

        for node_id, node in causal_chain.nodes.items():
            if node_id not in self.node_confidence_history:
                self.node_confidence_history[node_id] = []

            old_confidence = node.confidence

            # 如果高信用的节点导致亏损，降低其置信度
            if node.credit > 0.2:
                if not is_profitable and node.credit > 0.3:
                    # 错误决策，降低置信度
                    node.confidence = max(0.1, node.confidence * 0.9)
                elif is_profitable and node.credit > 0.3:
                    # 正确决策，提高置信度
                    node.confidence = min(1.0, node.confidence * 1.1)

            self.node_confidence_history[node_id].append(node.confidence)
            changes[node_id] = node.confidence - old_confidence

        return changes

    def get_adjusted_confidence(self, node_id: str, default: float | None = None) -> float:
        """
        获取调整后的置信度

        如果有历史记录，返回指数加权平均
        否则返回默认置信度
        """
        if node_id not in self.node_confidence_history:
            return default if default is not None else self.default_confidence

        history = self.node_confidence_history[node_id]
        if not history:
            return default if default is not None else self.default_confidence

        # 指数加权平均，最近的权重更大
        weights = [0.9**i for i in range(len(history) - 1, -1, -1)]
        total_weight = sum(weights)
        weighted_avg = sum(h * w for h, w in zip(history, weights)) / total_weight
        return weighted_avg

    def get_credit_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "tracked_nodes": len(self.node_confidence_history),
            "nodes_with_history": {
                node_id: len(history)
                for node_id, history in self.node_confidence_history.items()
            },
        }
