"""Read-only live trace adapter and deterministic, separately staged ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

VERSION = "live-ledger-1.0.0"
TABLES = ("artifacts", "runs", "events", "calls", "texts", "outputs", "reports", "sources",
          "exposures", "passages", "candidates", "relations", "urls", "atoms", "unresolved", "decisions")


def implementation_hashes():
    root = Path(__file__).resolve().parents[1]
    paths = ("live_verification/ledger.py", "live_verification/ledger_corpus.py",
             "live_verification/ledger_extract.py", "live_verification/ledger.schema.json",
             "verification/processing.py", "verification/refine_rules.py")
    return {path: sha((root / path).read_bytes()) for path in paths}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def ident(table, identity):
    return table + ":" + sha(canonical(identity))


def resolve(value, pointer):
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("Invalid JSON Pointer")
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def walk_strings(value, pointer=""):
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk_strings(item, pointer + "/" + str(i))
    elif isinstance(value, dict):
        for key, item in value.items():
            # Exclude inaccessible reasoning and redacted secrets from text inventories.
            if key in ("encrypted_content", "summary"):
                continue
            yield from walk_strings(item, pointer + "/" + key.replace("~", "~0").replace("/", "~1"))


def occurrences(text, quote):
    if not quote:
        return
    start = 0
    while (at := text.find(quote, start)) >= 0:
        yield at, at + len(quote)
        start = at + 1


class Ledger:
    def __init__(self):
        self.records = {}

    def add(self, table, identity, run_id=None, refs=(), **fields):
        if table not in TABLES:
            raise ValueError("Unknown canonical table")
        row = dict(id=ident(table, identity), table=table, run_id=run_id,
                   refs=sorted(set(r for r in refs if r is not None)), **fields)
        previous = self.records.get(row["id"])
        if previous is not None and previous != row:
            raise ValueError("Identity reused with changed canonical fields")
        self.records[row["id"]] = row
        return row

    def rows(self):
        return sorted(self.records.values(), key=lambda row: (row["table"], row["id"]))


def group(rows):
    result = {table: [] for table in TABLES}
    for row in rows:
        result[row["table"]].append(row)
    return result


def rebuild_index(rows, path):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE records(table_name TEXT NOT NULL,id TEXT PRIMARY KEY,run_id TEXT,row_json TEXT NOT NULL)")
        db.execute("CREATE INDEX records_run ON records(run_id,table_name)")
        db.executemany("INSERT INTO records VALUES(?,?,?,?)",
                       [(r["table"], r["id"], r["run_id"], canonical(r)) for r in rows])
        for table in TABLES:
            db.execute(f'CREATE VIEW "{table}" AS SELECT id,run_id,row_json FROM records WHERE table_name=\'{table}\'')


def load_ledger(dest):
    return [json.loads(line) for line in (Path(dest) / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]


def query(dest, table=None, run_id=None, limit=30):
    if table is not None and table not in TABLES:
        raise ValueError("Unknown table")
    if type(limit) is not int or limit < 0:
        raise ValueError("Limit must be a nonnegative integer")
    path = (Path(dest) / "ledger.sqlite").resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT row_json FROM records WHERE (? IS NULL OR table_name=?) AND (? IS NULL OR run_id=?) ORDER BY table_name,id LIMIT ?",
                          (table, table, run_id, run_id, limit)).fetchall()
    return [json.loads(row[0]) for row in rows]


def _validate_rows(rows):
    from .ledger_corpus import render_structured
    by_id = {r["id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError("Duplicate canonical identity")
    by = group(rows)
    events = {r["id"]: r for r in by["events"]}
    artifacts = {r["id"]: r for r in by["artifacts"]}
    texts = {r["id"]: r for r in by["texts"]}
    sources = {r["id"]: r for r in by["sources"]}
    for run in by["runs"]:
        previous = None
        for seq, event in enumerate(sorted((e for e in by["events"] if e["run_id"] == run["run_id"]), key=lambda e: e["seq"]), 1):
            raw = event["raw"]
            body = {k: v for k, v in raw.items() if k != "event_hash"}
            if (event["seq"] != seq or raw["seq"] != seq or raw["run_id"] != event["run_id"]
                    or raw["kind"] != event["kind"] or raw["timestamp"] != event["timestamp"]
                    or raw["previous_hash"] != previous or sha(json.dumps(body, sort_keys=True, ensure_ascii=False)) != raw["event_hash"]):
                raise ValueError("Embedded original trace integrity mismatch")
            previous = raw["event_hash"]
    for row in rows:
        if set(("id", "table", "run_id", "refs")) - row.keys() or row["table"] not in TABLES:
            raise ValueError("Invalid canonical envelope")
        if any(ref not in by_id for ref in row["refs"]):
            raise ValueError("Dangling canonical reference")
    for text in texts.values():
        if sha(text["text"]) != text["sha256"]:
            raise ValueError("Text hash mismatch")
        if text["event_id"]:
            value = resolve(events[text["event_id"]]["raw"], text["pointer"])
        else:
            value = resolve(artifacts[text["artifact_id"]]["data"], text["pointer"])
        if text["transform"]:
            value = render_structured(text["transform"]["name"], value)
            transform = text["transform"]
            observed = events[transform["observed_event_id"]]
            if observed["seq"] <= text["output_seq"] or resolve(observed["raw"], transform["observed_pointer"]) != value:
                raise ValueError("Structured rendering observed-output witness mismatch")
        if value != text["text"]:
            raise ValueError("Text source pointer/transform mismatch")
    for source in sources.values():
        event = events[source["event_id"]]
        if resolve(event["raw"], source["pointer"]) != source["content"] or sha(source["content"]) != source["sha256"]:
            raise ValueError("Source content binding mismatch")
        if source["source_version"] != source["sha256"]:
            raise ValueError("Source version must be content identity only")
    for row in rows:
        if "start" in row and "end" in row and "quote" in row:
            parent = texts.get(row.get("text_id")) or sources.get(row.get("source_id"))
            if parent is None:
                raise ValueError("Span has no canonical text/source parent")
            body = parent.get("text", parent.get("content"))
            a, b = row["start"], row["end"]
            if type(a) is not int or type(b) is not int or not 0 <= a <= b <= len(body) or body[a:b] != row["quote"]:
                raise ValueError("Exact Unicode span mismatch")
    calls = {r["id"]: r for r in by["calls"]}
    for report in by["reports"]:
        if resolve(artifacts[report["saved_artifact_id"]]["data"], report["saved_pointer"]) != texts[report["text_id"]]["text"]:
            raise ValueError("Saved report/source text binding mismatch")
    for exposure in by["exposures"]:
        call = calls[exposure["call_id"]]
        source = sources.get(exposure.get("source_id")) or texts.get(exposure.get("originating_text_id"))
        if source is None or source["run_id"] != call["run_id"]:
            raise ValueError("Invalid exposure source scope")
        origin_seq = source.get("seq", source.get("output_seq"))
        if origin_seq is None or origin_seq >= call["input_seq"] or not exposure["pre_assertion"]:
            raise ValueError("Exposure source hindsight")
        if source.get("content", source.get("text")) != exposure["quote"]:
            raise ValueError("Exposure does not match complete originating content")
    from .ledger_extract import validate_extraction
    validate_extraction(by)
    return dict(status="PASS", rows=len(rows), exact_span_and_reference_bindings=True,
                no_source_hindsight=True, accepted_factual_support=0)


def validate_ledger(dest, source_session=None):
    from .ledger_corpus import inspect_trace
    dest = Path(dest)
    rows = load_ledger(dest)
    expected_bytes = "".join(canonical(r) + "\n" for r in sorted(rows, key=lambda r: (r["table"], r["id"]))).encode("utf-8")
    raw_bytes = (dest / "ledger.jsonl").read_bytes()
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != VERSION or manifest.get("implementation_hashes") != implementation_hashes():
        raise ValueError("Ledger implementation version/hash mismatch")
    coverage = json.loads((dest / "coverage.json").read_text(encoding="utf-8"))
    if sha(canonical(coverage)) != manifest.get("coverage_sha256"):
        raise ValueError("Coverage/manifest binding mismatch")
    if raw_bytes != expected_bytes or sha(raw_bytes) != manifest["canonical_sha256"]:
        raise ValueError("Canonical bytes/manifest digest mismatch")
    if manifest["build_id"] != "live-ledger-" + sha(raw_bytes)[:20] or manifest["counts"] != dict(Counter(r["table"] for r in rows)):
        raise ValueError("Manifest identity/count mismatch")
    result = _validate_rows(rows)
    with closing(sqlite3.connect((dest / "ledger.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Ledger SQLite integrity failure")
        indexed = db.execute("SELECT table_name,id,run_id,row_json FROM records ORDER BY table_name,id").fetchall()
        if indexed != [(r["table"], r["id"], r["run_id"], canonical(r)) for r in rows]:
            raise ValueError("Canonical/index logical mismatch")
    by = group(rows)
    source_root = Path(source_session).resolve() if source_session is not None else None
    if source_root is not None:
        for artifact in by["artifacts"]:
            path = (source_root / artifact["path"]).resolve()
            if not path.is_relative_to(source_root) or "source-cache" in Path(artifact["path"]).parts:
                raise ValueError("Input artifact leaves safe corpus scope")
            if sha(path.read_bytes()) != artifact["sha256"]:
                raise ValueError("Original source artifact changed")
        for run in by["runs"]:
            inspect_trace(source_root / run["directory"])
    result.update(build_id=manifest["build_id"], canonical_sha256=manifest["canonical_sha256"],
                  logical_index_parity=True, original_sources_checked=source_root is not None)
    return result


def build_ledger(source_session: Path, dest: Path):
    from .ledger_corpus import ingest
    from .ledger_extract import extract
    source_session, dest = Path(source_session).resolve(), Path(dest).resolve()
    if dest.exists():
        raise FileExistsError("Ledger destination already exists")
    if dest.is_relative_to(source_session):
        raise ValueError("Cannot write inside the original source corpus")
    ledger = Ledger()
    ingest(ledger, source_session)
    extract(ledger)
    rows = ledger.rows()
    validation = _validate_rows(rows)
    raw = "".join(canonical(r) + "\n" for r in rows).encode("utf-8")
    by = group(rows)
    coverage = dict(counts=dict(Counter(r["table"] for r in rows)),
                    event_kinds=dict(Counter(r["kind"] for r in by["events"])),
                    source_statuses=dict(Counter(r["source_status"] for r in by["sources"])),
                    report_origins=dict(Counter(r["origin_method"] for r in by["reports"])),
                    output_dispositions=dict(Counter(r["disposition"] for r in by["outputs"])),
                    text_roles=dict(Counter(r["role"] for r in by["texts"])),
                    extraction_characters=sum(len(r["text"]) for r in by["texts"] if r["role"] in ("generated_narrative", "saved_report_unresolved")),
                    passage_dispositions=dict(Counter(r["disposition"] for r in by["passages"])),
                    extraction_complete_surface_partition=True, semantic_recall=None,
                    accepted_factual_support=0,
                    exclusions=["No private reasoning, credential caches, external fetch or source authority inference",
                                "Broad surface disposition is not complete semantic extraction",
                                "Exact input presence is not reliance, entailment or sufficient support"])
    manifest = dict(schema_version=VERSION, build_id="live-ledger-" + sha(raw)[:20],
                    canonical_sha256=sha(raw), counts=coverage["counts"],
                    source_artifacts=[{k: a[k] for k in ("path", "sha256")} for a in sorted(by["artifacts"], key=lambda a: a["path"])],
                    methods={"processing": "2.0.0", "refine_rules": "3.0.1", "adapter": VERSION},
                    implementation_hashes=implementation_hashes(),
                    coverage_sha256=sha(canonical(coverage)))
    dest.mkdir(parents=True, exist_ok=False)
    (dest / "ledger.jsonl").write_bytes(raw)
    rebuild_index(rows, dest / "ledger.sqlite")
    maps = []
    for decision in by["decisions"]:
        mapped = [r for r in by["relations"] if r["run_id"] == decision["run_id"]]
        maps.append(dict(decision=decision, relations=mapped,
                         unresolved=[r for r in by["unresolved"] if r["run_id"] == decision["run_id"]],
                         accepted_factual_support=0))
    for name, value in (("manifest.json", manifest), ("coverage.json", coverage), ("validation.json", validation), ("decision-maps.json", maps)):
        (dest / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (dest / "unresolved.jsonl").write_text("".join(canonical(r) + "\n" for r in by["unresolved"]), encoding="utf-8")
    # This second check includes input-file and raw trace/index audits, read-only.
    final_validation = validate_ledger(dest, source_session)
    (dest / "validation.json").write_text(json.dumps(final_validation, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Isolated read-only live ledger build/query/validate")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--source-session", required=True)
    build.add_argument("--dest", required=True)
    check = sub.add_parser("validate")
    check.add_argument("--ledger", required=True)
    check.add_argument("--source-session")
    read = sub.add_parser("query")
    read.add_argument("--ledger", required=True)
    read.add_argument("--table", choices=TABLES)
    read.add_argument("--run-id")
    read.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(argv)
    result = build_ledger(Path(args.source_session), Path(args.dest)) if args.command == "build" else (
        validate_ledger(args.ledger, args.source_session) if args.command == "validate" else query(args.ledger, args.table, args.run_id, args.limit))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
