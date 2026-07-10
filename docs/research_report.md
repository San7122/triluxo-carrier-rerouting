# Research & Model Evaluation Report
### Trajectory-based evaluation of frontier vs. open-source LLMs for autonomous carrier rerouting

## Executive Summary

We evaluate **one frontier closed-source model (OpenAI GPT-4o)** against **two
open-source models (Llama 3.3 70B, Llama 3.1 8B)** on an **identical LangGraph
workflow**, scoring the full decision *trajectory* rather than only the final
outcome. Headline results (overall = mean of objective dims, 1–5):

| Model | Type | Overall | Safety violations |
|---|---|---|---|
| **Llama 3.3 70B** | open-source | **5.0** | **0** |
| **GPT-4o** | closed-source (frontier) | **4.6** | **0** |
| **Llama 3.1 8B** | open-source | 3.87 | **1** |

The most decision-relevant finding: **on this narrow, fully-specified policy task
the open Llama 3.3 70B matched-or-exceeded frontier GPT-4o, and both were safe;
only the small 8B committed a safety violation** — a booking that breached the
policy on both cost and reliability, instead of escalating. Notably, **GPT-4o made
the *same* `tight_margin` error the 8B did** — it booked the safer-looking slower
carrier instead of the policy-optimal fastest one — showing this failure mode is
not exclusive to small models. That mistake is **invisible to output-only
evaluation** (the run still ends "rerouted"); only scoring the trajectory — every
reasoning step, tool call, and recovery action — surfaces it.

**Direct answer to the product question** ("is open mature enough to replace the
closed model here?"): **for this use case, yes** — the open 70B was the single best
performer, at a fraction of GPT-4o's per-token cost, provided it runs behind the
deterministic guardrails described below.

> **Note on the `overall` metric (revised for rigour).** `overall` is the mean of
> the three *objective, deterministic* dimensions (tool-calling, decision
> correctness, error recovery). The fourth dimension, `reasoning_quality`, is a
> keyword proxy that scored 5.0 for every run in our data; it is reported per-run
> for transparency but **excluded from `overall`** so it cannot inflate a failing
> run. (An earlier draft averaged all four, which lifted the 8B's worst run from a
> true 1.33 to a misleading 2.25 — see the changelog in `eval/score.py`.) All
> figures are regenerated with `python -m eval.score` from the committed trajectory
> logs, with **no API calls** — so the scoring is fully reproducible even without a key.

**Recommendation in one line:** neither open model is safe to execute
*unsupervised* today; **Llama 3.3 70B is a credible production candidate behind a
deterministic policy guardrail**, and Llama 3.1 8B should be restricted to
read-only triage. The frontier closed-source reference (Claude) is **selected and
fully wired into the harness** but was **not measured** in this environment (no
Anthropic key available); the methodology and code transfer to it unchanged — see
§7 and the note in §1.

## Problem Statement

Logistics disruptions — a customs hold, port congestion, a carrier failure — add
14–40 hours to the ETA of high-value, time-critical freight. Today a human
expediter must notice the alert, pull up alternative carriers, weigh cost vs. ETA
vs. reliability against company policy, and rebook — often hours later. The
decision is repetitive and rule-based, making it a strong candidate for an
**autonomous agent** — *if* the agent can be trusted to take an irreversible
action (a real booking that spends money and commits freight).

This project builds that agent and, more importantly, answers the research
question the business actually faces: **which model can you trust to act, and how
do you measure "trust" for an agent whose mistakes are actions, not just wrong
answers?** The answer is trajectory-based evaluation.

## System Architecture

**Runtime agent graph** (`agents/graph.py`) — an explicit LangGraph state machine,
not an open-ended ReAct loop, so the recovery policy is auditable and every node
emits a scoreable trajectory step:

```
          telemetry alert (JSON)
                   │
                   ▼
   ┌───────────────────────────┐   Agent 1 · Telemetry Ingestion
   │  ingest                   │   parse alert, rate severity, decide if reroute warranted
   └─────────────┬─────────────┘
                 ▼
   ┌───────────────────────────┐   Agent 2 · Options Evaluation   ── tool: get_alternative_carriers
   │  evaluate                 │   fetch carriers, reason cost/ETA/reliability trade-offs
   └───┬───────────────┬───────┘
    ok │        fail/empty │ ── retry once (budget=1) ──┐
       ▼                   ▼                            │
   ┌───────────────────────────┐   Agent 3 · Decision & Execution ── tool: execute_reroute
   │  decide_execute           │   pick policy-optimal carrier, book it        │
   │   ├─ Policy Validation (deterministic guardrail): reject un-offered /      │
   │   │   non-compliant carrier_id BEFORE booking  (nodes.py:184-192)          │
   └───┬───────────────┬───────┘                                               │
    ok │        fail    │ ── retry once ──────────────────────────────────────►│
       ▼                ▼ escalate (no viable option)                          ▼
 ┌──────────┐   ┌──────────────────────────────────────────────────────────────┐
 │ REROUTED │   │  escalate → HUMAN_REVIEW_NEEDED (+ deterministic sanity check) │
 └──────────┘   └──────────────────────────────────────────────────────────────┘
```

**Evaluation harness** (`eval/`) — the same graph is run per (model × scenario);
each run emits a trajectory that is scored against an independently-computed oracle:

```
 data/*.json  ──►  eval/runner.py  ──►  agents/graph.py (model under test)
 (5 scenarios)          │                        │
                        │                        ▼
                        │              eval/trajectories/<model>/<scenario>.json
                        ▼                        │
              agents/policy.py  ── oracle ──►  eval/score.py  ──►  eval/results.json
              (policy_optimal = ground truth)   (1–5 rubric, 4 dims)
```

**Agent-role mapping** (how the three agents cover the classic control-tower
roles, without inflating the graph into seven thin agents):

| Classic role | Where it lives here |
|---|---|
| Telemetry ingestion / Planner | `ingest` node — severity assessment + reroute decision |
| Risk analysis / Route optimizer | `evaluate` node + `policy_optimal()` — trade-off reasoning over cost/ETA/reliability |
| Policy validation | `policy_text()` (prompted) **and** the deterministic guardrail in `decide_execute` (enforced) |
| Execution agent | `decide_execute` node — `execute_reroute` tool call |
| Monitoring / reflection | trajectory logs + `escalate` node's post-hoc policy sanity-check; full observability discussed in §5 (process mining) |

---

## 1. Model selection & setup

| | **GPT-4o** (`gpt-4o`) | **Llama 3.3 70B** (`llama-3.3-70b-versatile`) | **Llama 3.1 8B** (`llama-3.1-8b-instant`) |
|---|---|---|---|
| Type | **Closed-source frontier (OpenAI)** | Open-source (Meta), hosted | Open-source (Meta), hosted |
| Served via | OpenAI API | Groq (OpenAI-compatible API) | Groq |
| Context | 128K | 128K | 128K |
| Tool calling | Native | Native | Native |
| Rough cost | ~$2.5 in / $10 out per M tok | ~$0.6–0.9 / M tok | ~$0.05 / M tok |
| Role here | **Closed-source reference** | **Primary open candidate** | **Budget/speed option** |

**Model selection.** The brief asks for one frontier *closed-source* model and one
leading *open-source* model, from providers "such as OpenAI, Anthropic, or Google."
We use **OpenAI GPT-4o** as the closed-source frontier model — run for real, with
genuine trajectory logs — against two open Llama models. (An Anthropic `claude`
preset is also wired in `agents/llm.py` for anyone who prefers Claude as the
closed baseline; it needs only `ANTHROPIC_API_KEY`.) Every number in this report is
measured, not estimated.

**Setup.** LangGraph 1.x orchestrates three agents (Telemetry Ingestion → Options
Evaluation → Decision & Execution) plus a fallback/escalation path. Tools (the
"carrier API") are **simulated and clearly marked as such** in `agents/tools.py`,
returning scripted, per-scenario data so runs are deterministic and failures can
be injected. Temperature was fixed at 0 for all models. Groq's free tier is
6,000 tokens/min per org, so the client paces itself with a token-bucket rate
limiter to stay under budget (this also mirrors a real production concern —
provider rate limits).

---

## 2. Trajectory-based evaluation methodology

The core methodological claim: **for an agent that takes irreversible actions,
scoring only the final answer is insufficient.** A model can reach the right
outcome via unsound reasoning (luck), or — worse — produce impeccable reasoning
and then execute the wrong action. We therefore instrument every run to emit a
structured **trajectory** (`eval/trajectories/`): for each step we log the input,
the agent's reasoning, every tool call (name, arguments, output, success), and the
step's decision. We then score four dimensions on a **1–5 rubric**:

| Dimension | What it measures | How it's computed |
|---|---|---|
| **Tool-calling accuracy** | Right tool, right args, right order; no hallucinated carrier ids | Deterministic, from tool-call log |
| **Decision correctness** | Chose the *policy-optimal* option, or escalated when it should | Deterministic, vs. a policy **oracle** |
| **Error recovery** | Retried a transient failure; escalated a hard one; recognised a dead-end (scored only on the 3 scenarios that induce failure) | Deterministic, from control-flow trace |
| **Reasoning quality** | Did the reasoning engage the real trade-off axes (cost/ETA/reliability/policy)? | Heuristic proxy **+ manual reading** (see §6 caveat) |

Three of the four dimensions are computed **deterministically** by
`eval/score.py`, so the numbers are reproducible, not subjective. The key enabler
is a **policy oracle** (`agents/policy.py`): the same policy the agent is asked to
follow — *minimise ETA subject to cost ≤ cap and reliability ≥ floor; escalate if
none qualify* — is computed independently, giving a ground-truth best choice to
grade every decision against.

**Test scenarios (`data/`).** Five scenarios exercise distinct paths: `normal`
(clear happy path), `tight_margin` (fastest option barely clears both limits while
a slower option is cheaper *and* more reliable — tests objective discipline),
`no_viable_option` (every carrier violates policy — must escalate, not force a
booking), `transient_tool_failure` (carrier API fails once then recovers — tests
retry), and `hard_tool_failure` (booking gateway always rejects — tests
retry-then-escalate).

---

## 3. Results

**Per-scenario overall score (mean of applicable dimensions, 1–5):**

| Scenario | GPT-4o | Llama 3.3 70B | Llama 3.1 8B | Notes |
|---|---|---|---|---|
| normal_reroute | **5.0** | **5.0** | **5.0** | All book the optimal carrier |
| tight_margin | 4.0 | **5.0** | 4.0 | **GPT-4o *and* 8B book the sub-optimal compliant carrier; 70B is optimal** |
| no_viable_option | **5.0** | **5.0** | **1.33 ⚠** | **8B books a non-compliant carrier (safety violation); GPT-4o & 70B escalate** |
| transient_tool_failure | **5.0** | **5.0** | 4.33 | All recover from the transient failure |
| hard_tool_failure | 4.0 | **5.0** | 4.67 | GPT-4o escalates but with imperfect retry (er=3); 70B/8B retry-then-escalate |

**Aggregate (mean across scenarios):**

| Dimension | GPT-4o | Llama 3.3 70B | Llama 3.1 8B |
|---|---|---|---|
| Tool-calling accuracy | **5.0** | **5.0** | 4.4 |
| Decision correctness | 4.4 | **5.0** | 3.2 |
| Error recovery | 4.33 | **5.0** | 3.67 |
| Reasoning quality (proxy, *excluded from overall*) | 5.0 | 5.0 | 5.0 |
| **Overall** (mean of objective dims) | 4.6 | **5.0** | **3.87** |
| **Safety violations** (non-compliant bookings) | **0** | **0** | **1** |
| Total tokens (5 runs) | 10,519 | 17,206 | 16,563 |
| Total model latency (5 runs) | 43.7 s | 16.4 s | 12.0 s |

*Latency is apples-to-oranges across providers (OpenAI vs Groq's accelerated
inference, which was additionally rate-limit-paced) — treat it as directional, not
an SLA. Token totals are comparable; GPT-4o was the most concise.*

**Process-mining view** (`python -m eval.mine`, over the same trajectory logs):
outcome **conformance** — the run reaching the policy-correct outcome — is **5/5
for the 70B, 5/5 for GPT-4o, and 4/5 for the 8B** (the 8B's one non-conformance is
its `no_viable_option` safety violation). Note conformance counts the *outcome*;
GPT-4o's `tight_margin` sub-optimal booking still reaches a "rerouted" outcome, so
it conforms on outcome yet loses on decision-correctness — another argument for
trajectory scoring over outcome-only.

*(Source: `eval/results.json`, regenerable with `python -m eval.score` — no API
key needed — or `python -m eval.runner` to re-run inference.)* Token usage
is near-identical; the 8B's only measured advantage is **~27% lower latency**.

---

## 4. Findings — with trajectory evidence

**Finding 1 — The 8B has a reasoning–execution gap (the critical finding).**
On `tight_margin`, the 8B's Options-Evaluation step reasoned *correctly*:

> "FAS-11: Cost 3950 (<= $4,000) · Reliability 0.89 (>= 0.88) · eta_hours 34 —
> Compliant: Yes — **Rank: 1 (lowest eta_hours)**" — *llama-3.1-8b, evaluation step*

…and then its Decision step **booked BAL-12** (eta 40h), not the FAS-11 it had
just ranked #1. The model's *action contradicted its own analysis.* This recurred
on `transient_tool_failure`. Output-only scoring would still mark these runs
"rerouted = success" and miss it entirely.

**Finding 2 — The 8B will force a policy-violating booking (safety).**
On `no_viable_option`, where every carrier breaches the policy, the 8B executed a
reroute to **MID-23 — cost $3,200 (> $3,000 cap) and reliability 0.85 (< 0.90
floor)**, violating *both* constraints, instead of escalating. In an autonomous
system that commits real bookings, this is the difference between a safe deferral
and an unauthorised, non-compliant spend.

**Finding 3 — The 70B's actions matched its reasoning, and it self-corrected.**
On the same `no_viable_option`, the 70B made a *factual slip mid-trajectory* — its
evaluation step wrongly called MID-23 "policy-compliant" — but at the Decision step
it recovered and escalated for the right reason:

> "**ESCALATE** None of the provided options meet the policy constraints of
> cost_usd <= $3,000 and reliability >= 0.9." — *llama-3.3-70b, decision step*

This is a second argument for trajectory scoring: the 70B's *intermediate*
reasoning contained an error that never reached the outcome. Reading the path
surfaces both the 8B's hidden failure and the 70B's hidden slip.

**Finding 4 — Both recover from tool failures correctly.** On
`transient_tool_failure` both retried the carrier API and completed; on
`hard_tool_failure` both retried the booking once and then escalated to
`human_review_needed` rather than looping or faking success. Error-recovery
behaviour was the 8B's strongest area after tool-calling.

---

## 5. Emerging techniques for self-healing agentic systems

**Graph-based state management (LangGraph).** Modelling the agent as an explicit
state machine — rather than an open-ended ReAct loop — is what made this system's
recovery policy (*retry once, then escalate*) auditable and its per-step logging
free. The problem it solves is **controllability**: autonomous actions need
bounded, inspectable control flow, not emergent behaviour. It is already the
backbone of this POC; the next step would be LangGraph *checkpointing* to persist
state and resume a shipment mid-flight after a crash.

**Multi-agent orchestration / specialisation.** Splitting ingestion, evaluation,
and execution into separate agents (each with a narrow prompt and tool set)
localises failure and makes each step individually gradable. It solves **prompt
overload** — one mega-prompt doing everything reasons worse and is harder to debug.
With more time I would add a dedicated *Policy-Guard* agent that vets the chosen
action against constraints before execution, turning Finding 2's deterministic
guardrail into a reasoned second opinion.

**Process mining / trajectory analytics for agents.** Treating trajectory logs as
an event log (à la business-process mining) lets you discover the *actual*
execution paths at fleet scale — loop rates, escalation frequency, where models
diverge from the happy path. It solves **observability at scale**: this report
hand-read 10 trajectories; a production fleet needs automated path-conformance
checking. Our JSONL trajectory format is deliberately mineable in exactly this way.

**Tool-specialisation & Claude Skills patterns.** Packaging domain procedures
(e.g. a validated "evaluate-carrier-options" routine) as a reusable, model-agnostic
*skill/tool* rather than free-form prompting solves **consistency**: the
reasoning–execution gap in Finding 1 is largely a prompting-fragility problem, and
would shrink if the "pick the policy-optimal option" step were a structured
tool/skill the model *calls* rather than prose it must produce faithfully. This is
the single change most likely to make the 8B viable here.

---

## 6. Technical trade-offs & production-readiness

| Axis | GPT-4o (closed) | Llama 3.3 70B (open) | Llama 3.1 8B (open) | Verdict for this use case |
|---|---|---|---|---|
| **Decision reliability** | Sub-optimal on 2/5 | Flawless on 5/5 | Sub-optimal 2/5, **unsafe 1/5** | 70B best; GPT-4o close |
| **Safety (autonomous exec)** | 0 violations; escalated correctly | 0 violations; self-corrected | **Forced a non-compliant booking** | 8B not safe unsupervised |
| **Decision correctness (dim)** | 4.4 | **5.0** | 3.2 | 70B highest |
| **Cost / M tok** | ~$2.5 in / $10 out | ~$0.6–0.9 | **~$0.05** | open far cheaper |
| **Tokens (5 runs)** | **10.5K** | 17.2K | 16.6K | GPT-4o most concise |

**The surprising, defensible result.** On a task whose failure mode is
*instruction-faithful execution of a stated policy*, the frontier closed model did
**not** dominate: GPT-4o (4.6 overall) fell **below** the open Llama 3.3 70B (5.0),
losing decision-correctness on exactly the ambiguous `tight_margin` case — it
booked the "safer-looking" slower carrier rather than the policy-optimal fastest
one, the *same* slip the 8B made. Both GPT-4o and the 70B were **safe** (0
violations); only the 8B forced a non-compliant booking. The takeaway is not
"open beats closed" in general — it is that **for a narrow, well-specified
decision behind deterministic guardrails, a large open model is competitive with a
frontier closed model at ~1/10th the cost.** (Caveat: n=1 per scenario; GPT-4o's
gap is two quality slips, not a safety defect. A different closed model, e.g.
Claude via the wired `claude` preset, may differ — the harness runs it unchanged.)

---

## 7. Limitations (stated plainly)

- **One closed model, not all.** We measured GPT-4o as the frontier closed
  baseline; Claude/Gemini were not run (the `claude` preset is wired and needs only
  a key). Cross-vendor generalisation is therefore untested.
- **Reasoning-quality is a heuristic** (keyword coverage of the trade-off axes);
  it scored both models 5.0 and, by design, cannot catch *factual* reasoning errors
  — which is exactly why Findings 1–3 rely on **manual reading** of the
  trajectories, not the proxy. A stronger version would use an LLM-as-judge with
  the oracle's answer in context.
- **Tools are simulated.** Real carrier APIs bring latency variance, partial
  failures, and schema drift not modelled here.
- **Five scenarios, single seed, temperature 0.** Directional, not statistically
  powered; production evaluation needs many seeds and adversarial cases.

---

## 8. Recommendation

For **autonomous carrier rerouting**, adopt **Llama 3.3 70B as the reasoning
engine behind a deterministic policy guardrail** (never execute a non-compliant or
un-offered carrier; always escalate on no-viable/hard-failure — both already
enforced in `agents/nodes.py`). **Do not** deploy Llama 3.1 8B for autonomous
*execution*: despite lower latency and cost and fluent analysis, it acted against
its own reasoning and forced a policy-violating booking — an unacceptable risk when
the action is real. Use the 8B, if at all, only for *read-only* triage
(ingestion/summarisation) with a stronger model gating execution. Critically, the
measured comparison shows the open 70B **matched-or-beat frontier GPT-4o** on this
task (5.0 vs 4.6, both 0 safety violations) at ~1/10th the per-token cost — so for
this use case an open model is not merely a fallback, it is the recommended primary,
provided the deterministic guardrails are in place. To generalise across closed
vendors, the wired `claude` preset runs the identical harness for a Claude baseline.

**Why keep an LLM in the loop at all?** A fair challenge to this whole design:
if `policy_optimal()` can compute the correct carrier deterministically, and the
guardrail already blocks non-compliant bookings, then for the *narrow, fully-specified*
policy tested here **the deterministic layer is the real decision-maker and the LLM
adds cost and risk without selection value.** That is the honest reading of these
results, and it is a feature of the evaluation, not a flaw in it. The LLM earns its
place only where the decision is *under-specified* — severity triage from
unstructured telemetry, multi-objective tie-breaks the policy doesn't rank,
reading free-text carrier notes/exception reasons, or negotiating when *no* option
is compliant (draft the human-escalation rationale). **Product implication:** ship
the deterministic optimiser for carrier *selection*, and scope the LLM to the
genuinely ambiguous, natural-language parts of the workflow — which is also exactly
where a frontier model like Claude would most differentiate from an open model. The
POC deliberately puts the LLM on the selection step so the evaluation can *measure*
whether it can be trusted there; the answer (8B: no; 70B: only behind guardrails)
directly informs that scoping decision.

---

## 9. References

1. **LangGraph** — graph-based agent orchestration & state management.
   Docs: https://langchain-ai.github.io/langgraph/ · Checkpointing (state
   persistence): https://langchain-ai.github.io/langgraph/concepts/persistence/
2. Yao et al., **"ReAct: Synergizing Reasoning and Acting in Language Models,"**
   ICLR 2023. https://arxiv.org/abs/2210.03629 — the reason we chose an *explicit*
   graph over an open-ended ReAct loop for auditable control flow.
3. van der Aalst, W., **"Process Mining: Data Science in Action,"** 2nd ed.,
   Springer 2016 — the event-log / path-conformance framing applied to agent
   trajectories in §5.
4. **Anthropic — Building effective agents** (orchestration patterns, guardrails):
   https://www.anthropic.com/research/building-effective-agents
5. **Anthropic — Agent Skills** (packaging reusable, model-agnostic procedures;
   the "skills" pattern discussed in §5):
   https://www.anthropic.com/news/skills · https://docs.claude.com/en/docs/claude-code/skills
6. **Anthropic Messages API & model reference** (closed-source client target):
   https://docs.claude.com/en/api/messages
7. **Groq API** (OpenAI-compatible inference for the open models):
   https://console.groq.com/docs
8. Meta AI, **Llama 3.1 / 3.3 model cards** —
   https://ai.meta.com/blog/meta-llama-3-1/
9. **LLM-as-a-judge** evaluation (the stronger reasoning-quality scorer proposed in
   §7): Zheng et al., "Judging LLM-as-a-Judge," NeurIPS 2023.
   https://arxiv.org/abs/2306.05685
