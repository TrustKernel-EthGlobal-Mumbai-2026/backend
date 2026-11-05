# TradingAgents feedback lane

Updated 5 November 2026. **PERSISTED CORE ACCEPTED; DURABLE DEMO TESTED FOR FINAL REVIEW.**
Branch codex/tradingagents-feedback; draft PR base codex/continuous-verification.

Accepted A0.2 source e088970b0a2d4483b1a8d33309b8ef5c38fdd8d2 / integration
29f038f remains unchanged. Accepted B source 251b3b02c63e860020f94ce0b2962472eb0979fe
is imported unchanged: capture/journal/projection/service, two tests and CAPTURE.md
(dependency commit 91d39ba). No A/B-owned file independently edited. B is no longer
a blocker. C's 9478a61 ambiguity repair was accepted for scoped capture semantics;
orchestrator audit ran 13 generic controls, not native tests.

C owns tradingagents.py, its prompt, test_continuous_tradingagents.py and this
lane/implementation doc. The new StoredFeedbackHost binds actual durable receipt
validation, frozen checkpoint + resolve_view, stored verifier and explicit typed
feedback delivery/inclusion/acknowledgement/revision events. A LocalServiceWorker
keeps B's SQLite creation/calls/close on its owning thread under native ToolNode.
No B thread-safety check is disabled; no standalone transport is implemented.

Actual temporary persisted host-driver loop: original [FAIL,PASS] -> delivered
finding/input inclusion -> explicit acknowledgement -> authored source round ->
new report/proposal revision and checkpoint -> scoped [PASS,PASS] -> abstention.
Unchanged authored defect Close=99 Low=100 remains; procedure PASS does not verify
prices or decision truth. Original result and frozen prefix survive B reopen.
Real invalid-reply-after-commit retry does not duplicate the stored event.

Exact pinned native normal dispatch uses real ToolNode and B service with authored
Runnable/tool responses: normal recheck [PASS,PASS]; capped wrap-up recheck
[INCONCLUSIVE,PASS]/RECHECK. Flattened origin stays UNKNOWN with no invented
feedback_inclusion. Completion metadata is explicitly scripted. Host checkpoint/
coverage/recheck driver is authored; full GraphSetup and actual-model behavior are
not claimed. Host source/verify/remediation counts normal 1/2/1, capped 0/2/1.

Tests: C18 stdlib controls including 4 real persisted-host cases and an artifact case; C5 native cases.
Combined A29+B49+C23: 101 PASS in cached native environment. Stdlib-only: 96 PASS,
native class SKIP. All inputs/stores temporary and authored. Command:
python -S -B -m unittest discover -s tests -p "test_continuous*.py".
For native tests set TRUSTKERNEL_TRADINGAGENTS_UPSTREAM to exact reviewed pin and
omit -S in cached framework environment. No dependency installation.

Historical review: 7961d39 falsely linked two identical returns from one marker;
changes requested. Accepted repair 9478a61 withholds all flattened name/body
attribution, including unique matches. Original review/commits remain preserved;
new B integration preserves those negative controls and uncertainty. A unchanged.

Details, exact seams, evidence distinctions and limits:
[TRADINGAGENTS.md](../TRADINGAGENTS.md). B reports atomic_semantic_ready=false;
convenience acknowledgement remains unsupported. No whole-session capture, global
decision clearance, full semantic ledger or durable graph restart claim.

Next: orchestrator review/integration and shared README/orchestration/CI updates;
generated metadata conflicts handled centrally. Full GraphSetup, actual-model
smoke/live policies, frontend and quality evaluation remain deferred. No paid
model/provider calls, budget/hold mutation, private rebuild, experiment launch,
trade, signature, on-chain action, main merge or sibling clone write.

Bounded scope extension authorized by orchestrator: new tools/continuous_demo.py,
without changing tools/offline_demo.py. Public-helper stdlib host demo retains
feedback.sqlite, events.jsonl and JSON/Markdown summary in a NEW directory under
.local-runs; refuses overwrite/path escape/links. Actual command exercised:
python -S -B tools/continuous_demo.py --output .local-runs/continuous-review-001.
The retained artifact shows original omission FAIL, delivered finding/input,
authored source and revised report/proposal, scoped recheck and preserved failure,
with provider defect UNRESOLVED. This is authored host behavior, not native/model
inference. CLI prints output/read-only SQLite and trace-viewing instructions.

Orchestrator accepted core 1e4e8bd367508b99588f11f43534de32c84d28eb after independent
immutable-snapshot review: 100 PASS native-enabled; 95 PASS stdlib with native
class explicitly skipped (five native cases unexecuted there). This is scoped
persisted/exact AST-seam acceptance, not full GraphSetup or model behavior. Only
the requested demo/handoff remains for final review; no new research scope.
