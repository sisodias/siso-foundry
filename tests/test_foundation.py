"""Synthetic regression tests. No production DB, network, credential or corpus."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "core"))
import check_external_data as external_gate
from check_external_data import capability_ids, verify_atlas
from db import connect_ro, connect_rw
from source_safety import matching_rules, repository_files, scan


class ReadOnlyDatabaseTests(unittest.TestCase):
    def test_uri_reserved_characters_and_writes_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename in ("plain.sqlite", "space name.sqlite", "hash#name.sqlite", "query?name.sqlite", "percent%23.sqlite", "unicode-\u00e9.sqlite"):
                with self.subTest(filename=filename):
                    path = Path(directory) / filename
                    with contextlib.closing(sqlite3.connect(path)) as writer:
                        writer.execute("CREATE TABLE example (value TEXT)")
                        writer.execute("INSERT INTO example VALUES ('synthetic')")
                        writer.commit()
                    before = hashlib.sha256(path.read_bytes()).hexdigest()
                    filenames = {item.name for item in Path(directory).iterdir()}
                    with contextlib.closing(connect_ro(path)) as reader:
                        self.assertEqual(reader.execute("SELECT value FROM example").fetchone()["value"], "synthetic")
                        with self.assertRaises(sqlite3.OperationalError):
                            reader.execute("INSERT INTO example VALUES ('forbidden')")
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
                    self.assertEqual({item.name for item in Path(directory).iterdir()}, filenames)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing?#.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                connect_ro(path)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_writer_behavior_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.sqlite"
            with contextlib.closing(connect_rw(path)) as writer:
                writer.execute("CREATE TABLE example (value TEXT)")
                writer.commit()
                self.assertEqual(writer.execute("PRAGMA busy_timeout").fetchone()[0], 30000)


class AtlasTests(unittest.TestCase):
    def check(self, payload, expected=None, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "atlas.jsonl"
            path.write_bytes(payload)
            before = path.read_bytes()
            answer = verify_atlas(path, {"a", "b"} if expected is None else expected, **kwargs)
            self.assertEqual(before, path.read_bytes())
            self.assertNotIn(str(path), json.dumps(answer))
            self.assertEqual(answer["execution_readiness"], "not_established")
            return answer

    def test_not_configured_blocks(self):
        self.assertEqual(verify_atlas(None, {"a"})["status"], "blocked")

    def test_missing_file_blocks_without_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing"
            self.assertEqual(verify_atlas(path, {"a"})["status"], "blocked")
            self.assertFalse(path.exists())

    def test_directory_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(verify_atlas(Path(directory), {"a"})["status"], "blocked")

    def test_exact_match_has_byte_hash(self):
        payload = b'{"capability_id":"b"}\n\n{"capability_id":"a"}\n'
        answer = self.check(payload)
        self.assertEqual(answer["status"], "pass")
        self.assertEqual(answer["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(answer["observed_count"], 2)

    def test_same_count_wrong_ids_fails(self):
        answer = self.check(b'{"capability_id":"a"}\n{"capability_id":"c"}\n')
        self.assertEqual(answer["status"], "fail")
        self.assertEqual((answer["missing_count"], answer["unexpected_count"]), (1, 1))

    def test_duplicate_fails(self):
        self.assertEqual(self.check(b'{"capability_id":"a"}\n{"capability_id":"a"}')["reason"], "duplicate_atlas_identifier")

    def test_empty_fails(self):
        self.assertEqual(self.check(b'')["status"], "fail")

    def test_malformed_json_fails(self):
        self.assertEqual(self.check(b'{broken')["reason"], "invalid_atlas_record")

    def test_non_utf8_fails(self):
        self.assertEqual(self.check(b'\xff')["reason"], "invalid_atlas_record")

    def test_missing_identifier_fails(self):
        self.assertEqual(self.check(b'{}')["status"], "fail")

    def test_non_object_fails(self):
        self.assertEqual(self.check(b'[]')["status"], "fail")

    def test_non_string_identifier_fails(self):
        self.assertEqual(self.check(b'{"capability_id":42}')["status"], "fail")

    def test_blank_identifier_fails(self):
        self.assertEqual(self.check(b'{"capability_id":" "}')["status"], "fail")

    def test_size_limit_fails(self):
        self.assertEqual(self.check(b'12345', max_bytes=4)["reason"], "atlas_size_limit")

    def test_map_duplicate_fails(self):
        with self.assertRaises(ValueError):
            capability_ids({"capabilities": [{"capability_id": "a"}, {"capability_id": "a"}]})

    def test_map_empty_fails(self):
        with self.assertRaises(ValueError):
            capability_ids({"capabilities": []})

    def test_map_valid(self):
        self.assertEqual(capability_ids({"capabilities": [{"capability_id": "a"}]}), {"a"})


class PublicationTests(unittest.TestCase):
    def test_github_prefixes(self):
        for kind in "pousr":
            with self.subTest(kind=kind):
                self.assertIn("github_token", matching_rules("gh" + kind + "_" + "A" * 36))

    def test_fine_grained_prefix(self):
        self.assertIn("github_fine_grained_token", matching_rules("github" + "_pat_" + "A" * 82))

    def test_api_prefix(self):
        self.assertIn("api_key", matching_rules("sk" + "-proj-" + "A" * 30))

    def test_private_path_markers(self):
        self.assertIn("personal_absolute_path", matching_rules("/" + "Users" + "/synthetic"))
        self.assertIn("private_workspace_marker", matching_rules("SISO" + "_Workspace"))

    def test_key_marker(self):
        self.assertIn("private_key", matching_rules("-----BEGIN " + "PRIVATE KEY-----"))

    def test_ordinary_source_does_not_match(self):
        self.assertEqual(matching_rules("const key = process.env.EXAMPLE;"), [])

    def test_ignored_data_not_scanned_and_receipt_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("private-data/\n")
            (root / "private-data").mkdir()
            token = "ghp" + "_" + "A" * 36
            (root / "private-data" / "secret.txt").write_text(token)
            (root / "safe.txt").write_text("ordinary source")
            self.assertEqual(scan(root), [])
            (root / "candidate.bin").write_bytes(b"\xff" + token.encode())
            findings = scan(root)
            self.assertEqual(findings, [{"path": "candidate.bin", "rules": ["github_token"]}])
            self.assertNotIn(token, json.dumps(findings))

    def test_symlink_target_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("outside.txt\n")
            target = root / "outside.txt"
            target.write_text("ghp" + "_" + "A" * 36)
            (root / "link.txt").symlink_to(target)
            self.assertEqual(scan(root), [])


class GateContractTests(unittest.TestCase):
    def test_optimized_python_is_refused(self):
        completed = subprocess.run(
            [sys.executable, "-B", "-O", str(ROOT / "scripts/check.py"), "--source-only"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("FOUNDRY_CHECK_REFUSED", completed.stderr)

    def test_external_cli_missing_configuration_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "intelligence/agency/capability-pillar-map.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({"capabilities": [{"capability_id": "synthetic"}]}))
            output = io.StringIO()
            with patch.object(external_gate, "__file__", str(root / "scripts/check_external_data.py")):
                with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(output):
                    status = external_gate.main([])
            receipt = json.loads(output.getvalue())
            self.assertEqual(status, 2)
            self.assertEqual(receipt["status"], "blocked")
            self.assertEqual(receipt["reason"], "atlas_not_configured")
            self.assertNotIn(directory, output.getvalue())


class KnowledgeInputGateTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "pipelines/books/fix_tier_score.py"), *args],
            capture_output=True, text=True,
        )

    def test_explicit_root_is_required(self):
        completed = self.invoke()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--knowledge-root", completed.stderr)

    def test_missing_root_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            completed = self.invoke("--knowledge-root", str(missing))
            self.assertEqual(completed.returncode, 2)
            self.assertFalse(missing.exists())

    def test_apply_refused_before_input_read(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = self.invoke("--knowledge-root", directory, "--apply")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("--apply is unsupported", completed.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_empty_synthetic_root_reads_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "sections").mkdir()
            completed = self.invoke("--knowledge-root", directory)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Scanned 0 page files", completed.stdout)
            self.assertEqual(list((Path(directory) / "sections").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
