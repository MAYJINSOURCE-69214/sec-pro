import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("secpro_install", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_install_twice_preserves_unrelated_and_backs_up_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            codex, skills, data = base / "codex", base / "skills", base / "data"
            codex.mkdir()
            (codex / "AGENTS.md").write_text("# My guidance\nKeep this.\n", encoding="utf-8")
            skills.mkdir()
            (skills / "unrelated.txt").write_text("mine", encoding="utf-8")
            profile = codex / "agents/sec-pro-reader.toml"
            profile.parent.mkdir()
            profile.write_text("custom old content", encoding="utf-8")
            command = [sys.executable, str(ROOT / "install.py"), "--codex-home", str(codex), "--skills-home", str(skills), "--data-dir", str(data), "--skip-gsd"]
            subprocess.run(command, check=True, capture_output=True)
            first = (codex / "AGENTS.md").read_bytes()
            backups = list(codex.rglob("*.secpro-backup-*"))
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(first, (codex / "AGENTS.md").read_bytes())
            self.assertEqual(backups, list(codex.rglob("*.secpro-backup-*")))
            self.assertIn(b"Keep this.", first)
            self.assertEqual(first.count(installer.BEGIN.encode()), 1)
            self.assertEqual((skills / "unrelated.txt").read_text(), "mine")
            self.assertEqual(next(profile.parent.glob("*.secpro-backup-*")).read_text(), "custom old content")

    def test_custom_home_refuses_upstream_before_running(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(installer, "node_runtime") as node:
            with self.assertRaisesRegex(ValueError, "require --skip-gsd"):
                installer.main(["--codex-home", temp])
            node.assert_not_called()

    def test_ambiguous_markers_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "AGENTS.md"
            path.write_text(installer.BEGIN, encoding="utf-8")
            with self.assertRaises(ValueError):
                installer.merge_agents(path, "unused")
            self.assertEqual(path.read_text(), installer.BEGIN)

    def test_archive_rejects_traversal_and_links_before_extraction(self):
        for name, is_link in (("../escape.js", False), ("package/link", True), ("C:\\escape.js", False)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                vendor = base / "vendor"
                vendor.mkdir()
                archive = vendor / "opengsd-gsd-core-1.19.0.tgz"
                with tarfile.open(archive, "w:gz") as bundle:
                    member = tarfile.TarInfo(name)
                    if is_link:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "../outside"
                        bundle.addfile(member)
                    else:
                        member.size = 1
                        bundle.addfile(member, io.BytesIO(b"x"))
                lock = {"version": "1.19.0", "archive": archive.name, "sha512": hashlib.sha512(archive.read_bytes()).hexdigest(), "license": "MIT"}
                (vendor / "gsd-lock.json").write_text(json.dumps(lock), encoding="utf-8")
                target = base / "extract"
                target.mkdir()
                with patch.object(installer, "ROOT", base), self.assertRaisesRegex(ValueError, "Unsafe"):
                    installer.unpack_gsd(target)
                self.assertEqual(list(target.iterdir()), [])

    def test_archive_checksum_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "vendor").mkdir()
            (base / "vendor/opengsd-gsd-core-1.19.0.tgz").write_bytes(b"corrupt")
            (base / "vendor/gsd-lock.json").write_text(json.dumps({"version": "1.19.0", "archive": "opengsd-gsd-core-1.19.0.tgz", "sha512": "wrong", "license": "MIT"}), encoding="utf-8")
            with patch.object(installer, "ROOT", base), self.assertRaisesRegex(ValueError, "SHA-512 mismatch"):
                installer.unpack_gsd(base / "extract")

    def test_gsd_merge_preserves_explicit_conflicts_and_unrelated(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "defaults.json"
            original = {"model_profile": "quality", "unrelated": {"keep": True},
                        "model_overrides": {"gsd-executor": "user-model"},
                        "effort": {"default": "high", "agent_overrides": {"gsd-executor": "low"}}}
            path.write_text(json.dumps(original), encoding="utf-8")
            models = json.loads((ROOT / "config/models.json").read_text())
            expected, conflicts = installer.merge_gsd_workers(path, models)
            result = json.loads(path.read_text())
            self.assertEqual(conflicts, ["gsd-executor"])
            self.assertNotIn("gsd-executor", expected)
            self.assertEqual(result["model_overrides"]["gsd-executor"], "user-model")
            self.assertEqual(result["effort"]["agent_overrides"]["gsd-executor"], "low")
            self.assertEqual(result["unrelated"], original["unrelated"])
            self.assertEqual(result["model_profile"], "quality")
            first = path.read_bytes()
            installer.merge_gsd_workers(path, models)
            self.assertEqual(path.read_bytes(), first)
            self.assertEqual(len(list(path.parent.glob("*.secpro-backup-*"))), 1)

    def test_pinned_official_gsd_converter_emits_explicit_worker_pairs(self):
        # Pure exported converter in a child process, not the official installer.
        # No global install, project changes, or current-home defaults are used.
        try:
            node = installer.node_runtime()
        except ValueError as exc:
            self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            extracted = installer.unpack_gsd(base / "extracted")
            config = base / "defaults.json"
            expected, conflicts = installer.merge_gsd_workers(config, json.loads((ROOT / "config/models.json").read_text()))
            self.assertEqual(conflicts, [])
            script = """
const fs = require('fs');
console.log = () => {}; // upstream prints a banner even when imported
const api = require(process.argv[1]);
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = {};
for (const name of Object.keys(cfg.model_overrides)) {
  out[name] = api.generateCodexAgentToml(name, `---\nname: ${name}\ndescription: isolated conversion test\n---\nBounded task.`, cfg.model_overrides, null, cfg.effort);
}
process.stdout.write(JSON.stringify(out));
"""
            env = dict(os.environ, GSD_TEST_MODE="1", HOME=str(base), USERPROFILE=str(base))
            result = subprocess.run([node, "-e", script, str(extracted), str(config)],
                                    cwd=base, env=env, text=True, encoding="utf-8", capture_output=True, check=True)
            converted = json.loads(result.stdout)
            for agent, (model, effort) in expected.items():
                profile = tomllib.loads(converted[agent])
                self.assertEqual(profile["model"], model, agent)
                self.assertEqual(profile["model_reasoning_effort"], effort, agent)


if __name__ == "__main__":
    unittest.main()
