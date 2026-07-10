# Video Narration Script — Autonomous Carrier Rerouting

**Target length:** ~15 minutes · **Pace:** ~140 words/min · **Voice:** first person, calm and confident.
**How to use:** each block is one slide. The *(cue)* line tells you when to advance. Speak the plain text; the **[on screen]** notes are just reminders of what the audience sees. Numbers are exact — from `eval/results.json`.

---

## Slide 1 — Title *(≈0:45)*

Hi, I'm Sanjana. Over the next fifteen minutes I'll walk you through a project with two parts: first, an autonomous agent that reroutes a shipment when a logistics disruption hits — and second, a research method for deciding *which AI model you can actually trust to run it in production*.

The short version is this: I built the agent on LangGraph, I benchmarked a frontier closed-source model — GPT-4o — against two open-source Llama models, and I scored not just their answers but their entire decision-making process. The result was genuinely surprising, and I'll show you the real numbers.

*(cue: advance to "The business problem")*

---

## Slide 2 — The Business Problem *(≈1:00)*

Let's start with why this matters. In logistics, a single disruption — a customs hold, port congestion, a carrier going bankrupt — can add fourteen to forty hours to a shipment's ETA. On high-value, time-critical freight, every one of those hours compounds into missed connections, penalty clauses, and spoiled goods.

Today, a human expediter handles this. They notice the alert, pull up alternative carriers, weigh cost against speed against reliability, and rebook — often hours later, often off-shift. It's slow, and it's inconsistent.

Here's the key insight: this decision is repetitive and rule-based, which makes it a perfect candidate for an autonomous agent — *if*, and only if, we can trust that agent to take a real, irreversible action. That word "trust" is the whole project.

*(cue: advance to "Research objective")*

---

## Slide 3 — Research Objective *(≈1:15)*

So the assignment was to compare a frontier closed-source model against a leading open-source model on an agentic workflow — and crucially, to evaluate the *intermediate reasoning*, not just the final output.

That framing is the heart of it. For an agent that takes irreversible actions, a right answer reached by *bad* reasoning is luck — and sound reasoning followed by a *wrong* action is a hidden liability. You can't see either of those if you only check the final result. You have to score the whole path.

I set three research questions. One: can an open model match a frontier closed model on a well-specified logistics task? Two: where do these agents actually fail — and are those failures even visible without inspecting the trajectory? And three: what has to wrap the model for autonomous execution to be *safe*?

*(cue: advance to "Architecture")*

---

## Slide 4 — System Architecture *(≈1:15)*

Here's the system. I built it as an explicit LangGraph state machine — three agents in a directed graph.

The alert comes in. The first agent, Ingestion, parses it and rates severity. The second, Evaluation, calls the carrier API and reasons about the cost, ETA, and reliability trade-offs. The third, Decision, picks the best carrier under policy and books the reroute.

And then there's the safety net — this amber path. If a tool fails, or if *no* carrier satisfies the policy, the system retries exactly once, and if it's still stuck, it escalates to a human instead of guessing.

I chose LangGraph specifically over something like CrewAI because this recovery behavior is a control-flow requirement, not a conversation. An explicit graph makes that retry-then-escalate policy auditable — and it gives me a step-by-step log of every decision for free, which is exactly what the evaluation needs.

*(cue: advance to "Agent workflow")*

---

## Slide 5 — Agent Workflow *(≈1:10)*

I want to be precise about what's implemented, because it matters. The classic control-tower pipeline has stages like planner, risk analysis, route optimization, policy validation, execution, monitoring, and feedback.

I implemented three of those as actual LLM agents — ingestion, evaluation, and execution — because those are the parts where model judgment matters and is worth grading. But policy validation and the recovery logic are *deterministic* — plain code, not the model — because safety should never depend on a model's whim. And monitoring here means structured trajectory logs.

I deliberately did *not* spin up seven separate agents. For a bounded task like this, that's complexity without benefit — it would just hide the very steps I need to inspect.

*(cue: advance to "Trajectory-based evaluation")*

---

## Slide 6 — Trajectory-Based Evaluation *(≈1:20)*

This is the core of the research. Think of two students who both write "forty-two" as their answer. One reasoned it out; one guessed. Same answer — completely different levels of trust. You have to see the working.

So I log every step: the agent's reasoning, which tools it called and with what arguments, and what it finally did.

Here's a real example from my logs. The small Llama 8B model, on a scenario where *every* carrier violated the policy — its analysis correctly flagged them all as non-compliant. And then it booked one anyway. It committed to a carrier that broke the cost cap *and* the reliability floor.

If you only looked at the final outcome, that run says "rerouted — success." It looks fine. Only by reading the trajectory do you see it was actually a safety violation. That's the entire argument for this method.

*(cue: advance to "Methodology")*

---

## Slide 7 — Experimental Methodology *(≈1:15)*

Here's how I set it up rigorously. Three models: GPT-4o as the closed frontier baseline, and Llama 3.3 70B and Llama 3.1 8B as the open contenders. Same graph, same prompts, same tools, same policy — the only thing that changes is the model. That symmetry is what makes the comparison fair.

I score four dimensions on a one-to-five scale: tool-calling accuracy, decision correctness, error recovery, and reasoning quality. And here's the important part — three of those four are computed *deterministically* against a policy oracle. That means I independently compute the correct answer in code, so "decision correctness" is a real, checkable number, not an opinion.

I ran five scenarios, each stressing a different behavior: a normal reroute, a tight-margin trade-off, a no-viable-option case that demands escalation, and two tool-failure cases that test recovery. Temperature zero throughout.

*(cue: advance to "Results")*

---

## Slide 8 — Results *(≈1:40)*

Now the results — and this is where it got interesting.

The open Llama 3.3 70B scored a perfect five-point-zero overall, with zero safety violations. GPT-4o, the frontier closed model, scored four-point-six — also zero safety violations, so it was safe, but it was *not* flawless. And the small 8B scored three-point-eight-seven, with one safety violation.

So read that carefully. The open 70B actually *beat* the frontier model on this task. GPT-4o lost points on the tight-margin scenario — and here's the striking part: it made the *exact same* mistake as the little 8B model. Both of them booked carrier BAL-12, the safer-looking, slower option, instead of the policy-optimal fastest one, FAS-11.

And only the 8B committed an outright safety violation — booking a non-compliant carrier instead of escalating.

The headline: on this narrow, well-specified task, a large open model matched a frontier closed model, both were safe — at roughly one-tenth of the per-token cost. And that GPT-4o mistake? Invisible unless you score the trajectory.

I'll add one honest caveat: this is one trial per scenario, so these are directional findings, not statistically powered ones. The harness supports multiple trials to tighten that up.

*(cue: advance to "Trade-offs")*

---

## Slide 9 — Technical Trade-offs *(≈1:05)*

Putting the trade-offs side by side. On accuracy, the 70B leads at five-point-zero. On safety, GPT-4o and the 70B tie at zero violations; the 8B is the outlier with one. On cost, the open models are dramatically cheaper — the 8B is around five cents per million tokens versus GPT-4o's dollars. And GPT-4o was actually the most token-efficient — it said more with less.

The one axis I won't over-claim is latency — that's cross-provider, OpenAI versus Groq's accelerated inference, so I treat it as directional only, not an SLA number.

The takeaway: for *this* job, accuracy and safety are the deciding axes — and the open 70B wins on accuracy, ties on safety, and self-hosts for a fraction of the cost.

*(cue: advance to "Production readiness")*

---

## Slide 10 — Production Readiness *(≈1:05)*

This is built like a system, not a notebook. The guardrail is deterministic — it blocks any booking of a carrier that wasn't offered, before the transaction. Error recovery is retry-once-then-escalate, and it never fakes success. There are twelve unit tests, including one that reproduces the 8B's exact failure scores — which proves the benchmark itself is correct.

Critically, the scoring is fully reproducible *without an API key* — I can regenerate every number from the committed trajectory logs. The whole thing runs in Docker with one command, there's structured logging, and a process-mining view over the logs for observability.

The point I want to land: safety lives in deterministic code, not in the model — so it holds no matter which model you plug in.

*(cue: advance to "Business recommendation")*

---

## Slide 11 — Business Recommendation *(≈1:10)*

So, can an open model replace GPT-4o here? For this use case — yes.

My recommendation is to deploy Llama 3.3 70B as the production primary, running behind the deterministic guardrail. It was the top scorer, it had zero safety violations, it's roughly a tenth of the cost, and because it's self-hostable you get data residency and no vendor lock-in.

What I would *not* do is let the small 8B execute autonomously — it forced a policy-violating booking, and that's a safety defect. Use it only for cheap, read-only triage, with a stronger model gating any real action.

And on ROI — the framing for the business: inference costs about three-tenths of a cent per reroute for the 70B, versus fifteen to thirty dollars of human expediter labor plus hours of delay. The cost of the model is a rounding error. This decision is about *trust*, not token price — and the guardrailed 70B earns that trust.

*(cue: advance to "Roadmap")*

---

## Slide 12 — Future Improvements *(≈0:50)*

Where this goes next. First, broaden the closed baseline — run Claude and Gemini through the identical harness; the adapters are already wired. Second, tighten the rigor: more trials, more scenarios, and an LLM-as-judge to replace my keyword-based reasoning proxy. Third, production scaffolding — LangGraph checkpointing so an in-flight reroute survives a crash, and a human-in-the-loop escalation console. And finally, swap the simulated carrier API for real TMS and booking integrations behind the same interfaces, with process-mining dashboards for fleet-scale observability.

*(cue: advance to "Lessons learned")*

---

## Slide 13 — Lessons Learned *(≈0:55)*

Three quick reflections. On research: outcome-only evaluation hides safety defects — a model can reason perfectly and then act unsafely — and a frontier model isn't automatically the best choice on a narrow task. On engineering: make safety deterministic, and use an independent oracle to turn evaluation from opinion into reproducible numbers. And on product: choose your model on trust, not token price — and scope the LLM to the genuinely ambiguous parts of the workflow, not the parts a simple rule already solves.

*(cue: advance to "Q&A / close")*

---

## Slide 14 — Close *(≈0:40)*

To wrap up: autonomous rerouting is buildable today. The hard part isn't the automation — it's trust. And what this project shows is that trust is *measurable*. By scoring the full decision trajectory, I could tell you not just which model scored highest, but exactly where and how each one would fail in production — and that's what turns a demo into a real recommendation.

Thank you. I'm happy to take questions, and I've got backup detail on the methodology, the cost model, and the failure cases.

*(end — total ≈14:30)*

---

### Delivery tips
- Pause for a beat after each **bold number** — let it land.
- The two moments to slow down and emphasize: the 8B "booked it anyway" story (Slide 6) and "the open model beat the frontier model" reveal (Slide 8).
- If you're over time, trim Slides 12 and 13 first — they're the most compressible.
- Keep the honest caveat on Slide 8 (single trial). Panels trust a presenter who states their own limits.
