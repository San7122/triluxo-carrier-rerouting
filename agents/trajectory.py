"""Structured trajectory logging.

A Trajectory captures, per run, the ordered sequence of agent steps. Each step
records: the node, the input it saw, the agent's reasoning ('thought'), any tool
calls (name, args, output, ok, latency), and the step's structured output. This
is the raw material Part 1 scores -- we evaluate the *path*, not just the final
answer.

Two artefacts are produced (see eval/runner.py):
  - eval/trajectories/<model>/<scenario>.json  : one rich, readable run
  - eval/trajectories/trajectories.jsonl       : one run per line (for scoring)
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class ToolEvent:
    name: str
    arguments: dict[str, Any]
    ok: bool
    output: Any = None
    error: Optional[str] = None
    latency_s: float = 0.0


@dataclass
class Step:
    index: int
    node: str
    input: Any = None
    thought: str = ""
    tool_events: list[ToolEvent] = field(default_factory=list)
    output: Any = None
    llm_latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Trajectory:
    run_id: str
    scenario_id: str
    model_label: str
    provider: str
    model_id: str
    started_at: float = field(default_factory=time.time)
    steps: list[Step] = field(default_factory=list)
    outcome: str = ""          # 'rerouted' | 'human_review_needed' | 'crashed'
    final_decision: Any = None
    escalation_reason: str = ""
    error: str = ""

    # --- construction helpers ------------------------------------------------
    def new_step(self, node: str, input: Any = None) -> Step:
        step = Step(index=len(self.steps), node=node, input=input)
        self.steps.append(step)
        return step

    def record_llm(self, step: Step, resp) -> None:
        step.thought = resp.text
        step.llm_latency_s = resp.latency_s
        step.input_tokens = resp.input_tokens
        step.output_tokens = resp.output_tokens

    # --- aggregates used by the scorer/report --------------------------------
    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens for s in self.steps)

    def total_latency_s(self) -> float:
        return sum(s.llm_latency_s for s in self.steps)

    def all_tool_events(self) -> list[ToolEvent]:
        return [te for s in self.steps for te in s.tool_events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "model_label": self.model_label,
            "provider": self.provider,
            "model_id": self.model_id,
            "outcome": self.outcome,
            "final_decision": self.final_decision,
            "escalation_reason": self.escalation_reason,
            "error": self.error,
            "totals": {
                "steps": len(self.steps),
                "tokens": self.total_tokens(),
                "llm_latency_s": round(self.total_latency_s(), 3),
            },
            "steps": [self._step_dict(s) for s in self.steps],
        }

    @staticmethod
    def _step_dict(s: Step) -> dict[str, Any]:
        d = asdict(s)
        return d
