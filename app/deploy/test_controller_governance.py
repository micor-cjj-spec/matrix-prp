import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("controller_verifier", ROOT / "verify_controller.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
MANIFEST_PATH = ROOT / "controller-manifest.json"
EXAMPLE = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
SHA = EXAMPLE["approved_controller"]["sha256"]


class ProductionControllerGovernanceTests(unittest.TestCase):
    def test_approved_production_digest_format(self):
        self.assertRegex(SHA, r"^[a-f0-9]{64}$")
        self.assertEqual(EXAMPLE["approved_controller"]["path"], verifier.CONTROLLER_PATH)

    def test_valid_attestation(self):
        line = SHA + "  " + verifier.CONTROLLER_PATH + "\n"
        self.assertEqual(verifier.verify_response(EXAMPLE, line), SHA)

    def test_valid_attestation_without_newline(self):
        self.assertEqual(
            verifier.verify_response(EXAMPLE, SHA + "  " + verifier.CONTROLLER_PATH), SHA
        )

    def test_wrong_digest_is_rejected(self):
        with self.assertRaisesRegex(verifier.AttestationError, "drift"):
            verifier.verify_response(
                EXAMPLE, "0" * 64 + "  " + verifier.CONTROLLER_PATH + "\n"
            )

    def test_fail_closed_for_missing_and_noncanonical_status(self):
        variants = [
            "", "\n", "error: unknown command\n",
            SHA + "  /tmp/prp-release\n",
            SHA + " *" + verifier.CONTROLLER_PATH + "\n",
            "banner\n" + SHA + "  " + verifier.CONTROLLER_PATH + "\n",
            SHA + "  " + verifier.CONTROLLER_PATH + "\n" * 2,
            SHA + "  " + verifier.CONTROLLER_PATH + "\n" + SHA + "  " + verifier.CONTROLLER_PATH,
            SHA.upper() + "  " + verifier.CONTROLLER_PATH + "\n",
        ]
        for output in variants:
            with self.subTest(output=output), self.assertRaises(verifier.AttestationError):
                verifier.verify_response(EXAMPLE, output)

    def test_invalid_or_incomplete_manifest_fails_closed(self):
        candidates = [{}, {"schema_version": 2}, {"schema_version": 1},
          {"schema_version": 1, "approved_controller": {"path": "/tmp/x", "sha256": SHA}},
          {"schema_version": 1, "approved_controller": {"path": verifier.CONTROLLER_PATH, "sha256": ""}},
          {"schema_version": 1, "approved_controller": {"path": verifier.CONTROLLER_PATH, "sha256": "garbage"}}]
        for data in candidates:
            with self.subTest(data=data), self.assertRaises(verifier.AttestationError):
                verifier.approved_sha256(data)

    def test_cli_fails_and_succeeds_without_network_access(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "response.txt"
            file.write_text(SHA + "  " + verifier.CONTROLLER_PATH + "\n", encoding="utf-8")
            cmd = [sys.executable, str(ROOT / "verify_controller.py"),
                   "--manifest", str(MANIFEST_PATH), "--response", str(file)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            file.write_text("disabled\n", encoding="utf-8")
            rejected = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("verification failed", rejected.stderr)

    def test_gateway_only_exposes_one_fixed_read_only_command(self):
        contents = (ROOT / "ssh-gateway.sh").read_text(encoding="utf-8")
        self.assertIn(
            "controller-sha256) exec /usr/bin/sha256sum /usr/local/sbin/prp-release ;;",
            contents,
        )
        self.assertNotIn("sudo -n /usr/bin/sha256sum", contents)
        self.assertIn("Allowed: deploy, status, check, controller-sha256", contents)
        self.assertEqual(
            subprocess.run(["/bin/sh", "-n", str(ROOT / "ssh-gateway.sh")]).returncode, 0
        )


if __name__ == "__main__":
    unittest.main()
