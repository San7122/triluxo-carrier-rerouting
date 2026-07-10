# Video Narration Script — Autonomous Carrier Rerouting

**Companion to `docs/deck.pdf` (14 slides). Target length: ~15 minutes.**
Every claim here matches the repository (`eval/results.json`, `agents/`, `eval/`).
Speak in first person, calm and confident. `SAY:` = read aloud. `[SCREEN]` = what to show / do.

**Delivery tips**
- Pace ~140 words/min. Pause 1 second at each `//`.
- Advance the slide at each new numbered section.
- Numbers are your credibility — say them clearly and don't rush them.
- Total spoken words ≈ 2,100 → ~15 minutes with natural pauses.

---

## Slide 1 — Title  *(~0:45)*

[SCREEN: Title slide]

SAY:
Hi — I'm Sanjana. // In the next fifteen minutes I'll walk you through an autonomous
carrier-rerouting agent I built for the AI Researcher assignment. //
The one-line version: when a shipment is disrupted, this system reroutes it to a
better carrier automatically — and, just as importantly, it knows when *not* to act
and to escalate to a human instead. //
But the real contribution isn't the agent. It's how I *evaluated* it — I scored the
model's decision-making step by step, and used that to answer a sharp business
question: for this job, can an open-source model replace a frontier closed model
like GPT-4o? // Let's start with the problem.

---

## Slide 2 — The Business Problem  *(~1:00)*

[SCREEN: Slide 2 — the 14–40h stat]

SAY:
In logistics, a single disruption — a customs hold, port congestion, a carrier
failure — can add fourteen to forty hours to a delivery, on freight that's often
high-value and time-critical. //
Today, a human expediter has to notice the alert, pull up alternative carriers,
weigh cost against speed against reliability, and rebook — usually hours later,
often off-shift. And every hour compounds: missed connections, penalty clauses,
spoiled goods. //
Here's the thing: that decision is repetitive and rule-based. It's a perfect
candidate for automation — *but* automation that books real freight and spends real
money has to be trustworthy. // That word "trust" is the whole project.

---

## Slide 3 — Research Objective  *(~1:00)*

[SCREEN: Slide 3 — three RQ cards]

SAY:
So the assignment asks me to compare a frontier closed-source model against a
leading open-source model on an agentic workflow — and crucially, to evaluate the
*intermediate reasoning*, tool-calling, and error recovery, not just the final
answer. //
I framed that as three research questions. // One: can an open model actually match
a frontier closed model on a deterministic logistics task? // Two: where do these
agents fail — and can you even *see* the failure without inspecting the trajectory?
// And three: what has to wrap the model for autonomous execution to be safe? //
The method that answers all three is trajectory-based evaluation, and I'll come back
to why that matters. First, the system itself.

---

## Slide 4 — System Architecture  *(~1:15)*

[SCREEN: Slide 4 — LangGraph diagram]

SAY:
I built this on LangGraph as an explicit state machine — three agents plus a
recovery path. //
The first agent, Ingestion, reads the raw alert and rates severity. // The second,
Evaluation, calls a carrier API to fetch alternatives and reasons about the
trade-offs — cost, ETA, reliability. // The third, Decision and Execution, picks the
best carrier under the policy and books it. //
The important part is the recovery path — the state transitions in amber. If a tool
fails, or if no carrier satisfies the policy, the graph retries exactly once, and
if it's still failing, it escalates to human review. It never crashes and never
fakes success. //
Why LangGraph instead of an open-ended agent loop? Because the recovery behaviour is
a control-flow *requirement*, not a conversation. An explicit graph makes that
policy auditable — and it makes every node a step I can score. That's the bridge to
the evaluation.

---

## Slide 5 — Agent Workflow  *(~1:15)*

[SCREEN: Slide 5 — pipeline stages]

SAY:
Let me be precise about what's an AI agent versus what's deterministic, because it
matters for safety. //
The classic control-tower pipeline is: telemetry, planning, risk analysis, route
optimisation, policy validation, execution, monitoring, feedback. //
I implemented three of these as LLM agents — ingestion, evaluation, and execution —
because those are the parts where model judgment actually matters and is worth
grading. //
But policy validation and the retry-then-escalate logic are *deterministic code*,
not the model. That's deliberate: safety must never depend on the model's mood. The
execution node has a hard guardrail that rejects any carrier that wasn't offered or
that violates the policy, *before* it books. //
And I deliberately did not spin up seven separate thin agents — for a focused task
that's complexity without benefit. Three agents, one guardrail, one escalation path.

---

## Slide 6 — Trajectory-Based Evaluation  *(~1:30)*  ← the core

[SCREEN: Slide 6 — "WHAT IT REASONED ✓ → WHAT IT DID ✕"]

SAY:
This is the heart of the project, so let me slow down. //
For an agent that takes irreversible actions, scoring only the final answer is
dangerous — because a model can reach the right outcome for the wrong reason, or,
worse, reason perfectly and then do the wrong thing. //
Here's a real example from my logs. Llama 3.1 8B, on a scenario where *every*
carrier breaks the policy. // On the left is what it reasoned: it correctly said —
MidFreight is thirty-two hundred dollars, over the three-thousand-dollar cap;
reliability zero-point-eight-five, below the zero-point-nine floor; non-compliant.
Perfect analysis. //
And then, on the right — it *booked MidFreight anyway*. A policy-violating,
irreversible commitment. And the run gets logged as "rerouted — success." //
That's the punchline: output-only scoring passes this run. Trajectory scoring flags
it as a safety violation. // Same outcome, opposite trust — and only the trajectory
tells them apart. That gap is the entire contribution.

---

## Slide 7 — Experimental Methodology  *(~1:15)*

[SCREEN: Slide 7 — model table]

SAY:
So how do I make that objective and not just my opinion? //
I ran three models through the *identical* harness — same graph, same prompts, same
tools, only the client swaps. GPT-4o as the closed-source frontier baseline, and
Llama 3.3 70B and 3.1 8B as the open models. //
I score four dimensions from the trajectory: tool-calling accuracy, decision
correctness, error recovery, and a reasoning-quality proxy. //
The key is that three of those four are computed *deterministically* against a
policy oracle — a function that independently calculates the correct carrier for
every scenario. So "did it make the right decision" is a checkable number, not a
vibe. //
And I built five scenarios that each stress a different behaviour: a normal reroute,
an ambiguous cost-versus-speed trade-off, a no-viable-option case that must
escalate, a transient tool failure that tests retry, and a hard failure that tests
retry-then-escalate.

---

## Slide 8 — Results  *(~1:45)*  ← the payoff

[SCREEN: Slide 8 — chart + per-scenario table]

SAY:
Here are the results, and they're more interesting than "the expensive model wins."
//
Overall, out of five: Llama 3.3 70B scored a perfect five-point-zero with zero
safety violations. // GPT-4o — the frontier closed model — scored four-point-six,
also zero safety violations. // And Llama 3.1 8B scored three-point-eight-seven,
with one safety violation. //
So on this task, the open 70B actually *edged out* GPT-4o. // And look at where
GPT-4o lost its points: on the tight-margin scenario, it made the *exact same
mistake* the small 8B made — it booked the safer-looking slower carrier instead of
the policy-optimal fastest one. That's a quality slip, not a safety failure — but it
shows this failure mode isn't unique to small models. //
The only model that committed an actual safety violation — booking a non-compliant
carrier instead of escalating — was the 8B. //
One honest caveat I'll state up front: this is one trial per scenario, so it's
directional, not statistically powered. The harness supports multiple trials to
tighten that.

---

## Slide 9 — Technical Trade-offs  *(~1:15)*

[SCREEN: Slide 9 — comparison table]

SAY:
Let me put the trade-offs side by side. //
On accuracy, the open 70B is highest at five-point-zero; GPT-4o is close at
four-point-six. On safety, the 70B and GPT-4o both have zero violations; the 8B has
one. //
But look at cost: GPT-4o is roughly two-and-a-half dollars in, ten dollars out per
million tokens. The 70B is well under a dollar. The 8B is about five cents. //
Interestingly, GPT-4o was the most *concise* — it used the fewest tokens. //
I'm not claiming open beats closed in general — GPT-4o's broader capability just
doesn't get exercised by a narrow, deterministic policy task. The claim is
narrower and defensible: for *this* job, a large open model is the right tool, on
accuracy, safety, and cost.

---

## Slide 10 — Production Readiness  *(~1:15)*

[SCREEN: Slide 10 — readiness cards]

SAY:
This is built like a system, not a notebook. //
Safety is deterministic: the guardrail blocks un-offered or non-compliant bookings,
and error recovery is retry-once-then-escalate — it never fakes success. //
There are twelve unit tests, including one that reproduces the 8B's exact failure
scores — so the benchmark itself is verified, not just asserted. //
The results are reproducible *without an API key* — I can rescore everything from
the committed trajectory logs with one command. // The whole thing runs in Docker
with a single command, there's structured logging on the control-flow events, and a
process-mining view over the trajectories. //
On scalability: the rate limiter is thread-safe for parallel runs, and swapping the
simulated carrier API for a real TMS or booking system is a localised change behind
the same interfaces.

---

## Slide 11 — Business Recommendation  *(~1:15)*

[SCREEN: Slide 11 — Yes / No columns + ROI]

SAY:
So — the business question. Can an open model replace GPT-4o here? For this use
case, yes. //
I'd deploy Llama 3.3 70B as the primary reasoning engine, behind the deterministic
guardrail. It beat GPT-4o, had zero safety violations, costs a fraction as much per
token, and it's self-hostable — which means data residency and no per-call vendor
lock-in. //
What I would *not* do is let the 8B execute autonomously. It forced a
policy-violating booking — that's a safety defect, not a quality nit. Its role is
cheap, read-only triage, with a stronger model gating any real action. //
And the ROI framing for non-technical stakeholders: inference costs about
three-tenths of a cent per reroute for the 70B, versus fifteen to thirty dollars of
human expediter labour plus hours of delay. // The decision was never about token
price. It's about trust — and the guardrailed 70B earns it.

---

## Slide 12 — Future Improvements  *(~0:45)*

[SCREEN: Slide 12 — roadmap]

SAY:
Where this goes next. // First, broaden the closed baseline — run Claude and Gemini
through the same harness; the adapters are already wired. // Second, statistical
rigour: multiple trials, more scenarios, and an LLM-as-judge to replace the keyword
reasoning proxy. // Then production scaffolding — persistent memory for crash-safe
in-flight reroutes, a human-in-the-loop escalation console, real integrations via
MCP, and process-mining dashboards for observability at scale.

---

## Slide 13 — Lessons Learned  *(~0:45)*

[SCREEN: Slide 13 — three columns]

SAY:
Three things I'm taking away. // On research: outcome-only evaluation hides safety
defects — and the frontier model isn't automatically best on a narrow task. // On
engineering: make safety deterministic, not model-dependent — and an independent
oracle turns evaluation from opinion into reproducible numbers. // And on product:
choose the model on trust, not token price, and always ask where the LLM actually
adds value versus where a rule is enough.

---

## Slide 14 — Close  *(~0:30)*

[SCREEN: Slide 14 — Q&A]

SAY:
To sum up: a working autonomous rerouting agent, a trajectory-based evaluation that
caught a safety failure output-scoring would miss, and a data-backed recommendation
— for this task, a guardrailed open model can replace the frontier one, at a
fraction of the cost. //
The code, the report, and this deck are all in the repository. // Thank you — I'm
happy to take questions.

---

### Optional 60-second version (for a LinkedIn / teaser cut)
SAY:
I built an autonomous logistics agent that reroutes disrupted shipments — and a way
to *trust* it. Instead of grading only the final booking, I scored the model's
entire decision trajectory. That caught something output-scoring never would: a
small model that reasoned a carrier was non-compliant, then booked it anyway. I ran
GPT-4o against two open Llama models on the identical harness — and the open 70B
actually matched the frontier model, with zero safety violations, at a tenth of the
cost. The takeaway: for a narrow, well-specified task, a guardrailed open model can
replace a closed one — you just have to measure trust, not just outcomes.
