"""Offline smoke test -- exercise the whole graph + trajectory + scorer with a
deterministic fake LLM. No API key, no network. This is how the control flow
(retry, escalation, guardrails) and the scorer were validated before spending any
real API calls.

Run:  python -m eval.smoke_offline
Expect: all 5 scenarios run; the fake books naively, so the scorer *correctly*
penalises it on no_viable_option (proving the rubric punishes bad behaviour).
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.graph import build_graph          # noqa: E402
from agents.llm import LLMResponse, ToolCall  # noqa: E402
from agents.trajectory import Trajectory      # noqa: E402
from eval.score import score_trajectory       # noqa: E402


class FakeClient:
    """Deterministic stand-in: fetch options, then book the lowest-eta option.
    Intentionally ignores the policy so the scorer's penalties are observable."""

    label = "fake:deterministic"
    provider = "fake"
    model_id = "fake-1"

    def chat(self, system, conversation, tools=None, temperature=0.0, max_tokens=1024):
        last = conversation[-1]
        has_tool_result = any(t["role"] == "tool" for t in conversation)
        text = "Considering cost, eta hours and reliability against the policy cap."
        if tools and "Options Evaluation" in system:
            if not has_tool_result:
                sid = (re.search(r"(SHP-\d+)", last["text"]) or [None, "SHP-0000"])[1] \
                    if re.search(r"(SHP-\d+)", last["text"]) else "SHP-0000"
                return LLMResponse(text="Fetching options.",
                                   tool_calls=[ToolCall("t1", "get_alternative_carriers",
                                                        {"shipment_id": sid})])
            return LLMResponse(text=text, tool_calls=[])
        if tools and "Decision & Execution" in system:
            sid = re.search(r"(SHP-\d+)", last["text"]).group(1)
            opts = json.loads(re.search(r"\[.*\]", last["text"], re.S).group(0))
            best = sorted(opts, key=lambda o: o["eta_hours"])[0]
            return LLMResponse(text=f"Booking {best['carrier_id']} (lowest eta). {text}",
                               tool_calls=[ToolCall("t2", "execute_reroute",
                                                    {"shipment_id": sid, "carrier_id": best["carrier_id"]})])
        return LLMResponse(text=text, tool_calls=[])


def main():
    fake = FakeClient()
    for f in sorted(glob.glob(str(ROOT / "data" / "*.json"))):
        sc = json.load(open(f))
        traj = Trajectory(run_id="smoke", scenario_id=sc["scenario_id"],
                          model_label=fake.label, provider="fake", model_id="fake-1")
        g = build_graph(fake, sc, traj)
        try:
            g.invoke({"alert": sc["alert"], "policy": sc["policy"], "retries": {}},
                     config={"recursion_limit": 25})
        except Exception as e:  # noqa: BLE001
            traj.outcome = "crashed"
            traj.error = f"{type(e).__name__}: {e}"
        d = traj.to_dict()
        s = score_trajectory(d, sc)
        print(f"{sc['scenario_id']:<24} outcome={traj.outcome:<20} "
              f"steps={len(d['steps'])} overall={s['overall']} dims={s['dims']}")
    print("SMOKE OK")


if __name__ == "__main__":
    main()
