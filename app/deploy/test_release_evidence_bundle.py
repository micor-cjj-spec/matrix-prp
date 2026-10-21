"""ENG-03G: never turn synthetically matched hashes into production approval."""
from contextlib import redirect_stdout
from io import StringIO
import copy
import json
from pathlib import Path
import tempfile
import unittest

from review_release_evidence_bundle import GATES, verify_bundle, main
from test_running_release_evidence import (
    FakeEvidenceFixture, COMMIT, DIGEST, metadata,
)


CANDIDATE_COMMIT = "e" * 40
CANDIDATE_DIGEST = "f" * 64
CHECKS = {
    "localhost_health": "PASS", "unauthorized_rejected": "PASS",
    "login_and_user_identity": "PASS", "finance_write_read": "PASS",
    "tenant_isolation": "PASS",
}


def ci_receipt(label, commit, digest):
    return {
        "schema_version": 1,
        "classification": "CI_SYNTHETIC_JAR_HTTP_PROBE",
        "production_deployment_attested": False,
        "production_authorized": False,
        "label": label,
        "source_commit": commit,
        "jar_sha256": digest,
        "checks": CHECKS.copy(),
    }


def fixture_inputs(fixture):
    observed = fixture.gather()
    candidate = dict(metadata())
    candidate["id"] = "r987654321-1"
    candidate["commit"] = CANDIDATE_COMMIT
    candidate["files"] = dict(candidate["files"], **{"backend.jar": CANDIDATE_DIGEST})
    baseline = ci_receipt("baseline", COMMIT, DIGEST)
    current = ci_receipt("candidate", CANDIDATE_COMMIT, CANDIDATE_DIGEST)
    return [observed, metadata(), json.loads(fixture.manifest), candidate, baseline, current]


def verify_json(items):
    return verify_bundle(*(json.dumps(x, sort_keys=True).encode() for x in items))


class ReleaseEvidenceBundleTests(unittest.TestCase):
    def test_consistent_inputs_are_still_hard_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            report = verify_json(fixture_inputs(fixture))
        self.assertEqual(report["classification"], "PRODUCTION_REVIEW_BLOCKED")
        self.assertFalse(report["production_authorized"])
        self.assertFalse(report["publication_gate_passed"])
        self.assertFalse(report["live_host_independently_attested"])
        self.assertFalse(report["trusted_artifact_provenance_attested"])
        self.assertFalse(report["real_backup_rehearsal_completed"])
        self.assertTrue(report["runtime_jar_matches_supplied_ci_baseline"])
        self.assertEqual(set(report["approval_gates"]), set(GATES))
        self.assertNotIn("PASS", report["approval_gates"].values())
        self.assertEqual(len(report["reviewed_inputs_sha256"]), 6)

    def test_main_baseline_mismatch_is_visible_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            inputs = fixture_inputs(fixture)
            inputs[4]["source_commit"] = "9" * 40
            result = verify_json(inputs)
        self.assertFalse(result["runtime_jar_matches_supplied_ci_baseline"])
        self.assertEqual(
            result["approval_gates"]["P5_REAL_PREVIOUS_AND_CANDIDATE_BINARY_COMPATIBILITY"],
            "BLOCKED_BASELINE_NOT_RUNNING_RELEASE")

    def test_forged_ci_or_release_metadata_rejected(self):
        edits = [
            (4, lambda x: x.update(classification="PRODUCTION_ATTESTED")),
            (4, lambda x: x.update(label="candidate")),
            (4, lambda x: x.update(production_authorized=True)),
            (4, lambda x: x.update(production_deployment_attested=True)),
            (4, lambda x: x["checks"].update(tenant_isolation="SKIPPED")),
            (4, lambda x: x["checks"].update(secret="token")),
            (4, lambda x: x.update(jar_sha256="xyz")),
            (4, lambda x: x.update(source_commit="invalid")),
            (5, lambda x: x.update(jar_sha256="0" * 64)),
            (5, lambda x: x.update(source_commit=COMMIT)),
            (5, lambda x: x.update(production_authorized=True)),
            (3, lambda x: x["files"].update(**{"backend.jar": "0" * 64})),
            (3, lambda x: x.update(commit=COMMIT)),
            (3, lambda x: x.update(id=metadata()["id"])),
            (3, lambda x: x.update(schema_version=22)),
            (2, lambda x: x["approved_controller"].update(sha256="0" * 64)),
            (0, lambda x: x["release"].update(commit="b" * 40)),
            (0, lambda x: x.update(production_authorized=True)),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            original = fixture_inputs(fixture)
            for index, edit in edits:
                changed = copy.deepcopy(original)
                edit(changed[index])
                with self.subTest(index=index, edit=str(edit)), self.assertRaises(ValueError):
                    verify_json(changed)

    def test_duplicate_keys_unknown_receipts_and_oversized_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = FakeEvidenceFixture(tmp)
            inputs = fixture_inputs(fixture)
            raws = [json.dumps(x, sort_keys=True).encode() for x in inputs]
            for altered_index, data in (
                (4, b'{"schema_version":1,"schema_version":2}'),
                (5, b"{" + b" " * 9000 + b"}"),
                (3, b"{}"),
                (0, b'{"secret":"private"}'),
            ):
                bad = raws.copy()
                bad[altered_index] = data
                with self.subTest(index=altered_index), self.assertRaises(ValueError):
                    verify_bundle(*bad)

    def test_cli_has_no_approval_token_or_sensitive_failure_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fixture = FakeEvidenceFixture(tmp)
            vals = fixture_inputs(fixture)
            params = [
                ("host-observation", "host.json"),
                ("deployed-release", "installed-release.json"),
                ("controller-manifest", "manifest.json"),
                ("candidate-release", "candidate.json"),
                ("baseline-ci-receipt", "baseline.json"),
                ("candidate-ci-receipt", "candidate-ci.json"),
            ]
            args = []
            for (name, file), data in zip(params, vals):
                p = folder / file
                p.write_text(json.dumps(data, sort_keys=True))
                args.extend(("--" + name, str(p)))
            buf = StringIO()
            with redirect_stdout(buf):
                self.assertEqual(main(args), 0)
            parsed = json.loads(buf.getvalue())
            self.assertEqual(parsed["classification"], "PRODUCTION_REVIEW_BLOCKED")
            self.assertFalse(parsed["publication_gate_passed"])
            (folder / "baseline.json").write_text('{"password":"very-private"}')
            buf = StringIO()
            with redirect_stdout(buf):
                self.assertEqual(main(args), 2)
            self.assertNotIn("very-private", buf.getvalue())
            self.assertEqual(json.loads(buf.getvalue())["classification"], "EVIDENCE_REJECTED")


if __name__ == "__main__":
    unittest.main()
