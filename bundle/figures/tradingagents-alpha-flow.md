# TradingAgents Alpha-Oriented Flow

This diagram summarizes the current A-share TradingAgents pipeline at a method level: evidence is converted into analyst reports, debated by multiple agents, transformed into target positions, calibrated under A-share constraints, and evaluated through Qlib.

```mermaid
%%{init: {"theme": "base", "flowchart": {"curve": "basis", "nodeSpacing": 58, "rankSpacing": 52}, "themeVariables": {"fontFamily": "Helvetica, Arial, sans-serif", "fontSize": "16px", "primaryColor": "#F7F8FA", "primaryTextColor": "#172033", "primaryBorderColor": "#CBD5E1", "lineColor": "#475569", "tertiaryColor": "#F8FAFC"}}}%%
flowchart TB
    I["A-share Evidence<br/><span style='font-size:13px'>price · fundamentals · news · sentiment</span>"]
    A["Analyst Layer<br/><span style='font-size:13px'>market · fundamentals · news · social reports</span>"]
    D["Multi-Agent Deliberation<br/><span style='font-size:13px'>bull/bear research + aggressive/neutral/conservative risk debate</span>"]
    P["Position-Aware Decision<br/><span style='font-size:13px'>Risk Manager outputs action + target_position + invalidation rules</span>"]
    G["Execution Calibration<br/><span style='font-size:13px'>A-share long-only constraints · risk caps · alpha participation floors</span>"]
    Q["Qlib Evaluation<br/><span style='font-size:13px'>weekly signals · next-step daily execution · return/alpha/IR/drawdown/alignment</span>"]

    I --> A --> D --> P --> G --> Q
    Q -. "diagnostics guide prompt and gate updates" .-> D

    classDef input fill:#EAF3F8,stroke:#5B8FA8,stroke-width:1.6px,color:#172033;
    classDef agent fill:#F7F4EA,stroke:#A88B4D,stroke-width:1.6px,color:#172033;
    classDef decision fill:#EEF6EF,stroke:#5E9C67,stroke-width:1.6px,color:#172033;
    classDef eval fill:#F3F0F7,stroke:#8A6BA8,stroke-width:1.6px,color:#172033;

    class I input;
    class A,D agent;
    class P,G decision;
    class Q eval;
```
