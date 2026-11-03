"""Read-only integrity/portability checks for the frozen BB8 instruction snapshot."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
SCHEMA = "bb8-repository-snapshot-1"
SOURCE_TYPES = {".md", ".yaml", ".yml", ".py", ".json"}
HELPERS = {"bb8/README.md", "bb8/snapshot.py", ".agents/skills/bb8/SKILL.md"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def checked_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Invalid relative snapshot path")
    logical = PurePosixPath(relative)
    if logical.is_absolute() or ".." in logical.parts or logical.as_posix() != relative:
        raise ValueError("Snapshot path escape or noncanonical path")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Snapshot path resolves outside its root")
    probe = path
    while probe != root:
        if probe.is_symlink():
            raise ValueError("Snapshot symlink not allowed")
        probe = probe.parent
    return path


def allowed_source(relative):
    parts = PurePosixPath(relative).parts
    if any(part in {"__pycache__", ".git", ".venv", "cache", "state", "sessions"} for part in parts):
        return False
    return relative == ".codex-plugin/plugin.json" or (
        parts[0] in {"harness", "skills"} and PurePosixPath(relative).suffix in SOURCE_TYPES)


def privacy_issues(text, path):
    rules = {
        "machine_private_path": r"(?i)(?:[A-Z]:[\\/]+Users[\\/]+|" + "/" + "Users" + r"/|/home/[A-Za-z0-9_.-]+/)",
        "private_key_shape": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "service_key_shape": r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{24,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{35,})",
    }
    return [{"path": path, "rule": rule} for rule, pattern in rules.items() if re.search(pattern, text)]


def relative_link_issues(path, boundary):
    issues = []
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        destination = match.group(1).strip().strip("<>")
        parsed = urlsplit(destination)
        if parsed.scheme or destination.startswith("#"):
            continue
        target = (path.parent / unquote(parsed.path)).resolve()
        if not target.is_relative_to(boundary.resolve()):
            issues.append({"path": path.relative_to(boundary).as_posix(), "rule": "relative_link_escape"})
        elif not target.exists():
            issues.append({"path": path.relative_to(boundary).as_posix(), "rule": "missing_relative_link", "target": parsed.path})
    return issues


def verify_snapshot(root=None, source_root=None):
    root = Path(root or ROOT).resolve()
    repo = root.parent
    manifest = json.loads((root / "SNAPSHOT.json").read_text(encoding="utf-8"))
    issues = []
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported snapshot schema")
    files = manifest["files"]
    paths = [row["path"] for row in files]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate snapshot file path")
    for row in files:
        if row["source_relative"] != row["path"]:
            raise ValueError("Source logical path must match the copied relative path")
        path = checked_path(root, row["path"])
        if not allowed_source(row["path"]):
            raise ValueError("File outside the human-authored source allowlist")
        data = path.read_bytes()
        if sha(data) != row["sha256"] or len(data) != row["bytes"]:
            issues.append({"path": row["path"], "rule": "snapshot_hash_or_size_mismatch"})
        issues.extend(privacy_issues(data.decode("utf-8"), row["path"]))
        if path.suffix == ".md":
            issues.extend(relative_link_issues(path, root))
        if source_root is not None:
            original = checked_path(Path(source_root).resolve(), row["source_relative"]).read_bytes()
            if sha(original) != row["source_sha256"]:
                issues.append({"path": row["path"], "rule": "installed_source_hash_mismatch"})
            transform = row["transform"]
            expected = original
            if transform is not None:
                if row["path"] != "skills/organise/SKILL.md" or transform["name"] != "portable_knowledge_root_default":
                    raise ValueError("Unknown source transformation")
                matches = list(re.finditer(rb"(?m)^- knowledge root: `([^`]+)`;", original))
                if len(matches) != 1 or sha(matches[0].group(1)) != transform["source_fragment_sha256"]:
                    raise ValueError("Expected single source-specific default")
                start, end = matches[0].span(1)
                expected = original[:start] + b"<USER_SELECTED_KNOWLEDGE_ROOT>" + original[end:]
            if expected != data:
                issues.append({"path": row["path"], "rule": "undeclared_source_transformation"})
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*")
              if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    if actual != set(paths) | {"README.md", "snapshot.py", "SNAPSHOT.json"}:
        issues.append({"path": "bb8/", "rule": "unexpected_or_missing_physical_file"})
    helper_paths = {row["path"] for row in manifest["repository_helpers"]}
    if helper_paths != HELPERS:
        raise ValueError("Unapproved helper scope")
    for row in manifest["repository_helpers"]:
        path = checked_path(repo, row["path"])
        if sha(path.read_bytes()) != row["sha256"]:
            issues.append({"path": row["path"], "rule": "repository_helper_hash_mismatch"})
    # Helpers are authored integration, not copies of current host prompts.
    issues.extend(relative_link_issues(root / "README.md", root))
    issues.extend(relative_link_issues(repo / ".agents/skills/bb8/SKILL.md", repo))
    plugin = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if plugin["version"] != manifest["source"]["plugin_version"] or plugin["author"]["name"] != manifest["source"]["author"]:
        issues.append({"path": ".codex-plugin/plugin.json", "rule": "plugin_provenance_mismatch"})
    if not (root / plugin["skills"]).resolve().is_relative_to(root) or not (root / plugin["skills"]).is_dir():
        issues.append({"path": ".codex-plugin/plugin.json", "rule": "invalid_skills_directory"})
    skills = sorted(path.parent.name for path in (root / "skills").glob("*/SKILL.md"))
    if skills != manifest["skills"] or len(files) != manifest["source_file_count"]:
        issues.append({"path": "SNAPSHOT.json", "rule": "source_skill_inventory_mismatch"})
    registry = (root / "harness/capability-registry.yaml").read_text(encoding="utf-8")
    ids = re.findall(r'^  - id: "([^"]+)"', registry, re.M)
    if sorted(ids) != skills:
        issues.append({"path": "harness/capability-registry.yaml", "rule": "capability_skill_mismatch"})
    for file in ("harness/capability-registry.yaml", "harness/manifest.yaml"):
        text = (root / file).read_text(encoding="utf-8")
        for relative in re.findall(r'^\s*(?:entrypoint|system_prompt|routing_contract|capability_registry|skill_catalog|plan_template): "([^"]+)"', text, re.M):
            target = (root / file).parent / relative
            if not target.resolve().is_relative_to(root) or not target.is_file():
                issues.append({"path": file, "rule": "unresolved_harness_entrypoint"})
    return {"status": "PASS" if not issues else "FAIL", "source_files": len(files), "skill_entrypoints": len(skills),
            "source_plugin_version": plugin["version"], "issues": issues,
            "scope": "instruction snapshot integrity/links; no host tool or private knowledge availability claim"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify"])
    parser.add_argument("--source-root", type=Path, help="Optional explicitly selected installed source to compare read-only")
    args = parser.parse_args()
    result = verify_snapshot(source_root=args.source_root)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
