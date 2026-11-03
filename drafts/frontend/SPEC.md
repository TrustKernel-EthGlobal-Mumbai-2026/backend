# System observatory exploration

Status: DRAFT, provisionally approved by the user on 1 November 2026. Keep the current exploration preserved; no further frontend development or production integration requested. The provisional approval is not approval of verification policies or live controls.

31 October 2026. This supersedes the earlier illustrative case-explorer direction as the current frontend exploration; the earlier files remain preserved. This is a local read-only prototype, not production integration.

## Intent and design thinking

Human statement: “this is a observablity layer fior the user to have look under the surface of what's going on, and how trust kernel keeps their systems in check”. The user previously selected Graph led. Treat this as a product correction: the user's running system and its oversight are the entry point; assertions and raw logs are progressively disclosed supporting detail.

Working user assumption: an owner/operator of an agent workflow wants to know what it is doing, what it rests on, what deserves attention and what TrustKernel actually did. We have one stakeholder's direction and existing recorded traces, not interviews or validated usage research. Do not claim broader demand or observed usability outcomes.

Experience hypothesis: an owner can follow an issue from a stage to exact input/output evidence and determine whether TrustKernel merely observed, assessed, notified or enforced. The exploration should make its own coverage limitations visible.

Three user journeys:
1. Orient: identify system/task, run state, latest recorded outcome and oversight mode.
2. Look underneath: select a stage in the graph; inspect its visible output, exact source, known evidence exposure and measured transfers into other calls.
3. Understand oversight: open a protocol finding or provenance observation; see scope, method, observed result, assessment timing availability, delivery and recorded response. Inspect unresolved scope instead of an invented trust score.

## Current prototype boundary

Populate one recorded run sol-0530a9827c2c from immutable expanded-v2-41f1e7dad4c96d9ea45d (SHA-256 401d716ff7cb007d2a44c8d23177b04f490983b0371b1507340b1a281686dd35). Source data is synthetic market fixture material; execution is recorded, not live. Use a static exported read model with exact text/pointers and hashes. No research execution, tool replays, inference, spending, credential access or writes to canonical traces.

Baseline trustkernel_feedback=false. Oversight rail: recorded observation, retrospective checks, feedback disabled, no recorded TrustKernel enforcement. Do not turn the operating-mode label into a global guarantee of safety. Historical guard restrictions are distinct from verifier interventions. Assessment records have no per-check execution timestamp: explicitly show it unavailable; do not plot them at the earlier model-event time. Check results come from preserved legacy narrow checks; v2 candidate extraction is not new verification.

System graph nodes are ten originating stage outputs. Exact whole-text matches in later final call inputs define measured text-transfer edges. These are not causality, semantic dependency, private reasoning or accepted support. Select a stage to show its measured incoming edges and actual output; use a text list for the graph's relation equivalents. No structural edge invented to make the graph look complete.

Source details show exact report/discussion text plus origin method. Evidence details distinguish run-level availability/retrieval from selected-call exact presence; absence of a complete exact match is not proof that no paraphrased or partial content reached the call. A missing required snapshot is a bounded protocol finding; it does not establish that price claims are false. Shared declared news-source identity is a provenance observation, not automatically a verification failure. Candidate gaps remain separately queryable.

## Component contracts and implementation seams

| Component | Input | Behavior / state |
|---|---|---|
| RunHeader | run manifest, final decision text | Identity/model/effort/replay state, synthetic fixture, recorded outcome |
| OversightRail | feedback config, available check records, delivery/enforcement evidence | Observation/assessment/feedback/enforcement states; no false active control |
| StageGraph | originating sources, measured text-transfer edges, selected source | Responsive nodes, selected incoming paths, semantic text equivalent |
| AttentionList | exact protocol check, shared source-root observation, unresolved count | Selection opens Inspector; labels finding/observation/extraction gap distinctly |
| Inspector | selected source/evidence/finding and read-model provenance | Activity/evidence/check detail, raw text disclosure, exact record IDs, no inference |
| RunSequence | ordered originating outputs | Select stage; actual event times in Asia/Calcutta; replay never re-executes |

Portable state: selected stage ID and inspector subject; presentation-only. Data exporter owns origin joins and counts; renderer consumes them without deriving truth. One root-scoped token set owns colors/type/spacing; component styles consume it. Trace text must be escaped or assigned through textContent. Show a visible data error if the embedded snapshot is absent; no synthetic fallback.

## Design application and provenance

Active BB8 experience-design owns framing and journey design. Requested legacy archive consulted: w401 frontend design system (classify structure/content; ground data; avoid drifting styles), w407 AI-integrated UI (inspectable claim/explanation/citation, component-local loading/error and safe text), w409 frontend engineering (co-located spec, shared tokens and component contracts). The archived LongGait Metal/Paper paths, fonts, endpoint examples, quality thresholds and private-reasoning language are not adopted. This project has no verified canonical LongGait design directory. Maintain explicit source/visible rationale instead of promising hidden chain-of-thought. No new inference is triggered by UI interaction.

## States, accessibility and validation

Completed replay is the implemented state. Live connected/lagged/disconnected/partial trace are proposed future states, not implemented claims. Current absence of notification/enforcement is explicitly shown. Missing evidence, no exact match and failed source resolution remain distinct. The graph has an equivalent text relationship list; native buttons preserve keyboard navigation, focus and labels. Narrow layouts stack. Color never carries status alone.

Browser checks: selecting stages, source/evidence/finding inspection, no network requests or script errors, source text round-trip, recorded feedback mode, responsive overflow and keyboard access. These are mechanism checks only. Future usability walkthroughs should ask the stakeholder to identify what the agent saw, whether a finding reached it and which conclusion remains unverified; no independent model-quality evaluation is implied.

## Build outcome

Implemented a read-only snapshot-backed exploration with ten actual originating stage outputs and thirty measured exact text-transfer edges from one recorded run. Stage/evidence/protocol/provenance/coverage selection changes the inspector locally. Exact source content, timestamps and source identities are preserved. A SHA-256 gate binds the exporter to the validated canonical ledger. The renderer makes no network requests. The previous hypothetical inline-feedback scenario is not reused as historical activity.

Sixteen stage/viewport/theme cases passed: first/final stage at 1024, 736, 360 and 320 pixels in light/dark appearances. Additional checks passed for source and evidence text round-trip, protocol timing unavailability, feedback disabled, declared source lineage, no fabricated enforcement, keyboard operation and no runtime/network errors. Desktop and mobile captures were inspected. Local preview wrapper height was expanded for full mobile screenshots; the fragment itself uses content height and responsive stacking.

Next design discussion: whether the default owner view should emphasize a selected decision's incoming context (current default) or a live stage's activity once real live instrumentation exists. No live supervision integration or verification-policy decision is made by this prototype.
