"""The reroute selection policy + a deterministic 'ground-truth' oracle.

The policy is intentionally explicit and simple so that (a) the Decision
agent has an unambiguous target to reason toward, and (b) the evaluator can
compute the *policy-optimal* answer independently and score whether each
model's autonomous choice was actually correct. This is what turns the
trajectory logs into real, objective numbers instead of vibes.

Policy (stated to the agent and enforced here):
  A carrier option is VIABLE iff  cost_usd <= max_cost_usd
                            AND    reliability >= min_reliability
  Among viable options, pick the one that minimises eta_hours
  (tie-break: higher reliability, then lower cost).
  If no option is viable, do NOT reroute -> escalate to human review.
"""
from __future__ import annotations

from typing import Any, Optional


def viable_options(options: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    max_cost = policy["max_cost_usd"]
    min_rel = policy["min_reliability"]
    return [
        o for o in options
        if o.get("cost_usd", float("inf")) <= max_cost
        and o.get("reliability", 0) >= min_rel
    ]


def policy_optimal(options: list[dict[str, Any]], policy: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Return the single option the policy says is best, or None if reroute
    is not warranted (no viable option)."""
    viable = viable_options(options, policy)
    if not viable:
        return None
    # minimise eta_hours; tie-break higher reliability then lower cost
    return sorted(
        viable,
        key=lambda o: (o["eta_hours"], -o.get("reliability", 0), o.get("cost_usd", 0)),
    )[0]


def policy_text(policy: dict[str, Any]) -> str:
    """Human-readable policy string injected into agent prompts."""
    return (
        f"REROUTE POLICY (hard constraints):\n"
        f"  - An option is only allowed if cost_usd <= ${policy['max_cost_usd']:,} "
        f"AND reliability >= {policy['min_reliability']}.\n"
        f"  - Objective: among allowed options, choose the one with the LOWEST "
        f"eta_hours (fastest recovery). Tie-break by higher reliability, then lower cost.\n"
        f"  - If NO option satisfies both constraints, DO NOT reroute. Escalate to "
        f"human review instead of forcing a non-compliant booking."
    )
