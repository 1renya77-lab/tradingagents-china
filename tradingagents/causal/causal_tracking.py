"""
因果追踪核心数据结构
Causal Credit Assignment for Multi-Agent Trading System
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CausalNode:
    """因果链中的一个节点"""
    node_id: str  # 唯一标识
    agent_id: str  # 谁说的 (e.g., "Portfolio_Manager", "Conservative_Analyst")
    content: str  # 说什么
    confidence: float = 0.5  # 自身置信度 0.0-1.0
    evidence_refs: list[str] = field(default_factory=list)  # 引用的节点ID
    credit: float = 0.0  # 最终分配的信用

    def __post_init__(self):
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class CausalChain:
    """完整因果链"""
    nodes: dict[str, CausalNode] = field(default_factory=dict)
    final_decision: Optional[str] = None
    final_credit: float = 1.0

    def add_node(
        self,
        node_id: str,
        agent_id: str,
        content: str,
        confidence: float = 0.5,
        evidence_refs: list[str] | None = None,
    ) -> CausalNode:
        """添加一个节点到因果链"""
        node = CausalNode(
            node_id=node_id,
            agent_id=agent_id,
            content=content,
            confidence=confidence,
            evidence_refs=evidence_refs or [],
        )
        self.nodes[node_id] = node
        return node

    def get_node(self, node_id: str) -> Optional[CausalNode]:
        """获取节点"""
        return self.nodes.get(node_id)

    def get_root_nodes(self) -> list[CausalNode]:
        """获取根节点（没有被引用的节点）"""
        all_refs = set()
        for node in self.nodes.values():
            all_refs.update(node.evidence_refs)
        return [n for n in self.nodes.values() if n.node_id not in all_refs]

    def propagate_credit(self) -> None:
        """
        反向传播信用
        从最终决策节点开始，反向计算每个节点的贡献
        """
        if not self.final_decision or self.final_decision not in self.nodes:
            return

        # 重置所有节点的信用
        for node in self.nodes.values():
            node.credit = 0.0

        # 从最终决策节点开始反向传播
        self._propagate(self.final_decision, self.final_credit)

    def _propagate(self, node_id: str, credit: float) -> None:
        """递归反向传播"""
        if node_id not in self.nodes:
            return

        node = self.nodes[node_id]
        node.credit = max(node.credit, credit)  # 取最大值（可能被多个节点引用）

        if not node.evidence_refs:
            return

        # 信用分配给引用节点
        # 每个引用节点获得 credit * (1 / ref_count) * 引用节点置信度
        ref_count = len(node.evidence_refs)
        base_share = credit / ref_count

        for ref_id in node.evidence_refs:
            if ref_id in self.nodes:
                ref_node = self.nodes[ref_id]
                # 引用节点获得的信用 = 基础份额 * 引用节点的置信度
                inherited_credit = base_share * ref_node.confidence
                self._propagate(ref_id, inherited_credit)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "final_decision": self.final_decision,
            "final_credit": self.final_credit,
            "nodes": {
                node_id: {
                    "agent_id": node.agent_id,
                    "content_preview": node.content[:100] + "..."
                    if len(node.content) > 100
                    else node.content,
                    "confidence": node.confidence,
                    "evidence_refs": node.evidence_refs,
                    "credit": node.credit,
                }
                for node_id, node in self.nodes.items()
            },
        }

    def get_credit_ranking(self) -> list[tuple[str, float, str]]:
        """获取信用排名 (node_id, credit, agent_id)"""
        ranking = [
            (node_id, node.credit, node.agent_id)
            for node_id, node in self.nodes.items()
        ]
        ranking.sort(key=lambda x: x[1], reverse=True)
        return ranking
