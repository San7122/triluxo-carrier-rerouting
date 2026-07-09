"""Generate docs/deck.pptx -- the Part 3 product strategy deck.

Built directly with python-pptx (the referenced /mnt pptx skill is not present on
this machine). Design intent: sparse slides (headline + <=4 bullets or one visual),
depth carried in speaker notes. Numbers come from the real eval run (eval/results.json).
"""
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]

# ---- palette -------------------------------------------------------------
NAVY = RGBColor(0x0B, 0x25, 0x45)
INK = RGBColor(0x1A, 0x1A, 0x2E)
TEAL = RGBColor(0x1B, 0x99, 0x8B)
AMBER = RGBColor(0xE8, 0xA3, 0x3D)
RED = RGBColor(0xD6, 0x45, 0x50)
GREY = RGBColor(0x5B, 0x64, 0x70)
LIGHT = RGBColor(0xF4, 0xF6, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]


def _fill(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def rect(slide, x, y, w, h, color):
    from pptx.enum.shapes import MSO_SHAPE
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    _fill(s, color)
    return s


def textbox(slide, x, y, w, h, lines, size=18, color=INK, bold=False,
            align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font="Calibri",
            space_after=8, line_spacing=1.05):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    if isinstance(lines, str):
        lines = [lines]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.line_spacing = line_spacing
        if isinstance(ln, tuple):
            text, opts = ln
        else:
            text, opts = ln, {}
        run = p.add_run()
        run.text = text
        f = run.font
        f.size = Pt(opts.get("size", size))
        f.bold = opts.get("bold", bold)
        f.name = font
        f.color.rgb = opts.get("color", color)
    return tb


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def content_slide(title, kicker=None):
    """Standard slide: top accent bar + title, returns slide + content top-y."""
    s = prs.slides.add_slide(BLANK)
    rect(s, 0, 0, SW, SH, WHITE)
    rect(s, 0, 0, Inches(0.28), SH, TEAL)          # left accent spine
    if kicker:
        textbox(s, Inches(0.7), Inches(0.42), Inches(11), Inches(0.4),
                [(kicker.upper(), {"size": 13, "bold": True, "color": TEAL})])
    textbox(s, Inches(0.7), Inches(0.72), Inches(12), Inches(1.0),
            [(title, {"size": 30, "bold": True, "color": NAVY})])
    rect(s, Inches(0.72), Inches(1.68), Inches(2.2), Pt(3), AMBER)
    return s


def bullets(slide, items, x=Inches(0.75), y=Inches(2.05), w=Inches(11.8),
            h=Inches(4.8), size=18, gap=14):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        text = it if isinstance(it, str) else it[0]
        opts = {} if isinstance(it, str) else it[1]
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        p.line_spacing = 1.05
        run = p.add_run()
        run.text = "•  " + text
        run.font.size = Pt(opts.get("size", size))
        run.font.color.rgb = opts.get("color", INK)
        run.font.bold = opts.get("bold", False)
        run.font.name = "Calibri"
    return tb


# =====================================================================
# Slide 1 — Title
# =====================================================================
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, SW, SH, NAVY)
rect(s, 0, Inches(6.9), SW, Inches(0.6), TEAL)
textbox(s, Inches(0.9), Inches(2.1), Inches(11.5), Inches(1.6),
        [("Autonomous Carrier Rerouting", {"size": 46, "bold": True, "color": WHITE})])
textbox(s, Inches(0.9), Inches(3.5), Inches(11.5), Inches(1.0),
        [("Agentic AI that reroutes shipments through disruption — and knows when to ask a human",
          {"size": 22, "color": RGBColor(0xC9, 0xE4, 0xE0)})])
textbox(s, Inches(0.95), Inches(5.2), Inches(11), Inches(0.8),
        [("Technical evaluation + product recommendation   ·   Llama 3.3 70B vs Llama 3.1 8B, real trajectory logs",
          {"size": 15, "color": RGBColor(0x9F, 0xB3, 0xC8)})])
notes(s, "The pitch in one line: we built a working autonomous rerouting agent, evaluated two "
         "open-source models on it by scoring their decision-making step-by-step (not just outcomes), "
         "and we have a clear, defensible recommendation on production-readiness. 15 minutes.")

# =====================================================================
# Slide 2 — Problem
# =====================================================================
s = content_slide("A delayed shipment is a race against the clock — and humans are the bottleneck",
                  kicker="The problem")
bullets(s, [
    ("A customs hold, port congestion, or carrier failure can add 14–40h to an ETA — "
     "on high-value, time-critical freight.", {}),
    ("Today a human expediter notices, pulls up alternatives, weighs cost vs. speed vs. "
     "reliability, and rebooks — often hours later, often off-shift.", {}),
    ("Every hour of latency compounds: missed connections, penalty clauses, spoiled goods.", {}),
    ("The decision is repetitive and rule-based — a strong fit for an autonomous agent, "
     "IF it can be trusted to act.", {"bold": True, "color": NAVY}),
])
notes(s, "Frame the pain around cost-of-delay and the human bottleneck. The punchline is the last "
         "bullet: this is automatable, but automation that books real freight has to be trustworthy. "
         "That 'if it can be trusted' sets up why we evaluated so carefully.")

# =====================================================================
# Slide 3 — Approach / architecture
# =====================================================================
s = content_slide("Three specialised agents, one explicit control graph", kicker="The approach")
# simple architecture diagram
def node(slide, x, y, w, label, sub, color):
    box = rect(slide, x, y, w, Inches(1.15), color)
    tf = box.text_frame; tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = label; r.font.size = Pt(15); r.font.bold = True; r.font.color.rgb = WHITE
    p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run(); r2.text = sub; r2.font.size = Pt(10.5); r2.font.color.rgb = RGBColor(0xE8,0xEE,0xF2)
    return box

y0 = Inches(2.35)
node(s, Inches(0.75), y0, Inches(2.75), "1 · Ingestion", "parse alert, rate severity", NAVY)
node(s, Inches(3.85), y0, Inches(2.75), "2 · Evaluation", "call carrier API, weigh trade-offs", NAVY)
node(s, Inches(6.95), y0, Inches(2.75), "3 · Decision", "pick per policy, book reroute", TEAL)
node(s, Inches(10.05), y0, Inches(2.55), "✔ Rerouted", "booking confirmed", RGBColor(0x2E,0x7D,0x32))
# arrows (thin rects)
for ax in (Inches(3.5), Inches(6.6), Inches(9.7)):
    rect(s, ax, Inches(2.83), Inches(0.35), Pt(3), GREY)
# fallback path
fb = rect(s, Inches(6.95), Inches(4.1), Inches(5.65), Inches(1.0), AMBER)
tf = fb.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE; tf.word_wrap=True
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
r = p.add_run(); r.text = "Fallback: tool fails or no compliant option  →  retry once  →  escalate to HUMAN REVIEW"
r.font.size = Pt(12.5); r.font.bold=True; r.font.color.rgb = INK
rect(s, Inches(8.1), Inches(3.5), Pt(3), Inches(0.6), GREY)
textbox(s, Inches(0.75), Inches(5.5), Inches(12), Inches(1.4), [
    ("Built on LangGraph: an explicit state machine, not an open-ended loop. The recovery rule — "
     "retry once, then escalate — is auditable, and every step is logged as a trajectory.",
     {"size": 15, "color": GREY})])
notes(s, "Walk left to right: ingest → evaluate (calls the — simulated — carrier API) → decide & "
         "execute. The amber box is the safety net: any tool failure or a no-viable-option situation "
         "retries once and then hands off to a human instead of crashing or guessing. Emphasise that "
         "LangGraph's explicit graph is what makes the safety behaviour inspectable and gives us the "
         "step-by-step logs the evaluation needs.")

# =====================================================================
# Slide 4 — Evaluation methodology (analogy)
# =====================================================================
s = content_slide("We grade the working, not just the final answer", kicker="How we evaluated")
bullets(s, [
    ("Analogy: two students both write '42'. One reasoned it out; one copied a neighbour. "
     "Same answer — very different trust. You have to see the working.", {"bold": True, "color": NAVY}),
    ("So we log every step of the agent's decision — its reasoning, which tools it called, "
     "with what arguments, and what it finally did.", {}),
    ("We score four things 1–5: tool use, decision correctness, error recovery, reasoning quality.", {}),
    ("Three of the four are graded automatically against a policy 'answer key' — so the "
     "numbers are objective and reproducible, not opinion.", {}),
], gap=16)
notes(s, "This is the heart of the technical contribution, explained for non-technical stakeholders. "
         "The student analogy lands the point: for an agent that takes real actions, outcome-only "
         "testing is dangerous because a model can get the right answer for the wrong reason — or, as "
         "we found, the right reasoning and then the wrong action. The 'answer key' is a policy oracle "
         "we compute independently.")

# =====================================================================
# Slide 5 — Head-to-head results (chart)
# =====================================================================
s = content_slide("Head-to-head: the big model was flawless; the small one wasn't", kicker="Results")
chart_data = CategoryChartData()
chart_data.categories = ["Tool use", "Decision\ncorrectness", "Error\nrecovery", "Overall"]
chart_data.add_series("Llama 3.3 70B", (5.0, 5.0, 5.0, 5.0))
chart_data.add_series("Llama 3.1 8B", (4.4, 3.2, 3.67, 4.17))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,
                        Inches(0.75), Inches(2.15), Inches(7.7), Inches(4.7), chart_data)
chart = gf.chart
chart.has_title = False
chart.value_axis.minimum_scale = 0
chart.value_axis.maximum_scale = 5
chart.has_legend = True
chart.legend.position = XL_LEGEND_POSITION.BOTTOM
chart.legend.include_in_layout = False
plot = chart.plots[0]
plot.series[0].format.fill.solid(); plot.series[0].format.fill.fore_color.rgb = TEAL
plot.series[1].format.fill.solid(); plot.series[1].format.fill.fore_color.rgb = AMBER
textbox(s, Inches(8.8), Inches(2.4), Inches(4.1), Inches(4.2), [
    ("Scores are 1–5, averaged over 5 disruption scenarios.", {"size": 14, "bold": True, "color": NAVY}),
    ("70B: 5.0 overall — correct on every scenario.", {"size": 14, "color": INK}),
    ("8B: 4.17 overall — fluent, but stumbled on the decisions that matter most.", {"size": 14, "color": INK}),
    ("8B's edge: ~27% faster and far cheaper per token.", {"size": 14, "color": GREY}),
], space_after=12)
notes(s, "The 70B is a clean sweep. The 8B looks respectable on average (4.17) — which is exactly the "
         "trap. The average hides that its losses are concentrated in decision correctness and error "
         "recovery, the two dimensions that govern whether it's safe to let it act. Next slide shows "
         "the specific failure.")

# =====================================================================
# Slide 6 — The critical finding
# =====================================================================
s = content_slide("The critical finding: the small model acted against its own reasoning",
                  kicker="Why the average lies")
box = rect(s, Inches(0.75), Inches(2.1), Inches(11.8), Inches(1.5), LIGHT)
tf = box.text_frame; tf.word_wrap=True; tf.vertical_anchor=MSO_ANCHOR.MIDDLE
tf.margin_left = Inches(0.25); tf.margin_right = Inches(0.25)
p=tf.paragraphs[0]
r=p.add_run(); r.text="8B, on a case where EVERY carrier broke policy:"; r.font.size=Pt(14); r.font.bold=True; r.font.color.rgb=NAVY
p2=tf.add_paragraph()
r2=p2.add_run(); r2.text='Its analysis flagged the carriers as non-compliant — then it booked one anyway ($3,200 vs $3,000 cap; 0.85 vs 0.90 reliability floor). It should have escalated.'
r2.font.size=Pt(14); r2.font.color.rgb=RED
bullets(s, [
    ("On a tight trade-off, the 8B ranked the fastest carrier #1 in its notes — then booked a slower one.", {}),
    ("The 70B, by contrast, made a slip mid-reasoning but self-corrected and escalated correctly.", {}),
    ("Output-only testing would have scored both these 8B runs as 'success'. Reading the trajectory caught it.",
     {"bold": True, "color": NAVY}),
], y=Inches(3.9), h=Inches(3.2), gap=14)
notes(s, "This is the money slide. The 8B doesn't fail by being confused — it fails by being "
         "inconsistent between what it concludes and what it does, and by forcing a policy-violating "
         "booking rather than deferring. For an agent that spends money and commits freight, that is a "
         "safety defect, not a quality nit. And crucially it is invisible unless you inspect the steps.")

# =====================================================================
# Slide 7 — Recommendation (direct)
# =====================================================================
s = content_slide("Is an open model ready to replace a closed one here? Not yet — but one is close",
                  kicker="The recommendation")
# two columns
c1 = rect(s, Inches(0.75), Inches(2.15), Inches(5.75), Inches(4.5), RGBColor(0xEA,0xF6,0xF4))
c2 = rect(s, Inches(6.8), Inches(2.15), Inches(5.75), Inches(4.5), RGBColor(0xFB,0xF0,0xDE))
textbox(s, Inches(1.0), Inches(2.4), Inches(5.3), Inches(4.1), [
    ("✔ Llama 3.3 70B — conditional YES", {"size": 18, "bold": True, "color": RGBColor(0x1B,0x77,0x6B)}),
    ("Deploy as the reasoning engine BEHIND a deterministic policy guardrail.", {"size": 14, "color": INK}),
    ("Flawless decisions + correct escalation in testing.", {"size": 14, "color": INK}),
    ("Guardrail already blocks non-compliant / un-offered bookings.", {"size": 14, "color": INK}),
], space_after=12)
textbox(s, Inches(7.05), Inches(2.4), Inches(5.3), Inches(4.1), [
    ("✘ Llama 3.1 8B — NO for autonomous execution", {"size": 18, "bold": True, "color": RGBColor(0xB2,0x38,0x42)}),
    ("Cheaper and faster, but forced a policy-violating booking.", {"size": 14, "color": INK}),
    ("Use only for read-only triage (ingest/summarise).", {"size": 14, "color": INK}),
    ("A stronger model must gate any real action.", {"size": 14, "color": INK}),
], space_after=12)
notes(s, "Give the direct answer the brief demands — no 'both are good' hedge. The 70B can go to "
         "production for this use case *if* wrapped in the deterministic guardrails we already built. "
         "The 8B should not execute autonomously at all; its role is cheap triage with a stronger model "
         "holding the execution rights. This also frames where a closed model like Claude fits: as the "
         "execution-gating model if the 70B ever proves insufficient at scale.")

# =====================================================================
# Slide 8 — Production architecture
# =====================================================================
s = content_slide("From POC to production: same graph, real edges", kicker="Recommended architecture")
bullets(s, [
    ("Swap simulated tools for real integrations — TMS / rate-shopping API for options, "
     "booking/EDI transaction for execution.", {}),
    ("Keep the deterministic guardrail layer: no non-compliant, un-offered, or over-budget booking ever executes.", {}),
    ("Add monitoring: trajectory logs → dashboards for escalation rate, loop rate, path conformance.", {}),
    ("Add cost controls: per-decision token budget, model routing (small model triages, large model decides).", {}),
    ("Persist state (LangGraph checkpointing) so an in-flight reroute survives a crash.", {}),
], gap=12, size=17)
notes(s, "The message: the architecture doesn't change from POC to prod — only the tool endpoints and "
         "the operational scaffolding around it. That de-risks the build. Call out the four production "
         "pillars: real APIs, guardrails, monitoring, cost controls. The model-routing point (8B "
         "triages, 70B decides) turns our finding into a cost lever.")

# =====================================================================
# Slide 9 — Risks & open questions
# =====================================================================
s = content_slide("Risks & open questions", kicker="What we don't yet know")
bullets(s, [
    ("Evaluation breadth: 5 scenarios, one seed. Production needs many seeds + adversarial cases.", {}),
    ("Closed-model baseline unmeasured: we should run the identical harness on Claude to quantify the gap.", {}),
    ("Real tools misbehave differently: partial failures, latency spikes, schema drift.", {}),
    ("Reasoning-quality auto-score is a proxy — it can't catch factual errors; needs LLM-as-judge.", {}),
    ("Where is the human-escalation threshold set, and who owns the SLA on escalations?", {}),
], gap=12, size=17)
notes(s, "Be candid — evaluators trust a recommendation more when its limits are stated. The most "
         "important open item is running Claude through the same harness; the code already supports it, "
         "it just needs a key. The last bullet is an org question, not a tech one, and worth raising "
         "with product/ops stakeholders.")

# =====================================================================
# Slide 10 — Roadmap / next steps
# =====================================================================
s = content_slide("Roadmap", kicker="Next steps")
def phase(slide, x, title, color, items):
    rect(slide, x, Inches(2.2), Inches(3.85), Inches(0.7), color)
    textbox(slide, x, Inches(2.28), Inches(3.85), Inches(0.6),
            [(title, {"size": 16, "bold": True, "color": WHITE})], align=PP_ALIGN.CENTER)
    tb = slide.shapes.add_textbox(x, Inches(3.05), Inches(3.85), Inches(3.6))
    tf = tb.text_frame; tf.word_wrap=True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i==0 else tf.add_paragraph()
        p.space_after=Pt(9)
        r=p.add_run(); r.text="•  "+it; r.font.size=Pt(13); r.font.color.rgb=INK
phase(s, Inches(0.75), "Now → 4 wks", TEAL,
      ["Run Claude on the same harness", "Expand to 25+ scenarios + seeds", "Add LLM-as-judge scoring"])
phase(s, Inches(4.75), "1 → 2 mo", NAVY,
      ["Integrate one real carrier API", "Shadow-mode on live alerts (no execute)", "Guardrail + monitoring hardening"])
phase(s, Inches(8.72), "2 → 4 mo", AMBER,
      ["Limited autonomous execution", "Model-routing for cost", "Human-in-loop escalation console"])
notes(s, "A credible, staged path: prove the eval out and add the closed-model baseline first; then a "
         "shadow-mode integration that reasons on real alerts but doesn't book; then graduated "
         "autonomous execution with cost routing. Nothing goes live executing until shadow mode earns "
         "trust.")

# =====================================================================
# Slide 11 — Closing
# =====================================================================
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, SW, SH, NAVY)
rect(s, 0, Inches(6.9), SW, Inches(0.6), TEAL)
textbox(s, Inches(0.9), Inches(2.4), Inches(11.5), Inches(1.2),
        [("Autonomous rerouting is buildable today —", {"size": 32, "bold": True, "color": WHITE}),
         ("the hard part is trust, and trust is measurable.", {"size": 32, "bold": True, "color": RGBColor(0xC9,0xE4,0xE0)})])
textbox(s, Inches(0.95), Inches(4.3), Inches(11), Inches(1.5), [
    ("Working POC · real trajectory logs · a defensible model recommendation · a guardrailed path to production.",
     {"size": 17, "color": RGBColor(0x9F,0xB3,0xC8)})])
notes(s, "Close on the theme: the technology is ready; the differentiator is a rigorous, trajectory-based "
         "evaluation that tells you which model to trust and how much to fence it. Invite questions.")

out = ROOT / "docs" / "deck.pptx"
prs.save(str(out))
print(f"Saved {out} with {len(prs.slides._sldIdLst)} slides")
