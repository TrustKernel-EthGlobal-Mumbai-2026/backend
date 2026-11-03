# Live-source arm runtime

Implemented 3 November 2026 for the human-approved paired 30-minute experiment.
This lane implements one research arm. The parent owns data-only preflight,
model/rate/budget checks, the 1800-second scheduler, 540-second child termination,
the actual paid launch, progress monitoring and final analysis. No paid model or
public-provider request was performed to implement or test this lane.

The earlier paired runs used actual models over synthetic evidence. This arm
uses native live sources and does not offer a synthetic fixture mode or fallback.
Live retrievals may differ across concurrent arms and times. This is paper
research with no broker, wallet, trading, signature or settlement authority.

## Callable and CLI boundary

```python
from live_experiment.arm import run, build_parser, validate_args, native_config

run(args) -> int                 # 0 success; 1 recorded runtime failure
build_parser() -> argparse.ArgumentParser
validate_args(args) -> dict      # read-only saved budget policy; raises on refusal
native_config(defaults, run_directory, model) -> dict
main(argv=None) -> int           # parser error on invalid preflight
```

The parent invokes `python -m live_experiment.arm` with these arguments:

| Argument | Meaning |
| --- | --- |
| --arm | sol or terra |
| --model | gpt-6.1-sol or gpt-6.1-terra, matching arm |
| --output | new parent session directory; a unique arm child directory is created |
| --pair-id | parent pair identifier |
| --deadline | finite future Unix epoch seconds, enforced again before every request by Budget |
| --approve-paid | explicit parent launch gate |
| --budget-db | existing Desktop TrustKernel runs/approved-budget.sqlite |
| --budget | 5, the existing cumulative hard ceiling |

There is no `--fixture`, source substitution, offline model switch or allowance
reset. `--help` only displays arguments. This lane did not execute the paid CLI.
Python callers supply the same attributes on `args`. Invalid preflight raises
before runtime/client/Budget creation; CLI errors omit credentials/request URLs.

`validate_args` reads the saved policy and opens the canonical existing ledger in
SQLite read-only/query-only mode. It requires the saved initial $3, cumulative
hard $5, one approved extension and finite existing balance within the ceiling.
It does not create a missing ledger, reconcile old requests or release unknown
holds. Deadline, STOP, arm/model and process key presence are checked. Only
`OPENAI_API_KEY` from the existing process environment supplies the model key;
no credential file or registry lookup is introduced. Existing Trace privacy
filtering remains in use for events and artifacts.

## Execution and dependency interfaces

The pinned upstream commit remains
`c4544913a14ed3df5f1ed7b9e8483270ce20682a`. The existing `upstream_check` verifies
HEAD, tracked-source cleanliness and origin before child network restrictions
block subprocesses. No upstream or old trustkernel source is edited.

Lazy `_load_runtime` imports the original `NormalizedChatOpenAI`, `Budget`,
`Trace`, `Observer`, `GraphSetup`, `ConditionalLogic` and `Propagator`. It couples
only to the agreed new APIs:

```python
from live_experiment.sources import live_tools
from live_experiment.safety import network_guard

network_guard(trace=trace)        # installed once inside a child
with live_tools(trace, cfg), run_config(cfg):
    # original graph factories, native tool schemas and model-visible results
    ...
```

The parent guard limits child network/process access; source owner supplies
native-provider HTTP/CFFI restrictions and observation/provenance. The separate
`ApiOnlyTransport` permits model POST requests only to
`https://api.openai.com:443/v1/responses` without query or userinfo. It allows
HTTPX's normalized default HTTPS port (`None`) as well as explicit 443, denies
other endpoints/methods before transport IO, uses zero transport retries and
disables HTTPX environment proxy configuration for the model client.

The same `NormalizedChatOpenAI` instance serves both graph tiers, with medium
reasoning, Responses API, 2048 output tokens, SDK retries zero, store false,
default service tier and 60-second request timeout. Native structured-output
fallbacks inside upstream remain observable; this arm adds no extra model
retry, alternate model or hidden data-vendor LLM. Each model start/end receives
the original Observer callbacks and Budget.before/Budget.settle. Existing
Budget enforces 24 calls, the conservative 50k-byte request envelope, shared
atomic reservations, STOP/deadline, and retains unknown usage reservations.
Upper billing stays in the original module: Sol 5 input / 10 output and Terra
2.5 input / 5 output per million, as parent verified conservative on this date.

`GraphSetup` selects market/news, one research and one risk round, max two
analyst tool rounds, recursion 50, max concurrency one. No
`TradingAgentsGraph` constructor or memory node is used: no persistent memory,
settlement, reflection or feedback. Native prompts, tool descriptions and
schemas are unchanged; snapshot calls are not forced by this wrapper.

The native framework's current host-local date supplies trade_date (the user's
Asia/Calcutta date on this host). Metadata records both UTC context_at/utc_date
and local_context_at/local_date/local_timezone at the same instant, with
date_basis=current_local_date. Thus UTC 2 November can legitimately have local
trade_date 3 November. This avoids native Polymarket treating today's run as
historical because it compares local dates. Source bar/publication/retrieval
clocks remain separate and may still identify a 2 November UTC bar; no next-day
bar or tick is fabricated. Instrument context states Ethereum
ETH-USD/USD and live native paper research without synthetic labels. Daily bars
and incomplete candles remain source observations, never relabeled current ticks.

## Native configuration and isolation

`native_config` deep-copies defaults and explicitly pins model/provider,
English/medium, graph limits, retries, disabled checkpoints and empty
tool_vendors. Selected vendor chains are core OHLCV/indicators/news = yfinance,
macro = FRED, prediction = Polymarket. The unused native fundamental category
retains sec_edgar,yfinance; no fundamental analyst is selected. No selected
category says `default`, so this arm does not silently add vendors.

Each unique arm run directory has fresh `data_cache_dir=source-cache`,
`results_dir=native-results`, and an unused memory path. Native global cache
isolation, including Yahoo timezone/cookie cache, is source-owner responsibility
inside `live_tools`. No old synthetic cache is reused by this arm.

## Artifacts and observable failure

Unique directories use `<arm>-<uuid12>` under the session; Trace creates them
exclusively. Artifacts are `run_manifest.json`, `trace.jsonl`, `trace.sqlite`,
`console.log`, and on success `final_state.json` and partial
`claim_candidates.json`. There is no fixture artifact/hash. Metadata mode and
source_mode both equal `live_native_market_sources`, inference = `paid-openai`.
The manifest captures configuration, native configuration, package versions,
upstream commit and implementation hashes using existing Trace digest behavior
(SHA256 of its JSON representation, not raw-file SHA256).

The arm runtime.log handler and top-level run.error/manifest exception strings
mask api_key/token query parameters before existing Trace filtering. Diagnostics
mentioning crumb/cookie labels have their entire message text redacted, retaining
logger/level or error_type and a privacy marker. This handles arbitrarily quoted
Yahoo material without modifying old Trace modules or native model-visible
tool results. Source HTTP provenance and native-source error sanitation remain
source-owner responsibilities.

Events include run.start, native source and callback events, decision.paper and
run.end on success; exceptions produce run.error and a failed manifest. An empty
final paper decision is a failure. Logger handlers/level and HTTP client are
restored/closed after execution. The historical summary helper is not invoked:
the new live review module owns cost/source descriptions without synthetic labels.

Native tool strings containing provider errors or NO_DATA remain their exact
native content; the arm does not reinterpret them as valid prices or fabricate
replacement values. The source owner records provider/provenance status; parent
preflight and monitoring own the core-source failure gate. A graph completion
alone does not certify complete source/tool coverage, freshness, claim support,
reasoning quality or suitable investment advice. Claim extraction remains the
old partial explicit-label regex, preserving raw outputs for later review.

## Lane plan and verification

Now complete: isolated arm, parent/source API milestone, and dedicated offline
boundary tests. Next: parent imports complete source/guard modules, runs integrated
offline checks and real data-only preflight, then exclusively controls paid launch.
Later: read-only live run review belongs to its designated owner. Old procedural
loop, recorded-loop, ledger packages, historical artifacts and budget are frozen.

Dedicated check (safe: no actual provider/model invocation):

```powershell
.venv\Scripts\python.exe -m unittest live_experiment.tests.test_arm -v
```

Observed result: 15 tests pass after local-date/privacy correction. Tests use temporary synthetic **test
ledgers and stub runtime objects**, which are never available to the production
arm as market evidence. One test builds the installed native model payload
without invoking it. No test instantiates Budget on the real spending ledger.

| Risk | Tested behavior |
| --- | --- |
| Unauthorized or changed allowance | Approval, canonical DB, saved-policy and model mismatch deny before runtime |
| Historical unknown hold erased | Read-only validator leaves temporary ledger bytes/unknown row unchanged |
| Deadline/STOP/key absent | Refuse before run creation or paid initialization |
| Non-native model route | Wrong host/path/method/port/query/userinfo denied before IO; native POST allowed |
| Hidden vendor or old cache | Explicit chains, empty overrides, per-arm paths and defaults remain unchanged |
| Callback or graph drift | Stub run verifies before/settle callbacks and exact model/graph controls |
| Synthetic/live or date confusion | Separate current UTC/local metadata, midnight-boundary regression, no fixture artifact or execution authority |
| Native crumb diagnostics leak | Runtime log/run error and manifest strings mask crumb/cookie/api_key/token material |
| Silent fallback or false success | Source/graph exception and absent final decision produce failed records |
| Unpinned source | Upstream failure prevents all client/runtime initialization |

These are runtime-boundary tests, not a completed live experiment or validation
of provider availability. No paid or real-provider execution is claimed here.
