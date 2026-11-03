"""Portable, repository-only context search (Python 3.11 standard library).

Read README active state and docs/context before interpreting historical hits.
Commands: build; check; status; search QUERY --limit 6. --root works before or
after the command for isolated tests. No network, models, Git or external roots.

Committed output: context-index/catalog.json and context-index/chunks.jsonl,
metadata/hashes only. Ignored local output: .context/index.sqlite plus its byte
checksum index.sha256. Build is explicit; searches never write/refresh silently.
Interrupted multi-file publication is detected as stale/corrupt on the next read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
from contextlib import closing
from pathlib import Path

VERSION = "repository-context-1.0"
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_FILES = 2_000
MAX_CHUNKS = 20_000
MAX_INDEX_BYTES = 160_000_000
MAX_CHUNK_CHARS = 12_000
CHUNK_LINES = 60
OVERLAP_LINES = 8
MAX_QUERY_CHARS = 4_096
MAX_QUERY_TERMS = 24
REBUILD = "python -B tools/context_index.py build"
EXTENSIONS = frozenset({".md", ".rst", ".txt", ".py", ".json", ".yaml", ".yml", ".toml",
                        ".ini", ".cfg", ".ps1", ".sh", ".js", ".ts", ".html", ".css"})
PRUNED = frozenset({".git", ".context", "context-index", ".venv", "venv", "__pycache__",
                    "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache", "cache", ".cache",
                    "caches", "source-cache", "runs", ".local-runs", "raw", "private", "secrets",
                    "credentials", "outputs", "work", "dist", "build", "data", "releases"})
SENSITIVE_NAME = re.compile(r"(?:secret|credential|password|cookie|private[-_]?key|api[-_]?key|access[-_]?token|refresh[-_]?token|budget|approval|(?:^|[-_.])(?:keys?|tokens?|auth)(?:[-_.]|$))", re.I)
SENSITIVE_CONTENT = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\bAKIA[A-Z0-9]{16}\b|"
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b|"
    r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}|"
    r"(?im:(?:^|[\s{,])[\"']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token)[\"']?\s*[:=]\s*[\"']?(?!\[REDACTED\]|None\b|null\b|\$|os\.|getenv\b|offline[-_]|test[-_]|example\b|placeholder\b|your[-_])[A-Za-z0-9+/_.-]{16,})"
)
GUIDANCE = "Read README active state and docs/context first; historical records do not override newer active state."


class ContextIndexError(ValueError):
    pass


class IndexStateError(ContextIndexError):
    def __init__(self, report):
        self.report = report
        super().__init__(report["reason"] + "; run " + REBUILD)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def _is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _root(root):
    path = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    # Reject linked ancestors, including Windows junctions, without traversing them.
    absolute = Path(os.path.abspath(path))
    for ancestor in [*reversed(absolute.parents), absolute]:
        if ancestor.exists() and _is_link(ancestor):
            raise ContextIndexError("Repository root must not use symlinks or reparse points")
    if not absolute.is_dir():
        raise ContextIndexError("Repository root is not an existing directory")
    return absolute.resolve()


def _denied_name(name):
    lower = name.casefold()
    return (lower.startswith(".env") or lower.startswith(".")
            or lower in {"id_rsa", "id_ed25519", "authorized_keys", "known_hosts"}
            or SENSITIVE_NAME.search(name) is not None)


def _walk(root):
    """Prune before scandir/read; never follow links, hidden or denied trees."""
    def visit(directory):
        if _is_link(directory) or not directory.resolve().is_relative_to(root):
            return
        with os.scandir(directory) as entries:
            children = sorted(entries, key=lambda entry: entry.name)
        for entry in children:
            path = Path(entry.path)
            if directory == root and entry.name.casefold() == "packaging_manifest.json":
                continue  # Packaging hashes the generated catalog; prevent a cycle.
            if _denied_name(entry.name) or entry.name.casefold() in PRUNED:
                continue
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                continue
            if stat.S_ISDIR(info.st_mode):
                yield from visit(path)
            elif stat.S_ISREG(info.st_mode) and path.suffix.casefold() in EXTENSIONS:
                # Windows DirEntry.stat may report zero device/inode. lstat
                # supplies the real file identity for descriptor comparison.
                yield path, path.lstat()
    yield from visit(root)


def _read(root, path, expected):
    if _is_link(path) or not path.resolve().is_relative_to(root):
        raise ContextIndexError("Source changed to an unsafe path while scanning")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as source:
        actual = os.fstat(source.fileno())
        if (actual.st_dev, actual.st_ino, actual.st_size) != (expected.st_dev, expected.st_ino, expected.st_size):
            raise ContextIndexError("Source changed while scanning; retry after repository writes finish")
        raw = source.read(MAX_FILE_BYTES + 1)
        after = os.fstat(source.fileno())
    if (after.st_size, after.st_mtime_ns) != (actual.st_size, actual.st_mtime_ns) or _is_link(path) or not path.resolve().is_relative_to(root):
        raise ContextIndexError("Source changed while scanning; retry after repository writes finish")
    return raw


def _kind(path):
    lower = path.casefold()
    if lower == "readme.md":
        return "active_state", 0
    if lower == "agents.md":
        return "retrieval_guidance", 1
    if lower.startswith("docs/context/"):
        return "active_context", 10
    if lower.startswith("docs/research/") or lower.startswith("explorations/") or "history" in Path(lower).stem or lower.startswith("drafts/"):
        return "historical", 90
    if lower.startswith("docs/"):
        return "documentation", 20
    if lower.startswith("bb8/"):
        return "portable_bb8", 30
    if path.endswith(".md"):
        return "documentation", 40
    return ("test", 70) if "tests" in Path(lower).parts else ("source", 60)


def _title(path, text):
    heading = next((line.lstrip("# ").strip() for line in text.splitlines() if re.match(r"^#{1,6}\s+\S", line)), Path(path).stem.replace("_", " "))
    # Metadata is portable even if a reviewed source contains a local reference.
    heading = re.sub(r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]\S+|/(?:Users|home)/\S+", "[local path]", heading)
    return heading[:160]


def _tags(path, kind):
    parts = re.findall(r"[^\W_]+", path.casefold(), re.UNICODE)
    return sorted(set([kind, *[part for part in parts if part not in {"md", "py", "json", "txt"}]]))[:24]


def _chunks(lines):
    start = 0
    while start < len(lines):
        end, characters = start, 0
        while end < len(lines) and end - start < CHUNK_LINES and characters + len(lines[end]) <= MAX_CHUNK_CHARS:
            characters += len(lines[end])
            end += 1
        if end == start:
            raise ContextIndexError("Unchunkable line; scan omission policy failed")
        yield start + 1, end, "".join(lines[start:end])
        if end == len(lines):
            break
        start = max(start + 1, end - min(OVERLAP_LINES, (end - start) // 4))


def _snapshot(root):
    files, omissions, chunks, bodies = [], [], [], {}
    total = 0
    eligible = 0
    for path, info in _walk(root):
        eligible += 1
        if eligible > MAX_FILES:
            raise ContextIndexError("Repository exceeds the eligible file-count cap")
        relative = path.relative_to(root).as_posix()
        if info.st_size > MAX_FILE_BYTES:
            omissions.append(dict(path=relative, reason="file_byte_cap", bytes=info.st_size))
            continue
        raw = _read(root, path, info)
        if len(raw) > MAX_FILE_BYTES:
            raise ContextIndexError("Source grew beyond the per-file byte cap")
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ContextIndexError("Repository exceeds the total scanned-byte cap")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeError:
            omissions.append(dict(path=relative, reason="invalid_utf8", source_sha256=_sha(raw)))
            continue
        if "\x00" in text or any(ord(c) < 9 or 13 < ord(c) < 32 for c in text):
            omissions.append(dict(path=relative, reason="binary_control_bytes", source_sha256=_sha(raw)))
            continue
        if SENSITIVE_CONTENT.search(text):
            # Do not publish filenames/content for secret-bearing material.
            continue
        lines = text.splitlines(keepends=True)
        if any(len(line) > MAX_CHUNK_CHARS for line in lines):
            omissions.append(dict(path=relative, reason="line_character_cap", source_sha256=_sha(raw)))
            continue
        kind, priority = _kind(relative)
        common = dict(path=relative, source_sha256=_sha(raw), title=_title(relative, text),
                      type=kind, tags=_tags(relative, kind), priority=priority)
        count = 0
        for first, last, body in _chunks(lines):
            item = dict(**common, start_line=first, end_line=last, text_sha256=_sha(body))
            item["id"] = "chunk:" + _sha(_canonical(item))
            chunks.append(item)
            bodies[item["id"]] = body
            count += 1
            if len(chunks) > MAX_CHUNKS:
                raise ContextIndexError("Repository exceeds the chunk-count cap")
        files.append(dict(**common, bytes=len(raw), line_count=len(lines), chunk_count=count))
    chunks.sort(key=lambda item: (item["path"], item["start_line"], item["end_line"]))
    chunk_bytes = "".join(_canonical(item) + "\n" for item in chunks).encode("utf-8")
    catalog = dict(schema_version=VERSION, files=files, omissions=omissions, chunk_count=len(chunks),
                   chunks_sha256=_sha(chunk_bytes), retrieval_guidance=GUIDANCE,
                   policy=dict(file_bytes=MAX_FILE_BYTES, total_scanned_bytes=MAX_TOTAL_BYTES, eligible_files=MAX_FILES,
                               chunks=MAX_CHUNKS, chunk_characters=MAX_CHUNK_CHARS, chunk_lines=CHUNK_LINES,
                               overlap_lines=OVERLAP_LINES, allowed_extensions=sorted(EXTENSIONS),
                               local_index_bytes=MAX_INDEX_BYTES, excluded_root_files=["PACKAGING_MANIFEST.json"],
                               pruned_directories=sorted(PRUNED), hidden_sensitive_paths_and_links="excluded",
                               sensitive_content="excluded_before_indexing", query_mode="quoted_unicode_lexical_AND"))
    catalog["catalog_id"] = "catalog:" + _sha(_canonical(catalog))
    return catalog, chunks, bodies, (_canonical(catalog) + "\n").encode("utf-8"), chunk_bytes


def _directory(root, name, create=False):
    path = root / name
    if path.exists() or path.is_symlink():
        if _is_link(path) or not path.is_dir() or not path.resolve().is_relative_to(root):
            raise ContextIndexError("Generated output directory is linked or unsafe")
    elif create:
        path.mkdir()
    return path


def _output(root, directory, name):
    path = _directory(root, directory) / name
    if path.exists() or path.is_symlink():
        if _is_link(path) or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ContextIndexError("Generated output file is linked or unsafe")
    return path


def _atomic(path, raw):
    descriptor, temporary = tempfile.mkstemp(prefix=".context-write-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(raw)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _bounded_output(path, cap):
    if path.stat().st_size > cap:
        raise ContextIndexError("Generated output exceeds its byte cap")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        value = source.read(cap + 1)
    if len(value) > cap:
        raise ContextIndexError("Generated output exceeds its byte cap")
    return value


def build(root=None):
    root = _root(root)
    catalog, chunks, bodies, catalog_bytes, chunk_bytes = _snapshot(root)
    local = _directory(root, ".context", create=True)
    _directory(root, "context-index", create=True)
    # Validate all fixed targets before creating/overwriting any file.
    index = _output(root, ".context", "index.sqlite")
    checksum = _output(root, ".context", "index.sha256")
    catalog_path = _output(root, "context-index", "catalog.json")
    chunks_path = _output(root, "context-index", "chunks.jsonl")
    descriptor, temporary = tempfile.mkstemp(prefix=".index-build-", suffix=".sqlite", dir=local)
    os.close(descriptor)
    temp = Path(temporary)
    try:
        with closing(sqlite3.connect(temp)) as db, db:
            db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("CREATE TABLE chunks(id TEXT PRIMARY KEY,path TEXT,start_line INTEGER,row_json TEXT NOT NULL,text TEXT NOT NULL)")
            db.execute("CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED,title,tags,text,tokenize='unicode61 remove_diacritics 0')")
            db.executemany("INSERT INTO meta VALUES(?,?)", [("version", VERSION), ("catalog_sha256", _sha(catalog_bytes)), ("chunks_sha256", _sha(chunk_bytes))])
            db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?)", [(item["id"], item["path"], item["start_line"], _canonical(item), bodies[item["id"]]) for item in chunks])
            db.executemany("INSERT INTO search(id,title,tags,text) VALUES(?,?,?,?)", [(item["id"], item["title"], " ".join(item["tags"]), bodies[item["id"]]) for item in chunks])
        _atomic(catalog_path, catalog_bytes)
        _atomic(chunks_path, chunk_bytes)
        os.replace(temp, index)
        _atomic(checksum, (_sha(_bounded_output(index, MAX_INDEX_BYTES)) + "\n").encode("ascii"))
    except sqlite3.Error as exc:
        raise ContextIndexError("SQLite FTS5 index build failed; Python must provide SQLite FTS5") from exc
    finally:
        if temp.exists():
            temp.unlink()
    return dict(status="CURRENT", schema_version=VERSION, catalog_id=catalog["catalog_id"],
                files=len(catalog["files"]), chunks=len(chunks), omissions=catalog["omissions"],
                committed=["context-index/catalog.json", "context-index/chunks.jsonl"],
                local_index=".context/index.sqlite", retrieval_guidance=GUIDANCE)


def _report(state, reason, catalog=None):
    report = dict(status=state, reason=reason, rebuild_command=REBUILD, retrieval_guidance=GUIDANCE)
    if catalog is not None:
        report.update(catalog_id=catalog["catalog_id"], files=len(catalog["files"]), chunks=catalog["chunk_count"], omissions=catalog["omissions"])
    return report


def _verified(root):
    catalog, chunks, bodies, catalog_bytes, chunk_bytes = _snapshot(root)
    paths = [_output(root, "context-index", "catalog.json"), _output(root, "context-index", "chunks.jsonl"),
             _output(root, ".context", "index.sqlite"), _output(root, ".context", "index.sha256")]
    if not all(path.is_file() for path in paths):
        return _report("MISSING", "Context catalog or local index is missing", catalog), None
    # Read at most the expected size + 1, so corrupt generated files cannot
    # circumvent input byte caps. Oversize/changed metadata is simply stale.
    with paths[0].open("rb") as source:
        actual_catalog = source.read(len(catalog_bytes) + 1)
    with paths[1].open("rb") as source:
        actual_chunks = source.read(len(chunk_bytes) + 1)
    if actual_catalog != catalog_bytes or actual_chunks != chunk_bytes:
        return _report("STALE", "Repository sources/policy and committed catalog differ", catalog), None
    try:
        checksum = _bounded_output(paths[3], 128).decode("ascii").strip()
        if not re.fullmatch(r"[a-f0-9]{64}", checksum) or _sha(_bounded_output(paths[2], MAX_INDEX_BYTES)) != checksum:
            return _report("CORRUPT", "Local index byte checksum differs; rebuild required", catalog), None
        with closing(sqlite3.connect(paths[2].as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("Invalid integrity result")
            meta = dict(db.execute("SELECT key,value FROM meta"))
            if meta != dict(version=VERSION, catalog_sha256=_sha(catalog_bytes), chunks_sha256=_sha(chunk_bytes)):
                return _report("CORRUPT", "Local index metadata differs from committed catalog", catalog), None
            expected = [(item["id"], item["path"], item["start_line"], _canonical(item), bodies[item["id"]]) for item in chunks]
            if db.execute("SELECT id,path,start_line,row_json,text FROM chunks ORDER BY path,start_line,id").fetchall() != expected:
                return _report("CORRUPT", "Local chunk rows differ from exact source lines", catalog), None
            expected_fts = sorted((item["id"], item["title"], " ".join(item["tags"]), bodies[item["id"]]) for item in chunks)
            if db.execute("SELECT id,title,tags,text FROM search ORDER BY id").fetchall() != expected_fts:
                return _report("CORRUPT", "Local FTS content differs from source chunks", catalog), None
    except (sqlite3.Error, UnicodeError, OSError, ContextIndexError):
        return _report("CORRUPT", "Local SQLite/FTS index cannot be validated", catalog), None
    return _report("CURRENT", "Catalog and local index match current repository sources", catalog), (chunks, bodies, paths[2])


def check(root=None):
    try:
        report, _ = _verified(_root(root))
        return report
    except (ContextIndexError, OSError):
        return _report("UNSAFE", "Repository scope/output path or scan limits are unsafe; correct scope then rebuild")


def status(root=None):
    return check(root)


def _terms(query):
    if type(query) is not str or len(query) > MAX_QUERY_CHARS:
        raise ContextIndexError("Query must be text within the 4096-character cap")
    terms = list(dict.fromkeys(re.findall(r"[^\W_]+", query.casefold(), re.UNICODE)))
    if len(terms) > MAX_QUERY_TERMS or any(len(term) > 80 for term in terms):
        raise ContextIndexError("Query exceeds lexical term count/length caps")
    return terms


def search(query, root=None, limit=6):
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ContextIndexError("Search limit must be an integer from 1 to 50")
    terms = _terms(query)
    root = _root(root)
    report, verified = _verified(root)
    if report["status"] != "CURRENT":
        raise IndexStateError(report)
    chunks, bodies, index = verified
    ids = {item["id"]: item for item in chunks}
    results = []
    if terms:
        # All syntax is authored here; user-provided characters never reach the
        # FTS grammar. The expression itself is also a bound SQL parameter.
        expression = " AND ".join('"' + term + '"' for term in terms)
        try:
            with closing(sqlite3.connect(index.as_uri() + "?mode=ro", uri=True)) as db:
                db.execute("PRAGMA query_only=ON")
                matches = db.execute("SELECT id,bm25(search) FROM search WHERE search MATCH ?", (expression,)).fetchall()
        except sqlite3.Error as exc:
            raise IndexStateError(_report("CORRUPT", "Local FTS query failed; rebuild required")) from exc
        ranked = sorted(matches, key=lambda match: (ids[match[0]]["priority"], match[1], ids[match[0]]["path"], ids[match[0]]["start_line"]))
        for identity, _ in ranked[:limit]:
            item = ids[identity]
            results.append({**item, "excerpt": bodies[identity]})
    return dict(status="CURRENT", query=query, normalized_terms=terms, catalog_id=report["catalog_id"],
                retrieval_guidance=GUIDANCE, read_first=[p for p in ("README.md", "AGENTS.md") if p in {item["path"] for item in chunks}]
                + sorted({item["path"] for item in chunks if item["path"].startswith("docs/context/")})[:6],
                results=results, result_count=len(results))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root")
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "check", "status", "search"):
        child = subs.add_parser(name)
        child.add_argument("--root", default=argparse.SUPPRESS)
        if name == "search":
            child.add_argument("query")
            child.add_argument("--limit", type=int, default=6)
    args = parser.parse_args(argv)
    try:
        result = search(args.query, args.root, args.limit) if args.command == "search" else globals()[args.command](args.root)
        # Escaped JSON also works on Windows pipes with a legacy code page;
        # decoding it recovers the exact Unicode source excerpt.
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
        return 0 if result["status"] == "CURRENT" else 2
    except IndexStateError as exc:
        print(json.dumps(exc.report, ensure_ascii=True, sort_keys=True, indent=2))
        return 2
    except (ContextIndexError, OSError) as exc:
        print(json.dumps(dict(status="ERROR", reason=str(exc) if isinstance(exc, ContextIndexError) else "Repository IO failed", rebuild_command=REBUILD)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
