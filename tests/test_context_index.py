"""Isolated standard-library tests; never index the real checkout or old data."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_SPEC = importlib.util.spec_from_file_location("repository_context_index", Path(__file__).parents[1] / "tools/context_index.py")
ci = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ci)


class ContextIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.put("README.md", "# Active state\nSnapshot omission is recorded.\nLive feedback next steps remain proposed.\nSynthetic TTL is authored, not live policy.\nCorrected refinement semicolon repair is preserved.\nFrontend draft stays on hold.\n")
        self.put("AGENTS.md", "# Retrieval order\nRead README active state before history.\n")
        self.put("docs/context/STATE.md", "# Current context\nSnapshot omission and source gaps remain visible.\nLive feedback next steps need a separately scoped design.\n")
        self.put("docs/research/HISTORY.md", "# Historical study\nSnapshot omission was found in an older run.\nSynthetic TTL was a fixture rule.\n")
        self.put("bb8/skills/plan/SKILL.md", "# Plan\nPreserve known boundaries and ask only for missing decisions.\n")

    def put(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return target

    def test_end_to_end_priority_exact_lines_source_hash_and_guidance(self):
        built = ci.build(self.root)
        self.assertEqual(built["status"], "CURRENT")
        result = ci.search('"snapshot omission"', self.root)
        self.assertEqual(result["results"][0]["path"], "README.md")
        self.assertEqual([r["priority"] for r in result["results"]], sorted(r["priority"] for r in result["results"]))
        self.assertIn("README", result["retrieval_guidance"])
        for row in result["results"]:
            raw = (self.root / row["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row["source_sha256"])
            lines = raw.decode("utf-8").splitlines(keepends=True)
            self.assertEqual("".join(lines[row["start_line"]-1:row["end_line"]]), row["excerpt"])
        for query in ("live feedback next steps", "synthetic TTL", "corrected refinement semicolon", "frontend draft"):
            self.assertTrue(ci.search(query, self.root)["results"], query)

    def test_deterministic_metadata_and_logical_rebuild_without_absolute_paths(self):
        first = ci.build(self.root)
        catalog = (self.root / "context-index/catalog.json").read_bytes()
        chunks = (self.root / "context-index/chunks.jsonl").read_bytes()
        with contextlib.closing(sqlite3.connect(self.root / ".context/index.sqlite")) as db:
            logical = db.execute("SELECT * FROM chunks ORDER BY id").fetchall()
        second = ci.build(self.root)
        self.assertEqual(first, second)
        self.assertEqual(catalog, (self.root / "context-index/catalog.json").read_bytes())
        self.assertEqual(chunks, (self.root / "context-index/chunks.jsonl").read_bytes())
        self.assertNotIn(str(self.root).encode(), catalog + chunks)
        with contextlib.closing(sqlite3.connect(self.root / ".context/index.sqlite")) as db:
            self.assertEqual(logical, db.execute("SELECT * FROM chunks ORDER BY id").fetchall())
        self.assertEqual(ci.check(self.root)["status"], "CURRENT")

    def test_stale_edit_add_delete_refuse_until_explicit_build(self):
        ci.build(self.root)
        for action in (lambda: self.put("README.md", "# New active state\nSnapshot omission revised.\n"),
                       lambda: self.put("docs/context/NEW.md", "# A new decision\nNew context\n"),
                       lambda: (self.root / "docs/context/NEW.md").unlink()):
            action()
            self.assertEqual(ci.status(self.root)["status"], "STALE")
            with self.assertRaises(ci.IndexStateError) as caught:
                ci.search("snapshot omission", self.root)
            self.assertIn("build", caught.exception.report["rebuild_command"])
            ci.build(self.root)

    def test_missing_index_and_corrupt_sqlite_are_not_served(self):
        self.assertEqual(ci.status(self.root)["status"], "MISSING")
        with self.assertRaises(ci.IndexStateError):
            ci.search("snapshot", self.root)
        ci.build(self.root)
        (self.root / ".context/index.sqlite").write_bytes(b"not a database")
        self.assertEqual(ci.check(self.root)["status"], "CORRUPT")
        with self.assertRaises(ci.IndexStateError):
            ci.search("snapshot", self.root)

    def test_rehashed_corrupt_index_content_still_fails_logical_validation(self):
        ci.build(self.root)
        index = self.root / ".context/index.sqlite"
        with contextlib.closing(sqlite3.connect(index)) as db, db:
            db.execute("UPDATE chunks SET text='invented stale context'")
        (self.root / ".context/index.sha256").write_text(hashlib.sha256(index.read_bytes()).hexdigest()+"\n", encoding="ascii")
        self.assertEqual(ci.check(self.root)["status"], "CORRUPT")
        with self.assertRaises(ci.IndexStateError):
            ci.search("snapshot", self.root)

    def test_queries_are_lexical_not_sql_or_fts_programs(self):
        ci.build(self.root)
        for query in ("snapshot-omission", '"snapshot omission"', "snapshot:omission"):
            self.assertTrue(ci.search(query, self.root)["results"], query)
        for query in ('" OR 1=1 -- DROP TABLE chunks;', "snapshot NOT omitted", "../../outside/private.key", "* () : ^ -", "zzznomatch"):
            result = ci.search(query, self.root)
            self.assertEqual(result["result_count"], 0, query)
        self.assertEqual(ci.check(self.root)["status"], "CURRENT")
        for query in ("x" * 5000, " ".join("word"+str(i) for i in range(30))):
            with self.assertRaises(ci.ContextIndexError):
                ci.search(query, self.root)

    def test_policy_prunes_denied_names_dirs_binary_and_secret_content_before_index(self):
        denied = [".env", ".env.example", "credentials.md", "keys.txt", "api_key.json", "budget_policy.json",
                  "private/notes.md", "raw/context.md", "runs/test/trace.md", ".git/config.md", "cache/value.md", "outputs/data.md"]
        for path in denied:
            self.put(path, "NEVER_INDEX_PRIVATE_MARKER")
        self.put("photo.png", b"NEVER_INDEX_BINARY_MARKER")
        self.put("notes.md", json.dumps({"api_key": "opaque-" + "private-value-0123456789"}))
        read_paths = []
        original = ci._read
        def read(root, path, expected):
            read_paths.append(path.relative_to(root).as_posix())
            return original(root, path, expected)
        with patch.object(ci, "_read", side_effect=read):
            built = ci.build(self.root)
        self.assertFalse(set(denied) & set(read_paths))
        self.assertNotIn("photo.png", read_paths)
        catalog = json.loads((self.root / "context-index/catalog.json").read_text(encoding="utf-8"))
        self.assertNotIn("notes.md", [item["path"] for item in catalog["files"]])
        with contextlib.closing(sqlite3.connect(self.root / ".context/index.sqlite")) as db:
            saved = "\n".join(row[0] for row in db.execute("SELECT text FROM chunks"))
        self.assertNotIn("NEVER_INDEX", saved)
        self.assertNotIn("opaque-private-value", saved)
        self.assertGreater(built["files"], 0)

    def test_packaging_and_generated_outputs_do_not_create_hash_cycles(self):
        ci.build(self.root)
        before = (self.root / "context-index/catalog.json").read_bytes()
        self.put("PACKAGING_MANIFEST.json", '{"hashes_the_catalog":"changing export"}')
        self.put("context-index/other.md", "derived marker")
        self.put(".context/other.md", "cache marker")
        self.assertEqual(ci.check(self.root)["status"], "CURRENT")
        ci.build(self.root)
        self.assertEqual(before, (self.root / "context-index/catalog.json").read_bytes())

    def test_invalid_utf8_binary_control_and_large_lines_are_explicit_omissions(self):
        self.put("bad.md", b"\xff\xfeinvalid")
        self.put("binary.txt", b"text\x00binary")
        self.put("long.md", "x" * (ci.MAX_CHUNK_CHARS + 1))
        built = ci.build(self.root)
        reasons = {row["path"]: row["reason"] for row in built["omissions"]}
        self.assertEqual(reasons["bad.md"], "invalid_utf8")
        self.assertEqual(reasons["binary.txt"], "binary_control_bytes")
        self.assertEqual(reasons["long.md"], "line_character_cap")
        self.assertEqual(ci.check(self.root)["status"], "CURRENT")

    def test_byte_count_and_chunk_caps_are_enforced(self):
        self.put("large.md", "z" * 500)
        with patch.object(ci, "MAX_FILE_BYTES", 300):
            self.assertTrue(any(row["reason"] == "file_byte_cap" for row in ci.build(self.root)["omissions"]))
        with patch.object(ci, "MAX_FILES", 1), self.assertRaises(ci.ContextIndexError):
            ci.build(self.root)
        with patch.object(ci, "MAX_TOTAL_BYTES", 100), self.assertRaises(ci.ContextIndexError):
            ci.build(self.root)
        with patch.object(ci, "MAX_CHUNKS", 1), self.assertRaises(ci.ContextIndexError):
            ci.build(self.root)

    def test_multi_chunk_unicode_and_crlf_excerpt_is_exact(self):
        body = "".join(f"Line {i}: αλφα snapshot omission\r\n" for i in range(160))
        self.put("docs/context/UNICODE.md", body)
        ci.build(self.root)
        rows = ci.search("αλφα", self.root, limit=20)["results"]
        self.assertGreater(len(rows), 1)
        lines = body.splitlines(keepends=True)
        for row in rows:
            self.assertEqual(row["excerpt"], "".join(lines[row["start_line"]-1:row["end_line"]]))
            self.assertEqual(hashlib.sha256(row["excerpt"].encode("utf-8")).hexdigest(), row["text_sha256"])

    def test_symlinked_file_directory_and_output_never_escape_repo(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        target = outside / "notes.md"
        target.write_text("OUTSIDE_CONTENT_MUST_NOT_BE_READ", encoding="utf-8")
        try:
            (self.root / "linked.md").symlink_to(target)
            (self.root / "linked-dir").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Host does not permit creating symlinks")
        original = os.scandir
        seen = []
        def scan(path):
            seen.append(Path(path))
            self.assertTrue(Path(path).resolve().is_relative_to(self.root.resolve()))
            return original(path)
        with patch.object(ci.os, "scandir", side_effect=scan):
            ci.build(self.root)
        self.assertNotIn(outside, seen)
        self.assertEqual(ci.search("OUTSIDE_CONTENT_MUST_NOT_BE_READ", self.root)["results"], [])
        (self.root / "context-index/catalog.json").unlink()
        (self.root / "context-index/catalog.json").symlink_to(target)
        with self.assertRaises(ci.ContextIndexError):
            ci.build(self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), "OUTSIDE_CONTENT_MUST_NOT_BE_READ")

    def test_link_policy_rejects_unsafe_root_and_generated_directory(self):
        real_is_link = ci._is_link
        with patch.object(ci, "_is_link", side_effect=lambda path: Path(path) == self.root or real_is_link(path)):
            with self.assertRaises(ci.ContextIndexError):
                ci.build(self.root)
        (self.root / ".context").mkdir()
        with patch.object(ci, "_is_link", side_effect=lambda path: Path(path) == self.root / ".context" or real_is_link(path)):
            with self.assertRaises(ci.ContextIndexError):
                ci.build(self.root)

    def test_no_outside_or_junction_walk_even_without_symlink_creation_privilege(self):
        junction = self.root / "mock-junction"
        self.put("mock-junction/notes.md", "FORBIDDEN_JUNCTION_TARGET")
        self.put("runs/hidden/notes.md", "FORBIDDEN_RUN_TARGET")
        real_is_link, real_scandir = ci._is_link, os.scandir
        visited = []
        def scan(path):
            current = Path(path)
            self.assertTrue(current.is_relative_to(self.root))
            self.assertNotEqual(current, junction)
            self.assertFalse(current.is_relative_to(self.root / "runs"))
            visited.append(current)
            return real_scandir(path)
        with patch.object(ci, "_is_link", side_effect=lambda path: Path(path) == junction or real_is_link(path)), \
                patch.object(ci.os, "scandir", side_effect=scan):
            ci.build(self.root)
        self.assertIn(self.root, visited)
        self.assertNotIn(junction, visited)

    def test_source_link_swap_is_refused_before_open(self):
        source = self.root / "README.md"
        real_is_link = ci._is_link
        with patch.object(ci, "_is_link", side_effect=lambda path: Path(path) == source or real_is_link(path)):
            with self.assertRaises(ci.ContextIndexError), patch.object(ci.os, "open") as open_file:
                ci._read(self.root, source, source.lstat())
            open_file.assert_not_called()

    def test_cli_root_before_after_command_and_stale_exit_code(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(ci.main(["--root", str(self.root), "build"]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "CURRENT")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(ci.main(["search", "snapshot omission", "--root", str(self.root)]), 0)
        self.assertGreater(json.loads(output.getvalue())["result_count"], 0)
        self.put("README.md", "Changed state")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(ci.main(["check", "--root", str(self.root)]), 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "STALE")


if __name__ == "__main__":
    unittest.main()
