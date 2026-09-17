"""Exercise the interactive Sigma setup with local fixtures and a stubbed clone."""

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def extract_function(source, name):
    return source[source.index(f"{name}() {{") :].split("\n}", 1)[0] + "\n}"


class TestSigmaRepoSetup(unittest.TestCase):
    def run_setup(self, initial, answer="example/rules", writer_override=""):
        source = (ROOT / "setup.sh").read_text()
        functions = "\n".join(
            extract_function(source, name)
            for name in ("prompt_yes_no", "prompt_input", "handle_sigma_repo_setup")
        )
        # Stay inside the checkout; never read or write the operator's .env.
        with tempfile.TemporaryDirectory(prefix=".sigma-setup-test-", dir=ROOT) as directory:
            work = Path(directory) / "work"
            work.mkdir()
            fixture = work / ".env"
            if initial is not None:
                fixture.write_text(initial)
            script = f'''
set -eu
source "$1/scripts/startup_common.sh"
NON_INTERACTIVE=false
CYAN= NC= YELLOW=
print_status() {{ printf 'INFO: %s\\n' "$1"; }}
print_warning() {{ printf 'WARNING: %s\\n' "$1"; }}
print_header() {{ :; }}
git() {{ [[ "$1" == clone ]]; }}
{functions}
{writer_override}
handle_sigma_repo_setup
'''
            result = subprocess.run(
                ["bash", "-c", script, "test-setup", str(ROOT)],
                cwd=work,
                input=f"y\n{answer}\n",
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout, fixture.read_text() if fixture.exists() else None

    def test_fresh_template_records_selection(self):
        template = (ROOT / ".env.example").read_text()
        self.assertIn("GITHUB_REPO=", template.splitlines())
        output, content = self.run_setup(template)
        self.assertIn("GITHUB_REPO=example/rules", content.splitlines())
        self.assertIn("Updated .env", output)

    def test_appends_missing_key(self):
        output, content = self.run_setup("OTHER=value\n")
        self.assertEqual(content, "OTHER=value\nGITHUB_REPO=example/rules\n")
        self.assertIn("Updated .env", output)

    def test_replaces_existing_key(self):
        output, content = self.run_setup("GITHUB_REPO=old/rules\nOTHER=value\n")
        self.assertEqual(content, "GITHUB_REPO=example/rules\nOTHER=value\n")
        self.assertIn("Updated .env", output)

    def test_accepted_default_is_persisted(self):
        output, content = self.run_setup("GITHUB_REPO=\n", answer="")
        self.assertEqual(content, "GITHUB_REPO=your-username/Huntable-SIGMA-Rules\n")
        self.assertIn("Updated .env", output)

    def test_unchanged_selection_does_not_claim_update(self):
        initial = "GITHUB_REPO=example/rules\n"
        output, content = self.run_setup(initial)
        self.assertEqual(content, initial)
        self.assertNotIn("Updated .env", output)
        self.assertIn("already configured", output)

    def test_failed_and_silent_noop_writes_warn(self):
        for status in (0, 1):
            with self.subTest(writer_status=status):
                output, content = self.run_setup(
                    "GITHUB_REPO=\n",
                    writer_override=f"startup_set_env_key() {{ return {status}; }}",
                )
                self.assertEqual(content, "GITHUB_REPO=\n")
                self.assertIn("WARNING: Could not update .env GITHUB_REPO", output)
                self.assertNotIn("Updated .env", output)

    def test_missing_env_warns(self):
        output, content = self.run_setup(None)
        self.assertIsNone(content)
        self.assertIn("WARNING: Could not update .env GITHUB_REPO", output)
        self.assertNotIn("Updated .env", output)

    def test_sed_failure_warns_without_aborting_setup(self):
        output, content = self.run_setup(
            "GITHUB_REPO=\n", writer_override="sed() { return 1; }"
        )
        self.assertEqual(content, "GITHUB_REPO=\n")
        self.assertIn("WARNING: Could not update .env GITHUB_REPO", output)
        self.assertNotIn("Updated .env", output)


if __name__ == "__main__":
    unittest.main()
