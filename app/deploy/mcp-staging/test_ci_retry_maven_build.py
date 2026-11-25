"""Synthetic process-level tests; never contact Maven or Docker."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HELPER = Path(__file__).with_name("ci_retry_maven_build.sh")
NETWORK = "Non-resolvable parent POM: Could not transfer artifact; status code: 429"
WRAPPER = "wget: Failed to fetch https://repo.maven.apache.org/apache-maven-3.9.16-bin.zip"

class RetryTests(unittest.TestCase):
    def execute(self, messages, mode="E2E", runner=True):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            counter = root / "counter"
            fake = root / "fake"
            fake.write_text("#!/bin/bash\nset -eu\nn=0\nif [[ -f \"$COUNT\" ]]; then n=$(<\"$COUNT\"); fi\nn=$((n+1))\nprintf '%s' \"$n\" > \"$COUNT\"\ncase \"$n\" in\n" +
                "".join(f"{i}) printf '%s\\n' {__import__('shlex').quote(m)}; exit {0 if m == 'PASS' else 17};;\n" for i,m in enumerate(messages,1)) +
                "*) exit 99;;\nesac\n")
            fake.chmod(0o700)
            sleep = root / "sleep"
            sleep.write_text("#!/bin/bash\nexit 0\n")
            sleep.chmod(0o700)
            env = dict(os.environ, GITHUB_ACTIONS="true" if runner else "false",
                       RUNNER_OS="Linux", RUNNER_TEMP=str(root), GITHUB_RUN_ID="123",
                       COUNT=str(counter), PATH=str(root)+":"+os.environ["PATH"])
            p = subprocess.run(["bash", str(HELPER), mode, str(fake)],
                               env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(list(root.glob("prp-maven-build.*")), [])
            return p, int(counter.read_text()) if counter.exists() else 0

    def test_success_no_retry(self):
        p,n = self.execute(["PASS"])
        self.assertEqual((p.returncode,n),(0,1))

    def test_network_retries_only_until_success(self):
        for mode in ("E2E","OCI"):
            p,n = self.execute([NETWORK,NETWORK,"PASS"],mode)
            self.assertEqual((p.returncode,n),(0,3))
            self.assertIn("ATTEMPT=2",p.stderr)
            self.assertNotIn("Non-resolvable",p.stderr)

    def test_exhaustion_is_failure(self):
        p,n = self.execute([NETWORK]*3,"OCI")
        self.assertEqual((p.returncode,n),(17,3))
        self.assertIn("OCI_DIAG_MAVEN_BUILD_CATEGORY=DEPENDENCY_OR_NETWORK",p.stderr)

    def test_wrapper_only_in_e2e(self):
        p,n = self.execute([WRAPPER,"PASS"])
        self.assertEqual((p.returncode,n),(0,2))
        p,n = self.execute([WRAPPER,"PASS"],"OCI")
        self.assertEqual((p.returncode,n),(17,1))

    def test_generic_resolution_without_transport_not_retried(self):
        p,n = self.execute(["Could not resolve dependencies: absent artifact","PASS"])
        self.assertEqual((p.returncode,n),(17,1))

    def test_hard_failures_override_network(self):
        for hard in ("COMPILATION ERROR","checksum mismatch","Permission denied",
                     "No space left on device","OutOfMemoryError","status code: 404",
                     "Tests run: 5, Failures: 1, Errors: 0"):
            with self.subTest(hard=hard):
                p,n = self.execute([NETWORK+"\n"+hard,"PASS"])
                self.assertEqual((p.returncode,n),(17,1))

    def test_unknown_and_redaction(self):
        p,n = self.execute(["PRIVATE_TEST_SENTINEL","PASS"])
        self.assertEqual((p.returncode,n),(17,1))
        self.assertNotIn("PRIVATE_TEST_SENTINEL",p.stdout+p.stderr)
        self.assertIn("UNKNOWN",p.stderr)

    def test_runner_required(self):
        p,n = self.execute(["PASS"],runner=False)
        self.assertEqual((p.returncode,n),(2,0))

if __name__ == "__main__":
    unittest.main()
