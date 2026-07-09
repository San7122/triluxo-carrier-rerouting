# Autonomous Carrier Rerouting Agent — AI Researcher Assessment

A small, legible **LangGraph** multi-agent system that autonomously reroutes a
shipment when a logistics disruption fires, plus a **trajectory-based evaluation**
comparing two open-source LLMs on the exact same graph, plus a **product strategy
deck**. Built as a timed take-home.

The use case: a telemetry alert (delay/failure) arrives → the system evaluates
alternative carriers via a (simulated) carrier API → it **autonomously executes a
reroute** against an explicit policy, with a **retry-then-escalate** safety path
when tools fail or no compliant option exists.

---

## How the three assignment parts map to this repo

| Part | Deliverable | Where |
|------|-------------|-------|
| **Part 2 — Technical POC** | LangGraph multi-agent workflow, mock tools, error recovery, trajectory logging | [`agents/`](agents/), [`data/`](data/), [`eval/runner.py`](eval/runner.py) |
| **Part 1 — Research & Model Evaluation** | Trajectory-based eval methodology, rubric, scored results, techniques survey | [`docs/research_report.md`](docs/research_report.md) |
| **Part 3 — Product Strategy Deck** | 10–14 slide pitch (PowerPoint) | [`docs/deck.pptx`](docs/deck.pptx) |
| Raw evidence | Real per-run trajectory logs + scores | [`eval/trajectories/`](eval/trajectories/), [`eval/results.json`](eval/results.json) |

---

## Architecture

```
          telemetry alert (JSON)
                   │
                   ▼
        ┌───────────────────────┐
        │ Telemetry Ingestion   │  assess severity, decide if reroute warranted
        └───────────┬───────────┘
                    ▼
        ┌───────────────────────┐   tool: get_alternative_carriers  (SIMULATED)
        │ Options Evaluation    │──────────────┐
        └───────────┬───────────┘              │ fail / empty
             ok      │                          ▼
                     ▼                    retry once ──► still failing ──►┐
        ┌───────────────────────┐   tool: execute_reroute (SIMULATED)    │
        │ Decision & Execution  │──────────────┐                         │
        └───────────┬───────────┘              │ fail                    │
             ok      │                          ▼                         │
                     ▼                    retry once ──► still failing ──►│
              ┌────────────┐                                              ▼
              │  REROUTED  │                                   ┌──────────────────────┐
              └────────────┘                                   │ HUMAN_REVIEW_NEEDED  │
                                                               └──────────────────────┘
```

Three agent nodes + a fallback/escalation path, orchestrated as an explicit
LangGraph state machine. The retry budget is **1** (retry a failed tool step
once, then escalate). Every node appends a step to a structured **trajectory
log** — the raw material the evaluation scores.

**Models compared:** `llama-3.3-70b-versatile` vs `llama-3.1-8b-instant` (both
open-source, run for real via Groq). Claude (the closed-source reference) is
discussed qualitatively — see the report for why it wasn't run here. The client
layer ([`agents/llm.py`](agents/llm.py)) is provider-agnostic, so adding Claude
is a one-line preset once an Anthropic API key is available.

---

## Setup — clone & run in under 5 minutes

```bash
# 1. From the repo root, create a venv (Python 3.11 or 3.12 recommended)
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install deps
pip install -r requirements.txt

# 3. Configure a key. Groq is free: https://console.groq.com/keys
cp .env.example .env
# edit .env and set GROQ_API_KEY=gsk_...

# 4. Run all 5 scenarios against both open models
python -m eval.runner

# (optional) run a single scenario or model
python -m eval.runner --models llama70b --scenario normal_reroute
```

Outputs after a run:
- `eval/trajectories/<model>/<scenario>.json` — one rich, readable trajectory per run
- `eval/trajectories/trajectories.jsonl` — one run per line (for scoring)
- `eval/results.json` — per-run + aggregated rubric scores

To re-score without re-calling the models, the scoring logic lives in
[`eval/score.py`](eval/score.py) and reads the saved trajectories.

### Offline sanity check (no API key)
```bash
python -m eval.smoke_offline
```
Exercises the whole graph, retry/escalation paths, guardrails, and scorer with a
deterministic fake client — no key, no network. This is how the control flow was
validated before spending any API calls. (The fake books naively, so the scorer
*correctly* penalises it on `no_viable_option` — proof the rubric punishes bad
behaviour rather than rubber-stamping.)

---

## What is real vs. simulated

Being explicit, because it matters for reading the results:

- **Real:** the LLM reasoning, tool-*calling* decisions, the LangGraph
  orchestration, the retry/escalation control flow, the trajectory logs, and the
  rubric scores.
- **Simulated (clearly marked in [`agents/tools.py`](agents/tools.py)):** the
  "carrier API" itself. `get_alternative_carriers` and `execute_reroute` return
  scripted data from each scenario's config so runs are deterministic and
  failures can be injected on demand. No real carrier network, booking system, or
  HTTP call is involved. The tool *interfaces* are shaped like the real
  integrations (a rate-shopping/TMS API and a booking/EDI transaction) so swapping
  in live clients is a localized change.

---

## AI tool decision log

*(Required by the assignment. Written in my own voice — what I directed the AI
assistant to build, what I'd review before trusting it, and the calls I made
deliberately.)*

I used **Claude Code** as a pair-programmer to scaffold and implement this repo
under time pressure. The prompts, architecture, evaluation design, and scenario
design are mine; the assistant did most of the typing and the boilerplate.

**What the assistant generated:** the LangGraph wiring, the provider-agnostic LLM
adapter, the mock tools, the trajectory logger, the scorer, and the first drafts
of the report and deck. **What I would review/adjust before shipping to
production** (and partially reviewed here): (1) the **scoring rubric thresholds** —
the objective dimensions are defensible but the exact point deductions are
judgement calls I'd calibrate against more scenarios; (2) the **reasoning-quality
heuristic**, which is a keyword proxy and needs human spot-reading (I did read
excerpts — see the report); (3) **error handling around the LLM clients**, which
I hardened after a real Groq rate-limit corrupted a run.

**Architectural decisions I made deliberately:**

1. **LangGraph over CrewAI/AutoGen** — the recovery behaviour (retry a failed
   tool exactly once, then escalate) is a control-flow requirement, not a
   conversation. An explicit state graph makes that policy auditable and makes
   per-node trajectory logging fall out for free. CrewAI's role-chat abstraction
   would have hidden exactly the intermediate steps I needed to score.
2. **A thin provider-agnostic client seam** ([`agents/llm.py`](agents/llm.py))
   rather than LangChain's model abstractions — so the *graph, prompts, tools, and
   policy are byte-for-byte identical* across models and only the client swaps.
   That symmetry is what makes the head-to-head fair.
3. **A deterministic policy oracle** ([`agents/policy.py`](agents/policy.py)) —
   the same policy the agent is asked to follow is computed independently, so
   "decision correctness" is a real, checkable number (did it pick the
   policy-optimal option / escalate correctly), not a vibe.
4. **Guardrail: never book a carrier that wasn't offered** — the execution node
   rejects hallucinated `carrier_id`s before calling the booking tool. This is
   the kind of deterministic guardrail I'd want wrapping any autonomous action in
   production, independent of which model is driving.

---

## Repo layout

```
agents/          LangGraph POC
  llm.py         provider-agnostic client (Anthropic + Groq/OpenAI-compatible)
  tools.py       SIMULATED carrier API + tool schemas
  policy.py      reroute policy + deterministic optimal-choice oracle
  nodes.py       the agent nodes (ingest / evaluate / decide+execute / escalate)
  graph.py       LangGraph assembly + retry/escalation routers
  trajectory.py  structured trajectory logging
data/            5 test scenarios (normal, tight-margin, no-viable, transient-fail, hard-fail)
eval/
  runner.py      runs all scenarios x models, saves trajectories
  score.py       trajectory-based rubric scoring
  trajectories/  real per-run logs
  results.json   scored results
docs/
  research_report.md   Part 1
  deck.pptx            Part 3 (11 slides, regenerate with: python docs/build_deck.py)
  build_deck.py        deck generator (built with python-pptx; the referenced
                       /mnt pptx skill was unavailable in this environment)
```

## Results at a glance

From the real run (`eval/results.json`): **Llama 3.3 70B = 5.0/5.0 overall**,
**Llama 3.1 8B = 4.17/5.0**. The 8B is ~27% faster but, on the no-viable-option
case, booked a carrier that violated the policy on both cost and reliability
instead of escalating — a safety failure that only trajectory (not outcome-only)
scoring reveals. Full analysis in [`docs/research_report.md`](docs/research_report.md).
