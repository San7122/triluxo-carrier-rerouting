"""LangGraph assembly.

Why LangGraph: the workflow is a small state machine with a non-trivial control
path (retry a failed tool step exactly once, then escalate to a human). Modelling
that as an explicit graph -- rather than an implicit ReAct loop -- makes the
recovery policy auditable and makes trajectory logging trivial: each node is a
labelled step.

    ingest -> evaluate --ok--> decide_execute --ok--> finalize_success -> END
                 |  \\                  |  \\
             retry  escalate       retry  escalate
                 |      \\              |      \\
              (evaluate) escalate   (decide)  escalate -> END

Routers enforce the retry budget (agents.nodes.MAX_RETRIES = 1).
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .nodes import MAX_RETRIES, make_nodes
from .tools import SimulatedCarrierNetwork
from .trajectory import Trajectory


class RerouteState(TypedDict, total=False):
    # inputs
    alert: dict[str, Any]
    policy: dict[str, Any]
    # working memory
    normalized_alert: dict[str, Any]
    reasoning: dict[str, str]
    options: list[dict[str, Any]]
    chosen: dict[str, Any]
    # control
    route: str            # 'ok' | 'retry_or_escalate' | 'escalate'
    error: str
    stage: str
    retries: dict[str, int]
    escalation_reason: str
    status: str           # 'rerouted' | 'human_review_needed'


def _route_after_evaluate(state: RerouteState) -> str:
    if state.get("route") == "ok":
        return "decide_execute"
    # failure: retry until budget exhausted, then escalate
    attempts = state.get("retries", {}).get("evaluate", 0)
    return "evaluate" if attempts <= MAX_RETRIES else "escalate"


def _route_after_decide(state: RerouteState) -> str:
    route = state.get("route")
    if route == "ok":
        return "finalize_success"
    if route == "escalate":            # agent deliberately escalated (no viable option)
        return "escalate"
    attempts = state.get("retries", {}).get("decide", 0)
    return "decide_execute" if attempts <= MAX_RETRIES else "escalate"


def build_graph(llm, scenario: dict[str, Any], traj: Trajectory):
    """Compile a run-ready graph bound to a model + scenario + trajectory logger."""
    network = SimulatedCarrierNetwork(sim=scenario.get("simulation", {}))
    nodes = make_nodes(llm, network, traj)

    g = StateGraph(RerouteState)
    for name, fn in nodes.items():
        g.add_node(name, fn)

    g.set_entry_point("ingest")
    g.add_edge("ingest", "evaluate")
    g.add_conditional_edges("evaluate", _route_after_evaluate,
                            {"decide_execute": "decide_execute", "evaluate": "evaluate",
                             "escalate": "escalate"})
    g.add_conditional_edges("decide_execute", _route_after_decide,
                            {"finalize_success": "finalize_success",
                             "decide_execute": "decide_execute", "escalate": "escalate"})
    g.add_edge("finalize_success", END)
    g.add_edge("escalate", END)
    return g.compile()
