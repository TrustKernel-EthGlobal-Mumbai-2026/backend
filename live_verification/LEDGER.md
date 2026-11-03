# Live corpus ledger 1.0.0

Implementation complete; this file is the frozen consumer contract. Parent
owns final integrated execution. Original live corpus and old packages are read-only.

API in `live_verification.ledger`:

```python
build_ledger(source_session: Path, dest: Path) -> dict  # dest must not exist
load_ledger(dest) -> list[dict]
group(rows) -> dict[str, list[dict]]
validate_ledger(dest, source_session=None) -> dict    # raises on invalid bindings
query(dest, table=None, run_id=None, limit=30) -> list[dict]
rebuild_index(rows, path) -> None                    # path must not exist
```

Rows have `id`, `table`, `run_id` (null for session artifacts) and `refs` containing
canonical row IDs. IDs are `table:SHA256(stable identity JSON)`. Canonical ordering
is `(table,id)`, UTF8 JSON with sorted keys/compact separators and LF. Destination
paths and wall-clock build times are excluded. Raw original timestamps remain.

| Table | Principal fields |
| --- | --- |
| artifacts | path (relative source_session), sha256 (raw bytes), data (JSON except trace/index), role |
| runs | directory, context, manifest_artifact_id, trace_artifact_id, event_count |
| events | seq,kind,timestamp,span_id,parent_id,artifact_id,raw (entire original event) |
| calls | span_id,actor,start_event_id,end_event_id,input_seq,output_seq,status |
| texts | text,sha256,artifact_id,event_id,pointer,transform,call_id,actor,role,input_seq,output_seq |
| outputs | event_id,call_id,pointer,disposition,text_ids,provider_status,incomplete_details |
| reports | field,text_id,call_id,output_event_id,origin_method,origin_pointer,origin_args,origin_status,saved_artifact_id,saved_pointer |
| sources | content,sha256,source_call_id,tool,args,provider,source_status,started_at,retrieved_at,event_id,seq,pointer,source_version,source_urls,source_time_fields,cache_status |
| exposures | call_id,text_id,source_id or originating_text_id,start,end,quote,mode,pre_assertion,retrieval_seq |
| passages | text_id,start,end,quote,disposition,heading,rule,tags |
| candidates | text_id,passage_id,start,end,quote,normalization,rule_ids,status |
| relations | relation,status,from_id,to_id,witness; never accepted factual support |
| urls | source_id or text_id,start,end,quote,url,identity_status |
| atoms | source_id or text_id,event_seq,start,end,quote,kind,value,status |
| unresolved | subject_id,reasons,status |
| decisions | report_id,text_id,call_id,event_id,as_of,scope |

Text roles distinguish input strings, generated narratives, and saved reports
with unresolved origins. Structured renderings count once as an originating
narrative only after exact generic rendering replay binds recorded generation
arguments to saved report bytes. Otherwise they remain unresolved saved inventory.
Replay also requires the same rendered field in a recorded step.end after that
generation and before the next model input. Both generation args and observed
step-output pointers are retained, so a plausible formatter alone is insufficient.
`outputs` inventories every generation even with no visible narrative. Inaccessible
reasoning/encrypted content is not extracted; original redacted raw events remain.

Spans are Python Unicode half-open offsets into their canonical parent text or
source content. Text pointer resolves in raw original event, or original JSON
artifact when event_id is null. A transform declares a deterministic structured
render recipe applied to the pointer's args object. Source versions are exact
content identities, not an external revision order or authoritative supersession.
No TTL is authored. Before-input exposures require a same-run original source
strictly earlier than model input; raw tool-role lineage is separate from plain
input content presence. Candidates/reasons are provisional extraction structure,
not verified facts, reliance, accepted premises or complete dependency sets.

Outputs in parent-selected destination: ledger.jsonl,ledger.sqlite,manifest.json,
coverage.json,validation.json,decision-maps.json,unresolved.jsonl. SQLite has
`records(table_name,id,run_id,row_json)` and same-named per-table read views;
query with JSON functions, e.g. `json_extract(row_json,'$.source_status')`.
`validate_ledger` checks canonical bytes/manifest, all references/hashes/spans,
no source hindsight and full canonical/SQLite logical parity. With source_session
it also rehashes only explicitly inventoried safe artifacts and audits source
JSONL chains/SQLite equality. It never traverses source-cache databases.

The manifest binds raw-byte hashes of ledger.py, ledger_corpus.py,
ledger_extract.py, ledger.schema.json and the two frozen processing/refine_rules
modules. Validation checks the loaded implementation against those hashes.
Extraction validation replays lossless passage boundaries/dispositions, all
candidate boundaries/roles, exact child descriptors, normalization and applied
rules from the original canonical text. This validates reproducible declared
surface processing, never semantic accuracy. A rehashed/index-rebuilt mutated
normalization is rejected by replay.

## Completion and limitations

Only the new dedicated suite was run, using temporary authored test traces/indexes:

```powershell
.venv\Scripts\python.exe -B -m unittest live_verification.tests.test_ledger -v
```

Fourteen tests pass: complete output/report inventory; exact generic structured
replay and unresolved mismatch; destination-independent canonical determinism;
read-only query/rebuild parity; input presence versus tool-call lineage; no source
hindsight; Unicode spans/full character disposition; semicolon condition scope;
original/cache preservation; overwrite refusal; raw chain/index and ledger index
corruption; typed unresolved status/truncation; rehashed normalization rejection;
method/source byte bindings. No original corpus build was performed by this lane.
Parent chooses the new runs/live-verification-* destination and performs the
actual ledger-to-rules run and independent audit under its implementation freeze.

Every saved report remains inventoried even if its generation origin is unknown.
Schema is an extensible envelope; this document and executable validators define
table-specific fields/invariants. Broad numerical/date/URL atoms are lexical
candidates, not certified atomic propositions. Full qualitative decomposition,
paraphrase reliance, source authority/freshness policy, exhaustive dependency
capture and suitability remain unresolved. Same exact content may occur in many
retrievals/inputs; those are occurrence counts, never independent corroboration.
All accepted factual-support counts remain zero. No model/API/source fetch,
spending, credential-cache read, new experiment, user interface or historical
profile regeneration is included.

Example parent-owned staging/readonly commands (use its actual chosen path):

```powershell
.venv\Scripts\python.exe -B -m live_verification.ledger validate --ledger runs/live-verification-<id>/ledger --source-session runs/20261102T192912Z-live-30min-2f24b1
.venv\Scripts\python.exe -B -m live_verification.ledger query --ledger runs/live-verification-<id>/ledger --table reports --limit 30
```

Now: adapter/API and boundary validation complete; source bytes unchanged.
Next: parent executes all six runs and rules, reports actual denominators/maps.
Later: any additional semantic or runtime intervention is separately scoped.
