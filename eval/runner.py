"""Run all scenarios against one or both models and save trajectories + scores.

Usage:
    python -m eval.runner                 # runs every model that has a key
    python -m eval.runner --models claude # just Claude
    python -m eval.runner --models claude groq
    python -m eval.runner --scenario normal_reroute

Outputs:
    eval/trajectories/<model>/<scenario>.json   rich per-run trajectory
    eval/trajectories/trajectories.jsonl        one run per line (for scoring)
    eval/results.json                           per-run + aggregated scores
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Structured logging for control-flow events (retries, guardrail blocks,
# escalations are emitted by agents.nodes under the 'rerouting' logger).
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rerouting.runner")

# make repo root importable when run as a script
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.graph import build_graph          # noqa: E402
from agents.llm import build_client            # noqa: E402
from agents.trajectory import Trajectory       # noqa: E402
from eval.score import aggregate, score_trajectory  # noqa: E402

load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
TRAJ_DIR = ROOT / "eval" / "trajectories"

# Named model presets. Each -> (provider_kind, model_id, column_label).
# The default comparison is the two open models (both free on Groq).
PRESETS: dict[str, tuple[str, str | None, str]] = {
    "llama70b": ("groq", "llama-3.3-70b-versatile", "llama-3.3-70b"),
    "llama8b": ("groq", "llama-3.1-8b-instant", "llama-3.1-8b"),
    "qwen32b": ("groq", "qwen-2.5-32b", "qwen2.5-32b"),
    "claude": ("claude", None, "claude"),
    # Local open model via LM Studio. model_id=None -> uses $LMSTUDIO_MODEL.
    "lmstudio": ("lmstudio", None, "lmstudio-local"),
}
DEFAULT_MODELS = ["llama70b", "llama8b"]


def _key_for(kind: str) -> str | None:
    # None => no API key required (e.g. a local LM Studio server).
    return {"groq": "GROQ_API_KEY", "claude": "ANTHROPIC_API_KEY"}.get(kind)


def load_scenarios(only: str | None = None) -> list[dict]:
    files = sorted(glob.glob(str(DATA_DIR / "*.json")))
    scenarios = []
    for f in files:
        with open(f) as fh:
            sc = json.load(fh)
        if only and sc["scenario_id"] != only:
            continue
        scenarios.append(sc)
    return scenarios


def available_models(requested: list[str] | None) -> list[str]:
    models = requested or DEFAULT_MODELS
    usable = []
    for m in models:
        if m not in PRESETS:
            print(f"[skip] unknown model preset '{m}'. Known: {list(PRESETS)}")
            continue
        kind = PRESETS[m][0]
        key = _key_for(kind)
        if key is None or os.environ.get(key):  # None => no key needed (local)
            usable.append(m)
        else:
            print(f"[skip] model '{m}': {key} not set.")
    return usable


def run_one(client, scenario: dict) -> Trajectory:
    traj = Trajectory(
        run_id=uuid.uuid4().hex[:12],
        scenario_id=scenario["scenario_id"],
        model_label=client.label,
        provider=client.provider,
        model_id=client.model_id,
    )
    graph = build_graph(client, scenario, traj)
    initial = {"alert": scenario["alert"], "policy": scenario["policy"], "retries": {}}
    log.info("run start: model=%s scenario=%s", client.label, scenario["scenario_id"])
    try:
        graph.invoke(initial, config={"recursion_limit": 25})
        log.info("run done:  model=%s scenario=%s outcome=%s",
                 client.label, scenario["scenario_id"], traj.outcome)
    except Exception as e:  # noqa: BLE001  -- never let one run kill the batch
        traj.outcome = "crashed"
        traj.error = f"{type(e).__name__}: {e}"
        log.error("run CRASHED: model=%s scenario=%s error=%s",
                  client.label, scenario["scenario_id"], traj.error)
    return traj


def safe(label: str) -> str:
    return label.replace(":", "_").replace("/", "_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=None,
                    help="presets to run: llama70b llama8b qwen32b claude "
                         "(default: llama70b llama8b)")
    ap.add_argument("--scenario", default=None, help="run only this scenario_id")
    args = ap.parse_args()

    scenarios = load_scenarios(args.scenario)
    models = available_models(args.models)
    if not models:
        print("No usable models (no API keys). Set ANTHROPIC_API_KEY and/or GROQ_API_KEY.")
        sys.exit(1)

    TRAJ_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = TRAJ_DIR / "trajectories.jsonl"
    all_scores = []
    print(f"Running {len(scenarios)} scenarios x {len(models)} model(s): {models}\n")

    with open(jsonl_path, "w") as jsonl:
        for m in models:
            kind, model_id, label = PRESETS[m]
            client = build_client(kind, model_id=model_id, label=label)
            print(f"=== MODEL: {client.label} ===")
            (TRAJ_DIR / safe(client.label)).mkdir(parents=True, exist_ok=True)
            for sc in scenarios:
                traj = run_one(client, sc)
                d = traj.to_dict()
                out = TRAJ_DIR / safe(client.label) / f"{sc['scenario_id']}.json"
                with open(out, "w") as fh:
                    json.dump(d, fh, indent=2)
                jsonl.write(json.dumps(d) + "\n")

                sc_score = score_trajectory(d, sc)
                all_scores.append(sc_score)
                dims = sc_score["dims"]
                print(f"  {sc['scenario_id']:<24} outcome={traj.outcome:<20} "
                      f"overall={sc_score['overall']}  "
                      f"tc={dims['tool_calling']} dc={dims['decision_correctness']} "
                      f"er={dims['error_recovery']} rq={dims['reasoning_quality']}")
            print()

    summary = aggregate(all_scores)
    results = {"per_run": all_scores, "summary": summary}
    with open(ROOT / "eval" / "results.json", "w") as fh:
        json.dump(results, fh, indent=2)

    print("=== AGGREGATE SUMMARY ===")
    for model, s in summary.items():
        print(f"{model}: overall={s['overall']}  tool={s['tool_calling']} "
              f"decision={s['decision_correctness']} recovery={s['error_recovery']} "
              f"reasoning={s['reasoning_quality']}  tokens={s['total_tokens']} "
              f"latency={s['total_llm_latency_s']}s")
    print(f"\nWrote {ROOT / 'eval' / 'results.json'} and {jsonl_path}")


if __name__ == "__main__":
    main()
