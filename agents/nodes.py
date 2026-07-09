"""The agent nodes.

Each node is one 'agent' in the workflow. Nodes use the LLM for the parts we
actually want to evaluate -- severity reasoning, tool selection, trade-off
analysis, and the escalate-vs-book decision -- while the graph (graph.py)
enforces control flow (retry once, then escalate). Every node appends a Step to
the run's Trajectory so the whole path is auditable.

Control flow contract (read by graph.py routers):
  state['route']    : one of {'ok','retry','escalate'} set by action nodes
  state['retries']  : per-stage retry counters (retry budget = 1)
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from .policy import policy_optimal, policy_text, viable_options
from .tools import TOOL_SCHEMAS, SimulatedCarrierNetwork, ToolError
from .trajectory import ToolEvent, Trajectory

MAX_RETRIES = 1  # retry a failed tool step once, then escalate (per spec)

_TOOL_BY_NAME = {t["name"]: t for t in TOOL_SCHEMAS}


def _run_tool(network: SimulatedCarrierNetwork, name: str, args: dict[str, Any]) -> ToolEvent:
    """Execute a (simulated) tool call defensively and return a ToolEvent."""
    t0 = time.time()
    try:
        if name == "get_alternative_carriers":
            out = network.get_alternative_carriers(shipment_id=args.get("shipment_id"))
        elif name == "execute_reroute":
            out = network.execute_reroute(
                shipment_id=args.get("shipment_id"), carrier_id=args.get("carrier_id")
            )
        else:
            raise ToolError(f"unknown_tool:{name}")
        return ToolEvent(name=name, arguments=args, ok=True, output=out, latency_s=time.time() - t0)
    except ToolError as e:
        return ToolEvent(name=name, arguments=args, ok=False, error=str(e), latency_s=time.time() - t0)


def make_nodes(llm, network: SimulatedCarrierNetwork, traj: Trajectory) -> dict[str, Callable]:
    """Build the node callables bound to a specific model + scenario + trajectory."""

    # ---------------------------------------------------------------- ingest
    def ingest(state: dict) -> dict:
        alert = state["alert"]
        step = traj.new_step("telemetry_ingestion", input=alert)
        system = (
            "You are the Telemetry Ingestion Agent in an autonomous logistics "
            "control tower. You receive a raw disruption alert for a shipment. "
            "Assess it: restate the disruption, estimate operational severity "
            "(low/medium/high) from the ETA impact and priority, and state whether "
            "an automated reroute should be attempted. Be concise (<=4 sentences)."
        )
        user = f"Raw telemetry alert (JSON):\n{json.dumps(alert, indent=2)}"
        resp = llm.chat(system, [{"role": "user", "text": user}], tools=None, max_tokens=400)
        traj.record_llm(step, resp)
        step.output = {"normalized_alert": alert, "assessment": resp.text}
        return {
            "normalized_alert": alert,
            "reasoning": {**state.get("reasoning", {}), "ingest": resp.text},
        }

    # -------------------------------------------------------------- evaluate
    def evaluate(state: dict) -> dict:
        alert = state["normalized_alert"]
        policy = state["policy"]
        retries = dict(state.get("retries", {}))
        retries["evaluate"] = retries.get("evaluate", 0) + 1
        step = traj.new_step(
            "options_evaluation",
            input={"shipment_id": alert["shipment_id"], "attempt": retries["evaluate"]},
        )
        system = (
            "You are the Options Evaluation Agent. Your job is to fetch alternative "
            "carriers for a disrupted shipment by calling the get_alternative_carriers "
            "tool, then reason about the trade-offs (cost vs ETA vs reliability) of the "
            "options returned. You MUST call the tool -- do not invent carriers.\n\n"
            + policy_text(policy)
        )
        user = (
            f"Shipment {alert['shipment_id']} is disrupted ({alert.get('event')}, "
            f"+{alert.get('eta_impact_hours')}h impact). Fetch alternative carriers now."
        )
        conv: list[dict[str, Any]] = [{"role": "user", "text": user}]
        resp = llm.chat(system, conv, tools=TOOL_SCHEMAS, max_tokens=500)
        traj.record_llm(step, resp)

        # The agent is expected to call get_alternative_carriers.
        call = next((c for c in resp.tool_calls if c.name == "get_alternative_carriers"), None)
        if call is None:
            step.output = {"error": "agent_did_not_call_get_alternative_carriers"}
            return {"route": "retry_or_escalate", "error": "no_tool_call:evaluate",
                    "stage": "evaluate", "retries": retries}

        te = _run_tool(network, call.name, call.arguments)
        step.tool_events.append(te)
        if not te.ok:
            step.output = {"error": te.error}
            return {"route": "retry_or_escalate", "error": te.error,
                    "stage": "evaluate", "retries": retries}

        options = te.output.get("carriers", [])
        if not options:
            step.output = {"options": [], "note": "no carriers returned"}
            return {"route": "retry_or_escalate", "error": "no_options_returned",
                    "stage": "evaluate", "options": [], "retries": retries}

        # Feed the tool result back and ask for a trade-off assessment.
        conv.append({"role": "assistant", "text": resp.text, "tool_calls": resp.tool_calls})
        conv.append({
            "role": "tool", "tool_call_id": call.id, "name": call.name,
            "content": json.dumps(te.output),
        })
        conv.append({"role": "user", "text": (
            "Assess these options against the policy. For each, note whether it is "
            "policy-compliant, and rank the compliant ones. Do NOT book anything yet."
        )})
        resp2 = llm.chat(system, conv, tools=TOOL_SCHEMAS, max_tokens=600)
        # merge reasoning/latency of the follow-up into the same step
        step.thought = (step.thought + "\n\n" + resp2.text).strip()
        step.llm_latency_s += resp2.latency_s
        step.input_tokens += resp2.input_tokens
        step.output_tokens += resp2.output_tokens
        step.output = {"options": options, "assessment": resp2.text}
        return {
            "options": options,
            "route": "ok",
            "error": "",
            "retries": retries,
            "reasoning": {**state.get("reasoning", {}), "evaluate": resp2.text},
        }

    # --------------------------------------------------------- decide/execute
    def decide_execute(state: dict) -> dict:
        alert = state["normalized_alert"]
        policy = state["policy"]
        options = state.get("options", [])
        retries = dict(state.get("retries", {}))
        retries["decide"] = retries.get("decide", 0) + 1
        step = traj.new_step(
            "decision_execution",
            input={"n_options": len(options), "attempt": retries["decide"]},
        )

        offered_ids = {o["carrier_id"] for o in options}
        system = (
            "You are the Decision & Execution Agent. Choose the single best carrier "
            "STRICTLY per the policy, then commit it by calling execute_reroute with "
            "that carrier_id. If -- and only if -- NO option satisfies the policy, do "
            "NOT call any tool; instead reply with the word ESCALATE and a one-line "
            "reason. Never book a non-compliant option.\n\n" + policy_text(policy)
        )
        user = (
            f"Shipment {alert['shipment_id']}. Candidate carriers:\n"
            f"{json.dumps(options, indent=2)}\n\nMake the call now."
        )
        conv: list[dict[str, Any]] = [{"role": "user", "text": user}]

        # Bounded ReAct loop: some models re-check the carrier list before acting.
        # We allow a couple of read-only get_alternative_carriers turns and then
        # require an execute_reroute call or an explicit ESCALATE. This keeps the
        # comparison about the model's *decision*, not about a single-shot harness.
        MAX_DECIDE_ITERS = 3
        last_text = ""
        for it in range(MAX_DECIDE_ITERS):
            resp = llm.chat(system, conv, tools=TOOL_SCHEMAS, max_tokens=500)
            last_text = resp.text or last_text
            if it == 0:
                traj.record_llm(step, resp)
            else:
                step.thought = (step.thought + "\n" + resp.text).strip()
                step.llm_latency_s += resp.latency_s
                step.input_tokens += resp.input_tokens
                step.output_tokens += resp.output_tokens

            exec_call = next((c for c in resp.tool_calls if c.name == "execute_reroute"), None)
            if exec_call is not None:
                # Guardrail: never book a carrier that was not offered.
                chosen_id = exec_call.arguments.get("carrier_id")
                if chosen_id not in offered_ids:
                    step.tool_events.append(ToolEvent(
                        name="execute_reroute", arguments=exec_call.arguments, ok=False,
                        error=f"hallucinated_carrier_id:{chosen_id} not in offered options",
                    ))
                    step.output = {"error": "chose carrier not in offered options"}
                    return {"route": "retry_or_escalate", "error": "invalid_carrier_id",
                            "stage": "decide", "retries": retries}
                te = _run_tool(network, "execute_reroute", exec_call.arguments)
                step.tool_events.append(te)
                if not te.ok:
                    step.output = {"error": te.error}
                    return {"route": "retry_or_escalate", "error": te.error,
                            "stage": "decide", "retries": retries}
                decision = {"chosen_carrier_id": chosen_id, "booking": te.output,
                            "rationale": last_text}
                step.output = decision
                return {"route": "ok", "chosen": decision, "error": "", "retries": retries,
                        "reasoning": {**state.get("reasoning", {}), "decide": last_text}}

            # Read-only re-check: re-serve the carrier list and loop.
            recheck = next((c for c in resp.tool_calls if c.name == "get_alternative_carriers"), None)
            if recheck is not None and it < MAX_DECIDE_ITERS - 1:
                te = _run_tool(network, "get_alternative_carriers", recheck.arguments)
                step.tool_events.append(te)
                conv.append({"role": "assistant", "text": resp.text, "tool_calls": resp.tool_calls})
                conv.append({"role": "tool", "tool_call_id": recheck.id,
                             "name": recheck.name, "content": json.dumps(te.output)})
                conv.append({"role": "user", "text": (
                    "You now have the options. Either call execute_reroute with the best "
                    "policy-compliant carrier_id, or reply ESCALATE if none is compliant."
                )})
                continue

            # No actionable tool call -> deliberate escalation / no-viable case.
            reason = resp.text or "no execute_reroute call and no compliant option"
            step.output = {"decision": "escalate", "reason": reason}
            return {"route": "escalate", "escalation_reason": f"agent_escalated: {reason[:160]}",
                    "stage": "decide", "retries": retries}

        # Loop exhausted without an execute call -> escalate rather than hang.
        step.output = {"decision": "escalate", "reason": "no decision within iteration budget"}
        return {"route": "escalate", "escalation_reason": "no_decision_within_budget",
                "stage": "decide", "retries": retries}

    # ---------------------------------------------------------------- finish
    def finalize_success(state: dict) -> dict:
        traj.outcome = "rerouted"
        traj.final_decision = state.get("chosen")
        return {"status": "rerouted"}

    def escalate(state: dict) -> dict:
        step = traj.new_step("human_review_needed", input={"stage": state.get("stage")})
        reason = state.get("escalation_reason") or state.get("error") or "unspecified"
        # A deterministic sanity note: was escalation actually the policy-correct move?
        opt = policy_optimal(state.get("options", []), state["policy"])
        note = ("policy confirms no viable option -> escalation correct"
                if opt is None else
                "NOTE: a viable option existed; escalation may be premature")
        step.output = {"escalation_reason": reason, "policy_check": note}
        traj.outcome = "human_review_needed"
        traj.escalation_reason = reason
        return {"status": "human_review_needed", "escalation_reason": reason}

    return {
        "ingest": ingest,
        "evaluate": evaluate,
        "decide_execute": decide_execute,
        "finalize_success": finalize_success,
        "escalate": escalate,
    }
