import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "agent_skills_install", Path(__file__).parents[1] / "install.py"
)
install = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(install)


class RuntimeTargetTests(unittest.TestCase):
    def test_default_runtime_paths(self):
        home = Path("/tmp/example-home")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                install.skills_dir_for("agents", home), home / ".agents" / "skills"
            )
            self.assertEqual(
                install.skills_dir_for("claude", home), home / ".claude" / "skills"
            )
            self.assertEqual(
                install.skills_dir_for("codex", home), home / ".codex" / "skills"
            )

    def test_generic_override_wins_and_legacy_override_is_claude_only(self):
        home = Path("/tmp/example-home")
        with mock.patch.dict(
            os.environ,
            {"AGENT_SKILLS_DIR": "/tmp/shared", "CLAUDE_SKILLS_DIR": "/tmp/old"},
            clear=True,
        ):
            self.assertEqual(install.skills_dir_for("codex", home), Path("/tmp/shared"))
        with mock.patch.dict(
            os.environ, {"CLAUDE_SKILLS_DIR": "/tmp/old"}, clear=True
        ):
            self.assertEqual(install.skills_dir_for("claude", home), Path("/tmp/old"))
            self.assertEqual(
                install.skills_dir_for("codex", home), home / ".codex" / "skills"
            )

    def test_non_claude_plan_skips_claude_plugins_with_warning(self):
        catalog = {
            "homemade": {},
            "external": {
                "superpowers": {
                    "name": "superpowers",
                    "kind": "plugin",
                    "id": "superpowers@example",
                }
            },
        }
        local = {"selected": ["superpowers"], "machine_local": {}}
        with mock.patch.object(install, "RUNTIME_TARGET", "codex"), mock.patch.object(
            install, "scan_installed", return_value=[]
        ):
            plan = install.build_plan(catalog, local)

        self.assertEqual(plan["to_install"], [])
        self.assertEqual(len(plan["warnings"]), 1)
        self.assertIn("仅支持 Claude Code", plan["warnings"][0])


class CliTests(unittest.TestCase):
    def test_target_option_configures_runtime_before_command(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            install, "cmd_scan", return_value=0
        ) as cmd_scan, mock.patch(
            "sys.argv", ["install.sh", "scan", "--target", "codex"]
        ), mock.patch.dict(os.environ, {"HOME": tmp}, clear=True):
            self.assertEqual(install.main(), 0)

        cmd_scan.assert_called_once()
        self.assertEqual(install.RUNTIME_TARGET, "codex")
        self.assertEqual(install.SKILLS_DIR, Path(tmp) / ".codex" / "skills")


if __name__ == "__main__":
    unittest.main()
