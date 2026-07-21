from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MULTI_SOURCE_ANALYSTS = ["market", "fundamentals", "news", "social"]


@dataclass(frozen=True)
class ExperimentModeConfig:
    name: str
    selected_analysts: list[str]
    single_llm_direct_enabled: bool
    enable_investment_debate: bool
    enable_risk_debate: bool

    def as_config(self) -> dict[str, object]:
        return {
            "experiment_mode": self.name,
            "single_llm_direct_enabled": self.single_llm_direct_enabled,
            "enable_investment_debate": self.enable_investment_debate,
            "enable_risk_debate": self.enable_risk_debate,
        }


EXPERIMENT_MODES: dict[str, ExperimentModeConfig] = {
    "single_llm_direct": ExperimentModeConfig(
        name="single_llm_direct",
        selected_analysts=DEFAULT_MULTI_SOURCE_ANALYSTS,
        single_llm_direct_enabled=True,
        enable_investment_debate=False,
        enable_risk_debate=False,
    ),
    "multi_agent_no_debate": ExperimentModeConfig(
        name="multi_agent_no_debate",
        selected_analysts=DEFAULT_MULTI_SOURCE_ANALYSTS,
        single_llm_direct_enabled=False,
        enable_investment_debate=False,
        enable_risk_debate=False,
    ),
    "multi_agent_full_debate": ExperimentModeConfig(
        name="multi_agent_full_debate",
        selected_analysts=DEFAULT_MULTI_SOURCE_ANALYSTS,
        single_llm_direct_enabled=False,
        enable_investment_debate=True,
        enable_risk_debate=True,
    ),
}


def resolve_experiment_mode(mode: str | None) -> ExperimentModeConfig:
    key = mode or "multi_agent_full_debate"
    try:
        return EXPERIMENT_MODES[key]
    except KeyError as exc:
        valid = ", ".join(sorted(EXPERIMENT_MODES))
        raise ValueError(f"Unknown experiment_mode: {key}. Valid modes: {valid}") from exc
