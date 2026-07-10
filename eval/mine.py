"""Process mining over agent trajectories.

Treats each saved trajectory as an event log (à la van der Aalst process mining)
and discovers, per model:
  - the distinct execution PATHS actually taken (sequence of node labels) and
    their frequency,
  - the escalation rate, retry rate, and mean steps,
  - path CONFORMANCE: did the observed outcome match the scenario's expected_path?

This makes the "process mining / trajectory analytics" technique discussed in the
research report concrete and reproducible. No API calls -- it reads the committed
trajectory logs only.

Run:  python -m eval.mine
"""
from __future__ import annotations

import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _expected_outcome(scenario: dict) -> str:
    ep = scenario.get("expected_path", "")
    return "human_review_needed" if "human_review" in ep or "escalat" in ep.lower() else "rerouted"


def mine() -> dict:
    scenarios = {}
    for f in glob.glob(str(ROOT / "data" / "*.json")):
        sc = json.load(open(f))
        scenarios[sc["scenario_id"]] = sc

    by_model: dict[str, list[dict]] = defaultdict(list)
    for tf in sorted(glob.glob(str(ROOT / "eval" / "trajectories" / "*" / "*.json"))):
        traj = json.load(open(tf))
        by_model[traj["model_label"]].append(traj)

    report = {}
    for model, trajs in sorted(by_model.items()):
        paths = Counter()
        escalations = retries = conforming = 0
        total_steps = 0
        for t in trajs:
            nodes = [s["node"] for s in t.get("steps", [])]
            paths[" -> ".join(nodes)] += 1
            total_steps += len(nodes)
            # a retry = the same node appearing more than once consecutively
            retries += sum(1 for i in range(1, len(nodes)) if nodes[i] == nodes[i - 1])
            if t.get("outcome") == "human_review_needed":
                escalations += 1
            sc = scenarios.get(t["scenario_id"])
            if sc and t.get("outcome") == _expected_outcome(sc):
                conforming += 1
        n = len(trajs)
        report[model] = {
            "runs": n,
            "distinct_paths": len(paths),
            "paths": dict(paths),
            "escalation_rate": round(escalations / n, 2),
            "retry_events": retries,
            "mean_steps": round(total_steps / n, 2),
            "outcome_conformance": f"{conforming}/{n}",
        }
    return report


def main():
    rep = mine()
    for model, r in rep.items():
        print(f"\n=== {model} ===")
        print(f"  runs={r['runs']}  mean_steps={r['mean_steps']}  "
              f"escalation_rate={r['escalation_rate']}  retry_events={r['retry_events']}  "
              f"outcome_conformance={r['outcome_conformance']}")
        print(f"  distinct execution paths ({r['distinct_paths']}):")
        for path, count in sorted(r["paths"].items(), key=lambda kv: -kv[1]):
            print(f"    [{count}x] {path}")


if __name__ == "__main__":
    main()
