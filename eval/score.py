"""Trajectory-based scoring.

We score the PATH, not just the final answer, on four dimensions (1-5). Three of
them are computed deterministically from the trajectory + the policy oracle, so
the numbers in the report are real and reproducible:

  1. tool_calling        - right tools, valid args, no hallucinated carrier ids
  2. decision_correctness- chose the policy-optimal option / escalated correctly
  3. error_recovery      - retried then escalated sensibly (only scored on
                           scenarios that actually induce a failure/dead-end)
  4. reasoning_quality   - HEURISTIC proxy: did the reasoning engage the real
                           trade-off axes (cost / eta / reliability / policy)?
                           Supplemented by manual reading of excerpts in the report.

Ground truth for each scenario is derived from its own simulation config, so
adding a scenario needs no changes here.
"""
from __future__ import annotations

from typing import Any, Optional

from agents.policy import policy_optimal


def _expected(scenario: dict) -> dict:
    """Derive the correct outcome for a scenario from its config + policy."""
    carriers = scenario["simulation"]["get_alternative_carriers"].get("carriers", [])
    get_mode = scenario["simulation"]["get_alternative_carriers"].get("mode", "return")
    exec_mode = scenario["simulation"].get("execute_reroute", {}).get("mode", "succeed")
    policy = scenario["policy"]
    optimal = policy_optimal(carriers, policy)

    # If no viable option OR booking can never succeed -> escalate is correct.
    bookable = optimal is not None and exec_mode != "always_fail"
    return {
        "optimal_carrier": optimal["carrier_id"] if optimal else None,
        "expected_outcome": "rerouted" if bookable else "human_review_needed",
        "no_viable": optimal is None,
        "induces_failure": (get_mode != "return") or (exec_mode != "succeed") or (optimal is None),
        "recoverable_failure": get_mode == "error_then_return" or exec_mode == "fail_then_succeed",
        "viable_ids": {o["carrier_id"] for o in carriers
                       if o.get("cost_usd", 1e9) <= policy["max_cost_usd"]
                       and o.get("reliability", 0) >= policy["min_reliability"]},
    }


def _clamp(x: int) -> int:
    return max(1, min(5, x))


def score_trajectory(traj: dict, scenario: dict) -> dict[str, Any]:
    exp = _expected(scenario)
    steps = traj.get("steps", [])
    tool_events = [te for s in steps for te in s.get("tool_events", [])]
    outcome = traj.get("outcome")

    got_calls = [te for te in tool_events if te["name"] == "get_alternative_carriers"]
    exec_calls = [te for te in tool_events if te["name"] == "execute_reroute"]
    hallucinated = [te for te in exec_calls if (te.get("error") or "").startswith("hallucinated")]
    shipment_id = scenario["alert"]["shipment_id"]

    chosen_carrier = None
    if traj.get("final_decision"):
        chosen_carrier = traj["final_decision"].get("chosen_carrier_id")

    # ---- 1. tool_calling ----------------------------------------------------
    tc = 5
    if not got_calls:
        tc -= 2  # never fetched options
    elif any(te["arguments"].get("shipment_id") != shipment_id for te in got_calls):
        tc -= 1  # fetched with wrong id
    if hallucinated:
        tc -= 2
    if exp["no_viable"] and any(te["ok"] for te in exec_calls):
        tc -= 3  # booked despite no compliant option
    if not exp["no_viable"] and exp["expected_outcome"] == "rerouted" and not any(te["ok"] for te in exec_calls):
        tc -= 1  # should have successfully booked but never did
    tool_calling = _clamp(tc)

    # ---- 2. decision_correctness -------------------------------------------
    if exp["no_viable"]:
        dc = 5 if outcome == "human_review_needed" else 1
    elif exp["expected_outcome"] == "human_review_needed":  # viable exists but booking impossible
        # correct = attempted the optimal carrier, then escalated on hard failure
        attempted_optimal = any(te["arguments"].get("carrier_id") == exp["optimal_carrier"] for te in exec_calls)
        if outcome == "human_review_needed" and attempted_optimal:
            dc = 5
        elif outcome == "human_review_needed":
            dc = 4  # escalated correctly but tried a non-optimal (still compliant) carrier
        else:
            dc = 1
    else:  # expected a successful booking
        if outcome != "rerouted":
            dc = 2  # escalated when it should have booked
        elif chosen_carrier == exp["optimal_carrier"]:
            dc = 5
        elif chosen_carrier in exp["viable_ids"]:
            dc = 3  # booked a compliant but sub-optimal option
        else:
            dc = 1  # booked a non-compliant option
    decision_correctness = dc

    # ---- 3. error_recovery (only where a failure/dead-end is induced) -------
    error_recovery: Optional[int] = None
    if exp["induces_failure"]:
        failed_tool_events = [te for te in tool_events if not te["ok"]]
        if exp["no_viable"]:
            error_recovery = 5 if outcome == "human_review_needed" else 1
        elif exp["recoverable_failure"]:
            # should retry and recover to the expected outcome
            if outcome == exp["expected_outcome"] and failed_tool_events:
                error_recovery = 5
            elif outcome == exp["expected_outcome"]:
                error_recovery = 4
            else:
                error_recovery = 2  # gave up / mishandled a recoverable failure
        else:  # hard failure -> retry once then escalate
            if outcome == "human_review_needed" and len(exec_calls) >= 2:
                error_recovery = 5  # retried then escalated
            elif outcome == "human_review_needed":
                error_recovery = 3  # escalated but without the expected retry
            else:
                error_recovery = 1  # faked success / mishandled

    # ---- 4. reasoning_quality (heuristic proxy) ----------------------------
    text = " ".join(
        (s.get("thought") or "") + " " +
        (str(s.get("output", "")) if isinstance(s.get("output"), str) else "")
        for s in steps
    ).lower()
    signals = 0
    signals += 1 if "cost" in text or "$" in text else 0
    signals += 1 if ("eta" in text or "hour" in text or "faster" in text or "time" in text) else 0
    signals += 1 if "reliab" in text else 0
    signals += 1 if ("polic" in text or "complian" in text or "constraint" in text or "cap" in text) else 0
    reasoning_quality = _clamp(1 + signals)

    dims = {
        "tool_calling": tool_calling,
        "decision_correctness": decision_correctness,
        "error_recovery": error_recovery,
        "reasoning_quality": reasoning_quality,
    }
    scored = [v for v in dims.values() if v is not None]
    overall = round(sum(scored) / len(scored), 2)

    return {
        "scenario_id": traj.get("scenario_id"),
        "model_label": traj.get("model_label"),
        "outcome": outcome,
        "expected_outcome": exp["expected_outcome"],
        "chosen_carrier": chosen_carrier,
        "optimal_carrier": exp["optimal_carrier"],
        "dims": dims,
        "overall": overall,
        "totals": traj.get("totals", {}),
    }


def aggregate(scores: list[dict]) -> dict[str, Any]:
    """Aggregate per-model averages across scenarios."""
    by_model: dict[str, list[dict]] = {}
    for s in scores:
        by_model.setdefault(s["model_label"], []).append(s)

    summary = {}
    for model, rows in by_model.items():
        def avg(key):
            vals = [r["dims"][key] for r in rows if r["dims"][key] is not None]
            return round(sum(vals) / len(vals), 2) if vals else None
        summary[model] = {
            "tool_calling": avg("tool_calling"),
            "decision_correctness": avg("decision_correctness"),
            "error_recovery": avg("error_recovery"),
            "reasoning_quality": avg("reasoning_quality"),
            "overall": round(sum(r["overall"] for r in rows) / len(rows), 2),
            "total_tokens": sum(r["totals"].get("tokens", 0) for r in rows),
            "total_llm_latency_s": round(sum(r["totals"].get("llm_latency_s", 0) for r in rows), 2),
            "n_scenarios": len(rows),
        }
    return summary
