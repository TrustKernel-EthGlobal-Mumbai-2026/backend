"""Frozen instruction inventory, portability and private-data boundary tests."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bb8.snapshot import checked_path, privacy_issues, verify_snapshot

REPO = Path(__file__).resolve().parents[1]


class BB8SnapshotTests(unittest.TestCase):
    def cloned(self):
        temporary = tempfile.TemporaryDirectory(prefix="bb8-instruction-snapshot-test-")
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name).resolve()
        self.assertTrue(target.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        shutil.copytree(REPO / "bb8", target / "bb8", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        bridge = target / ".agents/skills/bb8"
        bridge.mkdir(parents=True)
        (bridge / "SKILL.md").write_bytes((REPO / ".agents/skills/bb8/SKILL.md").read_bytes())
        return target

    def test_full_snapshot_and_relative_references_verify_without_personal_plugin(self):
        target = self.cloned()
        result = verify_snapshot(target / "bb8")
        self.assertEqual(result["status"], "PASS", result["issues"])
        self.assertEqual(result["source_files"], 68)
        self.assertEqual(result["skill_entrypoints"], 21)

    def test_source_identity_hashes_and_single_declared_portability_transform(self):
        manifest = json.loads((REPO / "bb8/SNAPSHOT.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source"]["author"], "Personal")
        self.assertEqual(manifest["source"]["plugin_version"], "0.2.0+codex.20260917171643")
        transformed = [row for row in manifest["files"] if row["transform"] is not None]
        self.assertEqual([row["path"] for row in transformed], ["skills/organise/SKILL.md"])
        self.assertEqual(sum(row["source_sha256"] == row["sha256"] for row in manifest["files"]), 67)
        content = (REPO / "bb8/skills/organise/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("<USER_SELECTED_KNOWLEDGE_ROOT>", content)
        self.assertEqual(privacy_issues(content, "organise"), [])

    def test_source_mutation_fails_hash_integrity(self):
        target = self.cloned()
        path = target / "bb8/skills/bb8/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nEdited instruction\n")
        result = verify_snapshot(target / "bb8")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(row["rule"] == "snapshot_hash_or_size_mismatch" for row in result["issues"]))

    def test_missing_and_escaping_relative_links_are_reported(self):
        target = self.cloned()
        path = target / "bb8/skills/bb8/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\n[Missing](missing.md)\n[Escape](../../../README.md)\n")
        rules = {row["rule"] for row in verify_snapshot(target / "bb8")["issues"]}
        self.assertIn("missing_relative_link", rules)
        self.assertIn("relative_link_escape", rules)

    def test_path_escape_is_rejected_before_external_file_read(self):
        target = self.cloned()
        for path in ("../outside", "/absolute", "folder/../../outside", "C:" + "/outside", "folder\\outside"):
            with self.assertRaises(ValueError):
                checked_path(target / "bb8", path)
        manifest_path = target / "bb8/SNAPSHOT.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][0]["path"] = "../private.env"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            verify_snapshot(target / "bb8")

    def test_excluded_state_and_compiled_cache_not_source_inventory(self):
        manifest = json.loads((REPO / "bb8/SNAPSHOT.json").read_text())
        self.assertFalse(any("__pycache__" in row["path"] or row["path"].endswith((".db", ".sqlite", ".pyc", ".env")) for row in manifest["files"]))
        target = self.cloned()
        (target / "bb8/unexpected.env").write_text("unit fixture only")
        result = verify_snapshot(target / "bb8")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(row["rule"] == "unexpected_or_missing_physical_file" for row in result["issues"]))

    def test_registry_and_helper_bindings_detect_tampering(self):
        target = self.cloned()
        bridge = target / ".agents/skills/bb8/SKILL.md"
        bridge.write_bytes(bridge.read_bytes() + b"\nModified bridge\n")
        registry = target / "bb8/harness/capability-registry.yaml"
        registry.write_text(registry.read_text().replace('id: "bb8"', 'id: "unregistered"'))
        rules = {row["rule"] for row in verify_snapshot(target / "bb8")["issues"]}
        self.assertIn("repository_helper_hash_mismatch", rules)
        self.assertIn("capability_skill_mismatch", rules)

    def test_no_private_machine_default_survives(self):
        marker = "C:" + "/" + "Users/" + "ExamplePerson/private-vault"
        self.assertTrue(privacy_issues(marker, "unit-fixture"))
        manifest = json.loads((REPO / "bb8/SNAPSHOT.json").read_text())
        for row in manifest["files"]:
            self.assertEqual(privacy_issues((REPO / "bb8" / row["path"]).read_text(encoding="utf-8"), row["path"]), [])


if __name__ == "__main__":
    unittest.main()
