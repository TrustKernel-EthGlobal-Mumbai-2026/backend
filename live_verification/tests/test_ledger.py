"""Only the new adapter is exercised; no historical build setup or network."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from live_verification import ledger
from live_verification.ledger_corpus import render_structured, inspect_trace


def make_corpus(root):
    directory = root / "run-live-test"
    directory.mkdir(parents=True)
    (root / "experiment.json").write_text('{"source_mode":"live_native_market_sources"}', encoding="utf-8")
    context = {"source_mode": "live_native_market_sources", "context_at": "2026-11-02T20:00:00Z",
               "trade_date": "2026-11-03", "model": "local-test-no-model"}
    source = "Date,Open,High,Low,Close\r\n2026-11-02,10,13,9,12\r\nURL: https://example.test/article\n"
    market = "α Close is 12 USD; if uninvested, do not initiate.\nUse no leverage because suitability is unknown.\n"
    news = "News source is unavailable. Read https://example.test/article.\n"
    args_plan = {"recommendation": "Underweight", "rationale": "Price is weak.", "strategic_actions": "Wait if uninvested."}
    args_trader = {"action": "Underweight", "reasoning": "Reduce conditionally, not because headlines prove causality.",
                   "entry_price": None, "stop_loss": None, "position_sizing": "75% of standard allocation"}
    args_pm = {"rating": "Underweight", "executive_summary": "If suitable, consider a modest reduction.",
               "investment_thesis": "Remain cautious because evidence is incomplete.", "price_target": None, "time_horizon": None}
    plan = render_structured("ResearchPlan", args_plan)
    trader = render_structured("TraderProposal", args_trader)
    decision = render_structured("PortfolioDecision", args_pm)
    events = []
    def emit(kind, payload, span=None, parent=None):
        row = dict(schema_version=1, seq=len(events)+1, event_id=f"event-{len(events)+1}", run_id=directory.name,
                   timestamp=f"2026-11-02T20:00:{len(events):02d}+00:00", kind=kind, span_id=span, parent_id=parent,
                   context=context, payload=payload, previous_hash=events[-1]["event_hash"] if events else None)
        row["event_hash"] = ledger.sha(json.dumps(row, sort_keys=True, ensure_ascii=False))
        events.append(row)
    def start(span, actor, messages):
        emit("llm.start", {"messages": [messages], "metadata": {"metadata": {
            "langgraph_node": actor, "langgraph_checkpoint_ns": actor + ":test"}}}, span)
    def end(span, content="", tools=None, status="completed"):
        message = dict(content=content, type="ai", tool_calls=tools or [], response_metadata={"status": status},
                       usage_metadata={"input_tokens": 10, "output_tokens": 5})
        emit("llm.end", {"response": {"generations": [[{"text": content if isinstance(content,str) else "", "message": message}]]}}, span)
    emit("run.start", {"context": context})
    start("m0", "Market Analyst", [{"type": "system", "content": "Before writing report call get_verified_market_snapshot. " + source}])
    end("m0", tools=[{"name": "get_stock_data", "args": {"start_date": "2026-11-01"}, "id": "tool-call-1"}])
    emit("tool.start", {"tool": {"name": "get_stock_data"}, "input": "{'start_date': '2026-11-01'}"}, "tool-span")
    emit("source.tool.start", {"evidence_id": "provider-call-1", "tool": "get_stock_data", "request": {"start_date": "2026-11-01"}})
    emit("evidence.retrieved", {"evidence_id": "provider-call-1", "tool": "get_stock_data", "request": {"start_date": "2026-11-01"},
         "content": source, "content_hash": ledger.sha(source), "source_status": "AVAILABLE", "provider": "native-test",
         "requested_at": "2026-11-02T20:00:04Z", "retrieved_at": "2026-11-02T20:00:05Z",
         "source_urls": ["https://example.test/article"], "source_time_fields": [], "cache_status": "network_observed"})
    emit("tool.end", {"output": {"content": source, "type": "tool", "name": "get_stock_data", "tool_call_id": "tool-call-1"}}, "tool-span")
    start("m1", "Market Analyst", [{"type": "tool", "name": "get_stock_data", "tool_call_id": "tool-call-1", "content": source}])
    end("m1", market, status="incomplete")
    start("n1", "News Analyst", [{"type": "human", "content": "Raw presence: " + source + "\nPrior: " + market}])
    end("n1", [{"type": "reasoning", "summary": [], "encrypted_content": "[REDACTED]"}, {"type": "text", "text": news}])
    for span, actor, schema, args, field, rendered, inputs in [
        ("r1", "Research Manager", "ResearchPlan", args_plan, "investment_plan", plan, market + news),
        ("t1", "Trader", "TraderProposal", args_trader, "trader_investment_plan", trader, plan),
        ("p1", "Portfolio Manager", "PortfolioDecision", args_pm, "final_trade_decision", decision, market + news + plan + trader),
    ]:
        start(span, actor, [{"type": "human", "content": inputs}])
        end(span, tools=[{"name": schema, "args": args, "id": "call-" + span}])
        emit("step.end", {"outputs": {field: rendered}}, span + "-step")
    emit("decision.paper", {"decision": decision, "execution_authority": False})
    emit("run.end", {"status": "success"})
    (directory / "trace.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")
    with closing(sqlite3.connect(directory / "trace.sqlite")) as db, db:
        db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,event_id TEXT,run_id TEXT,timestamp TEXT,kind TEXT,span_id TEXT,parent_id TEXT,payload_json TEXT,event_hash TEXT)")
        db.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)", [(e["seq"],e["event_id"],e["run_id"],e["timestamp"],e["kind"],e["span_id"],e["parent_id"],json.dumps(e["payload"],ensure_ascii=False),e["event_hash"]) for e in events])
    (directory / "run_manifest.json").write_text(json.dumps({"run_id": directory.name, "context": context}), encoding="utf-8")
    (directory / "final_state.json").write_text(json.dumps({"market_report": market, "news_report": news, "investment_plan": plan,
            "trader_investment_plan": trader, "final_trade_decision": decision}, ensure_ascii=False), encoding="utf-8")
    (directory / "source-cache").mkdir()
    (directory / "source-cache/private.sqlite").write_bytes(b"Never read source credential caches")
    return directory, events


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "original"
        self.directory, self.events = make_corpus(self.source)
        self.dest = self.root / "new-ledger"

    def build(self):
        manifest = ledger.build_ledger(self.source, self.dest)
        return manifest, ledger.group(ledger.load_ledger(self.dest))

    def test_complete_inventory_structured_origin_replay_and_zero_support(self):
        manifest, by = self.build()
        self.assertEqual(len(by["events"]), len(self.events))
        self.assertEqual(len(by["reports"]), 5)
        self.assertEqual(len(by["outputs"]), 6)
        self.assertEqual(len([r for r in by["reports"] if r["origin_method"] == "structured_render_replay_exact"]), 3)
        self.assertEqual(len([r for r in by["texts"] if r["role"] == "generated_narrative"]), 5)
        self.assertEqual(len(by["decisions"]), 1)
        self.assertTrue(all(c["normalization"]["accepted_factual_support"] is False for c in by["candidates"]))
        self.assertEqual(manifest["counts"]["sources"], 1)
        self.assertEqual(ledger.validate_ledger(self.dest, self.source)["status"], "PASS")

    def test_determinism_is_independent_of_destination_and_repeat_time(self):
        first = ledger.build_ledger(self.source, self.dest)
        second_dest = self.root / "another-ledger"
        second = ledger.build_ledger(self.source, second_dest)
        self.assertEqual(first, second)
        self.assertEqual((self.dest / "ledger.jsonl").read_bytes(), (second_dest / "ledger.jsonl").read_bytes())

    def test_read_only_query_and_rebuild_logical_parity(self):
        _, by = self.build()
        self.assertEqual(ledger.query(self.dest, "sources", "run-live-test", 2), by["sources"])
        rebuilt = self.root / "rebuilt.sqlite"
        rows = ledger.load_ledger(self.dest)
        ledger.rebuild_index(rows, rebuilt)
        with closing(sqlite3.connect(rebuilt)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM reports").fetchone()[0], 5)
            self.assertEqual(json.loads(db.execute("SELECT row_json FROM sources").fetchone()[0])["source_status"], "AVAILABLE")
        with self.assertRaises(FileExistsError):
            ledger.rebuild_index(rows, rebuilt)

    def test_input_presence_is_not_tool_lineage_and_no_hindsight(self):
        _, by = self.build()
        calls = {r["id"]: r for r in by["calls"]}
        source_exposures = [e for e in by["exposures"] if e["source_id"]]
        self.assertEqual({e["mode"] for e in source_exposures}, {"tool_role_call_lineage", "exact_source_text_presence"})
        self.assertTrue(all(calls[e["call_id"]]["input_seq"] > e["retrieval_seq"] for e in source_exposures))
        self.assertFalse(any(calls[e["call_id"]]["span_id"] == "m0" for e in source_exposures))

    def test_unicode_spans_full_passage_partition_and_semicolon_guards(self):
        _, by = self.build()
        texts = {r["id"]: r for r in by["texts"]}
        for row in by["passages"] + by["candidates"] + by["atoms"] + by["urls"]:
            if row.get("text_id"):
                self.assertEqual(texts[row["text_id"]]["text"][row["start"]:row["end"]], row["quote"])
        conditional = [c for c in by["candidates"] if c["normalization"]["condition_spans"]]
        self.assertTrue(conditional)
        for candidate in conditional:
            self.assertNotIn("α Close", candidate["quote"])
        self.assertTrue(any(r["relation"] == "explicit_stated_reason" for r in by["relations"]))

    def test_original_files_and_source_cache_untouched(self):
        before = {p.relative_to(self.source).as_posix(): ledger.sha(p.read_bytes()) for p in self.source.glob("*/*") if p.is_file()}
        self.build()
        after = {p.relative_to(self.source).as_posix(): ledger.sha(p.read_bytes()) for p in self.source.glob("*/*") if p.is_file()}
        self.assertEqual(before, after)
        artifacts = ledger.query(self.dest, "artifacts", limit=100)
        self.assertFalse(any("source-cache" in a["path"] for a in artifacts))

    def test_existing_and_inside_original_destinations_are_refused(self):
        self.dest.mkdir()
        with self.assertRaises(FileExistsError):
            ledger.build_ledger(self.source, self.dest)
        with self.assertRaises(ValueError):
            ledger.build_ledger(self.source, self.source / "new")

    def test_original_trace_index_and_chain_tampering_are_rejected(self):
        with closing(sqlite3.connect(self.directory / "trace.sqlite")) as db, db:
            db.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
        with self.assertRaisesRegex(ValueError, "logical mismatch"):
            inspect_trace(self.directory)
        raw = (self.directory / "trace.jsonl").read_text(encoding="utf-8")
        (self.directory / "trace.jsonl").write_text(raw.replace('"kind": "run.start"', '"kind": "tampered"'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "chain/sequence"):
            inspect_trace(self.directory)

    def test_unknown_structured_render_stays_unresolved_and_retains_saved_report(self):
        state_path = self.directory / "final_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["final_trade_decision"] += "\nUnproven changed rendering"
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        _, by = self.build()
        report = next(r for r in by["reports"] if r["field"] == "final_trade_decision")
        self.assertEqual(report["origin_method"], "unresolved")
        self.assertIsNone(report["call_id"])
        self.assertTrue(any(o["disposition"] == "structured_origin_unresolved" for o in by["outputs"]))

    def test_mutated_span_source_version_or_future_exposure_rejected(self):
        self.build()
        rows = ledger.load_ledger(self.dest)
        for table, field, value in (("passages", "end", 99999), ("sources", "source_version", "fabricated-authority"), ("exposures", "pre_assertion", False)):
            changed = copy.deepcopy(rows)
            next(r for r in changed if r["table"] == table)[field] = value
            with self.subTest(table=table), self.assertRaises(ValueError):
                ledger._validate_rows(changed)

    def test_index_canonical_and_original_artifact_tampering_rejected(self):
        self.build()
        with closing(sqlite3.connect(self.dest / "ledger.sqlite")) as db, db:
            db.execute("DELETE FROM records WHERE table_name='sources'")
        with self.assertRaisesRegex(ValueError, "logical mismatch"):
            ledger.validate_ledger(self.dest, self.source)
        with self.assertRaises(ValueError):
            ledger.query(self.dest, "malicious'; DROP TABLE records;--")
        with self.assertRaises(ValueError):
            ledger.query(self.dest, limit=-1)

    def test_unknown_prerequisites_source_status_and_truncation_are_preserved(self):
        _, by = self.build()
        self.assertTrue(any(o["provider_status"] == "incomplete" for o in by["outputs"]))
        self.assertTrue(any("freshness_TTL_authority_unknown" in q["reasons"] for q in by["unresolved"]))
        self.assertEqual(by["sources"][0]["source_version"], by["sources"][0]["sha256"])
        self.assertEqual(by["sources"][0]["version_status"], "content_identity_not_authority")

    def test_rehashed_normalization_tampering_fails_extraction_replay(self):
        self.build()
        rows = ledger.load_ledger(self.dest)
        candidate = next(r for r in rows if r["table"] == "candidates")
        candidate["normalization"]["kind"] = "invented_verified_fact"
        raw = "".join(ledger.canonical(r) + "\n" for r in rows).encode("utf-8")
        (self.dest / "ledger.jsonl").write_bytes(raw)
        manifest = json.loads((self.dest / "manifest.json").read_text(encoding="utf-8"))
        manifest.update(canonical_sha256=ledger.sha(raw), build_id="live-ledger-" + ledger.sha(raw)[:20])
        (self.dest / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.dest / "ledger.sqlite").unlink()
        ledger.rebuild_index(rows, self.dest / "ledger.sqlite")
        with self.assertRaisesRegex(ValueError, "normalization/rule replay"):
            ledger.validate_ledger(self.dest, self.source)

    def test_implementation_hash_and_original_artifact_bindings_are_checked(self):
        manifest, _ = self.build()
        self.assertEqual(set(manifest["implementation_hashes"]), {
            "live_verification/ledger.py", "live_verification/ledger_corpus.py", "live_verification/ledger_extract.py",
            "live_verification/ledger.schema.json", "verification/processing.py", "verification/refine_rules.py"})
        manifest["implementation_hashes"]["verification/refine_rules.py"] = "0" * 64
        (self.dest / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "implementation version/hash"):
            ledger.validate_ledger(self.dest, self.source)
        manifest["implementation_hashes"] = ledger.implementation_hashes()
        (self.dest / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        path = self.directory / "run_manifest.json"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source artifact changed"):
            ledger.validate_ledger(self.dest, self.source)


if __name__ == "__main__":
    unittest.main()
