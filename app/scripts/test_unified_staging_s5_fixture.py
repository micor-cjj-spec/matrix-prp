"""Execute the pinned historical S5 source with fake transport only, never a real helper."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import socket
import subprocess
import tempfile
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from unified_staging_s5_recovery import (assess_interrupted_journal, capture_baseline,
    persist_baseline_once, read_baseline, compare_baseline, BASELINE_FILE, build_offline_receipt)

SOURCE = Path(__file__).with_name("fixtures") / "unified_396_s5_operator.py.txt"
DIGEST = "2c199c8b0fae7bdaaae2a10cc3d06f2bfd8fd33ee8c096b9399d4ccb1eb0d04c"
IMAGES = {
    "backend": "sha256:396fc37f266ad8d197d074367d7a70ccdcf43f8c20909bfdc0119aa0dbdd3a89",
    "gateway": "sha256:f67163b616f1ee2fc931cc164934e5ddd5d89afd0b75c32cdb8a07b4b1999551",
    "mysql": "sha256:0f1a0ccadda3a1734d1db557e203ec58621d56fa248525016e85fe4f631311ec",
}
PATHS = {
    "/api/tasks": "task", "/api/records": "record",
    "/api/video/folders": "video", "/api/practice/subjects": "practice",
    "/api/finance/accounts": "account", "/api/finance/categories": "category",
    "/api/finance/transactions": "finance",
}
MODULES = {"task", "finance", "record", "video", "practice"}
CLEANUP_KEYS = {w + "_" + k for w in ("A", "B") for k in PATHS.values()}


class FakeHelper:
    BACKEND, GATEWAY, MYSQL = "backend", "gateway", "mysql"

    def __init__(self, work, fault):
        self.fault = fault
        self.CREDENTIAL_DIR = work / "credentials"
        self.CREDENTIAL_DIR.mkdir(mode=0o700)
        self.CREDENTIAL_FILE = self.CREDENTIAL_DIR / "a.json"
        self.CREDENTIAL_FILE.touch()
        (self.CREDENTIAL_DIR / "b.json").touch()
        self.credentials = {
            w: {"user_id": uid, "username": "fixture_" + w,
                "password": "fixture-password-" + w}
            for w, uid in (("A", 1), ("B", 2))
        }
        self.rows = {(w, kind): {} for w in ("A", "B") for kind in PATHS.values()}
        # Existing unrelated records must survive unchanged.
        self.rows["A", "task"][90] = {"id": 90, "title": "unrelated"}
        self.next_id = 100
        self.calls = []
        self.mutations = []
        self.fault_used = False

    def inspect_target(self):
        return {"backend": {"env": {
            "MATRIX_PRP_MCP_OAUTH_ISSUER": "https://auth-test.micor.top/realms/prp-mcp",
            "MATRIX_PRP_MCP_OAUTH_RESOURCE": "https://prp-test.micor.top/api/mcp",
        }}}

    def validate_target(self, metadata):
        if self.fault == "target":
            raise RuntimeError("STAGE_TARGET_MISMATCH")

    def _run(self, command, input_text=None):
        if command[:4] == ["docker", "inspect", "--format", "{{.Image}}"]:
            return "wrong-image" if self.fault == "image" else IMAGES[command[4]]
        if (command[:5] == ["docker", "exec", "-i", "mysql", "sh"]
                and input_text and input_text.startswith("START TRANSACTION READ ONLY;")
                and "flyway_schema_history" in input_text):
            return "30\n0" if self.fault == "schema" else "31\n0"
        raise AssertionError("unexpected fake command")

    def read_existing_credentials(self):
        who = {"a.json": "A", "b.json": "B"}[self.CREDENTIAL_FILE.name]
        if who == "B" and self.fault == "missing_b":
            raise RuntimeError("INVALID_B")
        return dict(self.credentials[who])

    def query_ordinary_identity_readonly(self, c):
        if c not in self.credentials.values():
            raise AssertionError("unknown synthetic identity")

    @staticmethod
    def valid_json_type(ctype):
        return ctype == "application/json"

    @staticmethod
    def ok(data):
        return 200, "application/json", {"code": "SUCCESS", "data": data}

    @staticmethod
    def denied():
        return 404, "application/json", None

    def http_json(self, path, *, method="GET", payload=None, token=None):
        self.calls.append((method, path))
        if path == "/api/auth/login" and method == "POST":
            w = next(w for w, c in self.credentials.items()
                     if payload == {"username": c["username"], "password": c["password"]})
            c = self.credentials[w]
            return self.ok({"user": {"id": c["user_id"], "username": c["username"],
                                     "administrator": self.fault == "admin"},
                            "tokenType": "Bearer", "token": "fake." + w + ".jwt"})
        w = {"fake.A.jwt": "A", "fake.B.jwt": "B"}[token]
        other = "B" if w == "A" else "A"
        if path == "/api/users/me" and method == "GET":
            c = self.credentials[w]
            return self.ok({"id": c["user_id"], "username": c["username"],
                            "administrator": False})
        if path.startswith("/api/finance/summary/monthly?month=") and method == "GET":
            exp = sum((Decimal(str(r["amount"])) for r in self.rows[w, "finance"].values()),
                      Decimal("0"))
            if self.fault == "finance_delta" and exp:
                exp += 1
            return self.ok({"income": "0", "expense": str(exp), "balance": str(-exp)})
        if path.startswith("/api/video/items?folderId=") or re.fullmatch(
                r"/api/practice/subjects/\d+/banks", path):
            if method != "GET":
                raise AssertionError("unexpected method")
            return self.denied()
        match = next((p for p in PATHS if path == p or path.startswith(p + "/")), None)
        if match is None:
            raise AssertionError("unexpected route")
        kind = PATHS[match]
        rows = self.rows[w, kind]
        if path == match and method == "GET":
            values = list(rows.values())
            if self.fault == "leak" and self.rows[other, kind]:
                values += [r for r in self.rows[other, kind].values() if r["id"] >= 100]
            return self.ok([dict(r) for r in values])
        if path == match and method == "POST":
            self.next_id += 1
            rid = self.next_id
            rows[rid] = dict(payload, id=rid)
            self.mutations.append((w, kind, method, rid))
            if self.fault == "lost_create" and not self.fault_used:
                self.fault_used = True
                raise OSError("simulated lost response after commit")
            if self.fault == "ambiguous" and not self.fault_used:
                self.fault_used = True
                self.next_id += 1
                rows[self.next_id] = dict(payload, id=self.next_id)
                raise OSError("simulated ambiguous create")
            return self.ok(dict(rows[rid]))
        rid = int(path[len(match) + 1:])
        if rid not in rows:
            if self.fault == "cross_owner" and method == "PUT" and rid in self.rows[other, kind]:
                return self.ok({})
            return self.denied()
        if rid < 100:
            raise AssertionError("attempted mutation of baseline row")
        if method == "PUT":
            rows[rid] = dict(payload, id=rid)
            self.mutations.append((w, kind, method, rid))
            return self.ok(dict(rows[rid]))
        if method == "DELETE":
            if self.fault == "cleanup":
                return 500, "application/json", None
            del rows[rid]
            self.mutations.append((w, kind, method, rid))
            return self.ok({})
        raise AssertionError("unexpected method")




class IntegratedFakeHelper(FakeHelper):
    """Capture the actual simulated preflight observations before first mutation.

    This class is deliberately test-only. It never imports the real transport.
    """
    def __init__(self, work, fault):
        super().__init__(work, fault)
        self.work = work
        self.actual_uid = os.geteuid()
        self.observed = {}
        self.observed_summaries = {}
        self.months = set()
        self.context = None
        self.sidecar_ready = False
        self.sidecar_failed = False

    def http_json(self, path, *, method="GET", payload=None, token=None):
        who = {"fake.A.jwt": "A", "fake.B.jwt": "B"}.get(token)
        if path != "/api/auth/login" and method in ("POST", "PUT", "DELETE"):
            if not self.sidecar_ready:
                if self.sidecar_failed:
                    raise RuntimeError("BASELINE_NOT_DURABLE")
                try:
                    journal = json.loads((self.work / "local-private-journal.json").read_text())
                    attempts = journal["attempted"]
                    if (method != "POST" or len(attempts) != 1
                            or attempts[0]["owner"] != who
                            or attempts[0]["kind"] != PATHS.get(path)
                            or attempts[0]["id"] is not None
                            or len(self.months) != 1 or self.mutations):
                        raise RuntimeError("BASELINE_ORDER_MISMATCH")
                    self.context = {
                        "run": journal["run"], "month": next(iter(self.months)),
                        "target": "https://prp-test.micor.top", "schema": 31,
                        "images": dict(IMAGES),
                        "owners": {w: self.credentials[w]["user_id"] for w in ("A", "B")},
                        "sourceSha256": DIGEST,
                    }
                    baseline = capture_baseline(self.context, self.observed, self.observed_summaries)
                    # Historical script mocks geteuid to 0; the sidecar must
                    # check the actual temporary directory owner instead.
                    with patch.object(os, "geteuid", return_value=self.actual_uid):
                        if self.fault == "baseline_io":
                            raise OSError("simulated persistence failure")
                        persist_baseline_once(self.work, baseline)
                        if read_baseline(self.work) != baseline:
                            raise RuntimeError("BASELINE_READBACK_MISMATCH")
                    self.sidecar_ready = True
                except Exception:
                    self.sidecar_failed = True
                    raise RuntimeError("BASELINE_NOT_DURABLE")
            if not self.sidecar_ready:
                raise RuntimeError("BASELINE_NOT_DURABLE")
        result = super().http_json(path, method=method, payload=payload, token=token)
        if not self.sidecar_ready and not self.sidecar_failed and method == "GET" and who:
            status, ctype, body = result
            if status == 200 and ctype == "application/json":
                if path in PATHS:
                    self.observed[who + "_" + PATHS[path]] = body["data"]
                elif path.startswith("/api/finance/summary/monthly?month="):
                    self.months.add(path.rsplit("=", 1)[1])
                    self.observed_summaries[who] = body["data"]
        return result

    def finish_receipt(self, report, journal):
        if not self.sidecar_ready:
            # No baseline means no eligible pass, even for an empty journal.
            return build_offline_receipt(report, journal, None, self.context, {}, {})
        if self.fault == "post_baseline_drift":
            self.rows["A", "task"][90]["title"] = "simulated drift after cleanup"
        if self.fault == "corrupt_sidecar":
            (self.work / BASELINE_FILE).write_text("{}")
        try:
            baseline = read_baseline(self.work)
        except (OSError, ValueError):
            baseline = None
        snapshots, summaries = {}, {}
        for who in ("A", "B"):
            for path, kind in PATHS.items():
                status, _, body = self.http_json(path, token="fake." + who + ".jwt")
                if status == 200:
                    snapshots[who + "_" + kind] = body["data"]
            status, _, body = self.http_json(
                "/api/finance/summary/monthly?month=" + self.context["month"],
                token="fake." + who + ".jwt")
            if status == 200:
                summaries[who] = body["data"]
        return build_offline_receipt(report, journal, baseline, self.context, snapshots, summaries)


def run_fixture(fault=None, *, integrated=False):
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DIGEST:
        raise AssertionError("historical source digest changed")
    with tempfile.TemporaryDirectory(prefix="prp-s62-fixture-") as tmp:
        work = Path(tmp)
        helper = (IntegratedFakeHelper if integrated else FakeHelper)(work, fault)
        output = io.StringIO()
        # Loader interception injects the fake helper instead of loading p420.py.
        fake_spec = types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda _: None))
        def forbid(*args, **kwargs):
            raise AssertionError("offline fixture attempted real network or process")
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(importlib.util, "spec_from_file_location", return_value=fake_spec))
            stack.enter_context(patch.object(importlib.util, "module_from_spec", return_value=helper))
            stack.enter_context(patch.object(os, "geteuid", return_value=0))
            stack.enter_context(patch.dict(os.environ, {"B_FILE": ""}))
            stack.enter_context(patch.object(socket, "socket", side_effect=forbid))
            stack.enter_context(patch.object(socket, "create_connection", side_effect=forbid))
            stack.enter_context(patch.object(subprocess, "Popen", side_effect=forbid))
            stack.enter_context(contextlib.redirect_stdout(output))
            try:
                exec(compile(raw, str(work / "cross_uat.py"), "exec"),
                     {"__file__": str(work / "cross_uat.py"), "__name__": "__main__"})
            except SystemExit as exc:
                exit_code = exc.code
            else:
                raise AssertionError("missing exit status")
        report = json.loads(output.getvalue())
        journal = json.loads((work / "local-private-journal.json").read_text())
        for text in (output.getvalue(), json.dumps(journal)):
            if "fixture-password" in text or "fake.A.jwt" in text or "fake.B.jwt" in text:
                raise AssertionError("credential leak")
        if integrated:
            helper.receipt = helper.finish_receipt(report, journal)
        return exit_code, report, helper, journal


class S5OfflineReuseTests(unittest.TestCase):
    def assert_review(self, fault, expected_failure=None):
        code, report, helper, journal = run_fixture(fault)
        self.assertEqual(code, 1)
        self.assertEqual(report["state"], "CROSS_MODULE_UAT_REVIEW_REQUIRED")
        if expected_failure:
            self.assertEqual(report["failure"], expected_failure)
        self.assertFalse(report["liveVerified"])
        self.assertFalse(report["productionAuthorized"])
        self.assertFalse(report["automatedRunnerEnabled"])
        return report, helper, journal

    def test_success_all_modules_and_cleanup(self):
        code, report, helper, journal = run_fixture()
        self.assertEqual(code, 0)
        self.assertEqual(report["state"], "CROSS_MODULE_UAT_PASS")
        self.assertEqual(set(report["moduleResults"]), MODULES)
        self.assertEqual(set(report["cleanup"]), CLEANUP_KEYS)
        self.assertEqual(set(report["cleanup"].values()), {"API_ABSENT"})
        self.assertTrue(report["visibleBaselineRestored"])
        self.assertEqual(helper.rows["A", "task"], {90: {"id": 90, "title": "unrelated"}})
        self.assertEqual(sum(len(v) for v in helper.rows.values()), 1)
        self.assertEqual(sum(m[2] == "POST" for m in helper.mutations), 14)
        self.assertEqual(sum(m[2] == "DELETE" for m in helper.mutations), 14)
        self.assertFalse(report["createdAccounts"])
        self.assertFalse(report["healthTestsExecuted"])
        self.assertFalse(report["aiProviderCalled"])
        self.assertFalse(report["databaseWritesDirect"])
        self.assertFalse(report["automatedRunnerEnabled"])
        self.assertFalse(report["productionAuthorized"])
        self.assertFalse(report["liveVerified"])

    def test_bad_preflight_never_writes(self):
        for fault, reason in (("target", "STAGE_TARGET_MISMATCH"),
                              ("image", "STAGE_IMAGE_MISMATCH"),
                              ("schema", "STAGE_SCHEMA_MISMATCH"),
                              ("missing_b", "B_CREDENTIAL_FILE_NOT_UNIQUELY_VERIFIED"),
                              ("admin", "LOGIN_IDENTITY_MISMATCH")):
            with self.subTest(fault=fault):
                report, helper, _ = self.assert_review(fault, reason)
                self.assertEqual(helper.mutations, [])
                self.assertEqual(report["cleanup"], {})

    def test_cross_owner_acceptance_is_failure(self):
        report, _, _ = self.assert_review("cross_owner", "CROSS_OWNER_DENIAL_FAILED")
        self.assertTrue(report["visibleBaselineRestored"])
        self.assertNotIn("task", report["moduleResults"])

    def test_cross_owner_list_leak_is_failure(self):
        self.assert_review("leak")

    def test_finance_delta_mismatch_is_failure(self):
        report, _, _ = self.assert_review("finance_delta", "MONTHLY_FINANCE_DELTA_MISMATCH")
        self.assertTrue(report["visibleBaselineRestored"])

    def test_lost_create_response_cleanup_by_marker(self):
        report, helper, journal = self.assert_review("lost_create", "LOCAL_OR_API_ERROR")
        self.assertEqual(report["cleanup"], {"A_task": "API_ABSENT"})
        self.assertTrue(report["visibleBaselineRestored"])
        self.assertIsNone(journal["attempted"][0]["id"])
        self.assertEqual(sum(len(v) for v in helper.rows.values()), 1)

    def test_ambiguous_create_refuses_unsafe_cleanup(self):
        report, helper, _ = self.assert_review("ambiguous", "LOCAL_OR_API_ERROR")
        self.assertEqual(report["cleanup"], {"A_task": "REVIEW_REQUIRED"})
        self.assertFalse(report["visibleBaselineRestored"])
        self.assertFalse(any(m[2] == "DELETE" for m in helper.mutations))

    def test_cleanup_failure_never_passes(self):
        report, _, _ = self.assert_review("cleanup")
        self.assertIn("REVIEW_REQUIRED", report["cleanup"].values())
        self.assertFalse(report["visibleBaselineRestored"])


class S5RecoveryReviewTests(unittest.TestCase):
    def setUp(self):
        self.run = "UAT396-0123456789abcdef"
        self.marker = self.run + "-A"
        self.journal = {
            "run": self.run, "phase": "task",
            "attempted": [{"owner": "A", "kind": "task", "marker": self.marker, "id": 101}],
            "results": {}, "cleanup": {},
        }
        self.snapshots = {"A_task": [], "B_task": []}

    def assess(self):
        result = assess_interrupted_journal(self.journal, self.snapshots)
        for k in ("baselineRestored", "liveVerified", "cleanupAuthorized", "productionAuthorized"):
            self.assertIs(result[k], False)
        self.assertNotIn(self.marker, json.dumps(result))
        return result

    def test_known_id_residual(self):
        self.snapshots["A_task"] = [{"id": 101, "title": self.marker}]
        self.assertEqual(self.assess()["entries"], {"A_task": "KNOWN_ID_REMAINS"})

    def test_unconfirmed_create_residual(self):
        self.journal["attempted"][0]["id"] = None
        self.snapshots["A_task"] = [{"id": 101, "title": self.marker}]
        self.assertEqual(self.assess()["entries"], {"A_task": "UNCONFIRMED_CREATE_REMAINS"})

    def test_id_and_marker_conflicts(self):
        for row in ({"id": 101, "title": "unrelated"}, {"id": 102, "title": self.marker}):
            with self.subTest(row=row):
                self.snapshots["A_task"] = [row]
                self.assertEqual(self.assess()["entries"], {"A_task": "ID_MARKER_CONFLICT"})

    def test_ambiguous_marker(self):
        self.snapshots["A_task"] = [{"id": i, "title": self.marker} for i in (101, 102)]
        self.assertEqual(self.assess()["entries"], {"A_task": "AMBIGUOUS_MARKER"})

    def test_cross_owner_conflict(self):
        for row in ({"id": 101, "title": "unrelated"}, {"id": 102, "title": self.marker}):
            with self.subTest(row=row):
                self.snapshots["B_task"] = [row]
                self.assertEqual(self.assess()["entries"], {"A_task": "CROSS_OWNER_CONFLICT"})

    def test_missing_snapshot_or_duplicate_id(self):
        del self.snapshots["B_task"]
        self.assertEqual(self.assess()["state"], "INCOMPLETE_SNAPSHOTS")
        self.snapshots["B_task"] = [{"id": 2}, {"id": 2}]
        self.assertEqual(self.assess()["state"], "INVALID_SNAPSHOT")

    def test_invalid_journal(self):
        self.journal["attempted"][0]["marker"] = "wrong"
        self.assertEqual(self.assess()["state"], "INVALID_JOURNAL")
        self.journal["attempted"][0]["marker"] = self.marker
        self.journal["attempted"].append(dict(self.journal["attempted"][0]))
        self.assertEqual(self.assess()["state"], "INVALID_JOURNAL")

    def test_absent_is_not_baseline_restoration(self):
        self.snapshots["A_task"] = [{"id": 90, "title": "unrelated"}]
        self.assertEqual(self.assess()["state"], "NO_MARKERS_OBSERVED")

    def test_historical_failed_cleanup_journal(self):
        code, report, helper, journal = run_fixture("cleanup")
        self.assertEqual(code, 1)
        result = assess_interrupted_journal(journal, {
            w + "_" + k: list(rows.values()) for (w, k), rows in helper.rows.items()
        })
        self.assertEqual(result["state"], "RECOVERY_REVIEW_REQUIRED")
        self.assertEqual(set(result["entries"]), set(report["cleanup"]))
        self.assertIn("KNOWN_ID_REMAINS", result["entries"].values())
        self.assertFalse(result["cleanupAuthorized"])

    def test_historical_cleaned_journal(self):
        code, _, helper, journal = run_fixture()
        self.assertEqual(code, 0)
        result = assess_interrupted_journal(journal, {
            w + "_" + k: list(rows.values()) for (w, k), rows in helper.rows.items()
        })
        self.assertEqual(result["state"], "NO_MARKERS_OBSERVED")
        self.assertEqual(set(result["entries"]), CLEANUP_KEYS)
        self.assertFalse(result["baselineRestored"])


class S5BaselineTests(unittest.TestCase):
    def setUp(self):
        self.context = {"run": "UAT396-0123456789abcdef", "month": "2026-11",
                        "target": "https://prp-test.micor.top", "schema": 31,
                        "images": dict(IMAGES), "owners": {"A": 1, "B": 2},
                        "sourceSha256": DIGEST}
        self.snapshots = {k: [] for k in CLEANUP_KEYS}
        self.snapshots["A_task"] = [{"id": 90, "title": "unrelated-private"},
                                    {"id": 91, "title": "second"}]
        self.summaries = {w: {"income": "0.00", "expense": "0", "balance": "0"}
                          for w in ("A", "B")}
        self.baseline = capture_baseline(self.context, self.snapshots, self.summaries)

    def compare(self):
        result = compare_baseline(self.baseline, self.context, self.snapshots, self.summaries)
        for k in ("baselineRestored", "liveVerified", "cleanupAuthorized", "productionAuthorized"):
            self.assertIs(result[k], False)
        return result

    def test_private_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            persist_baseline_once(tmp, self.baseline)
            file = Path(tmp) / BASELINE_FILE
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(read_baseline(tmp), self.baseline)
            self.assertNotIn("unrelated-private", file.read_text())
            self.assertNotIn(self.context["run"], file.read_text())
            with self.assertRaises(FileExistsError):
                persist_baseline_once(tmp, self.baseline)
            self.assertEqual(read_baseline(tmp), self.baseline)
            self.assertEqual(list(Path(tmp).iterdir()), [file])

    def test_complete_match_and_row_order(self):
        self.snapshots["A_task"].reverse()
        self.summaries["A"]["income"] = 0
        self.assertEqual(self.compare()["state"], "BASELINE_DIGESTS_MATCH")

    def test_changed_existing_row_detected(self):
        self.snapshots["A_task"][0]["title"] = "changed"
        self.assertEqual(self.compare()["entries"], {"A_task": "CHANGED"})

    def test_finance_summary_exact_decimal(self):
        self.summaries["B"]["expense"] = "0.00000000000000000000000000001"
        self.assertEqual(self.compare()["entries"], {"finance_summary_B": "CHANGED"})

    def test_missing_and_duplicate_lists(self):
        self.snapshots["A_task"].append(dict(self.snapshots["A_task"][0]))
        self.assertEqual(self.compare()["state"], "INVALID_BASELINE_OBSERVATION")
        del self.snapshots["B_task"]
        self.assertEqual(self.compare()["state"], "INVALID_BASELINE_OBSERVATION")

    def test_context_binding(self):
        for key, value in (("month", "2026-12"), ("owners", {"A": 2, "B": 1}),
                           ("images", {**IMAGES, "backend": "sha256:" + "1"*64})):
            with self.subTest(key=key):
                original = self.context[key]
                self.context[key] = value
                self.assertEqual(self.compare()["state"], "BASELINE_CONTEXT_MISMATCH")
                self.context[key] = original

    def test_invalid_context(self):
        self.context["target"] = "https://micor.top"
        self.assertEqual(self.compare()["state"], "INVALID_BASELINE_OBSERVATION")

    def test_tamper_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            persist_baseline_once(tmp, self.baseline)
            file = Path(tmp) / BASELINE_FILE
            data = json.loads(file.read_text())
            data["lists"]["A_task"] = "0"*64
            file.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "BASELINE_DIGEST_MISMATCH"):
                read_baseline(tmp)
            file.write_text("{")
            with self.assertRaises(ValueError):
                read_baseline(tmp)

    def test_symlink_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / BASELINE_FILE
            file.symlink_to(Path(tmp) / "missing")
            with self.assertRaises(OSError):
                read_baseline(tmp)
            with self.assertRaises(FileExistsError):
                persist_baseline_once(tmp, self.baseline)
            file.unlink()
            persist_baseline_once(tmp, self.baseline)
            file.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "INVALID_BASELINE_FILE"):
                read_baseline(tmp)

    def test_invalid_summary(self):
        self.summaries["B"]["expense"] = "NaN"
        self.assertEqual(self.compare()["state"], "INVALID_BASELINE_OBSERVATION")


class S5IntegratedRehearsalTests(unittest.TestCase):
    def run_integrated(self, fault=None):
        code, report, helper, journal = run_fixture(fault, integrated=True)
        receipt = helper.receipt
        self.assertEqual(receipt["kind"], "S5_OFFLINE_REHEARSAL")
        for key in ("liveVerified", "baselineRestored", "cleanupAuthorized",
                    "automatedRunnerEnabled", "productionAuthorized", "deploymentAuthorized"):
            self.assertIs(receipt[key], False)
        serialized = json.dumps(receipt)
        for private in ("UAT396-", "fixture-password", "fake.A.jwt", "unrelated"):
            self.assertNotIn(private, serialized)
        return code, report, helper, journal, receipt

    def test_integrated_pass(self):
        code, _, helper, _, receipt = self.run_integrated()
        self.assertEqual(code, 0)
        self.assertTrue(helper.sidecar_ready)
        self.assertEqual(receipt["state"], "OFFLINE_REHEARSAL_PASS")
        self.assertEqual(receipt["modulesPassed"], 5)
        self.assertEqual(receipt["cleanupObservedAbsent"], 14)
        self.assertEqual(receipt["baselineState"], "BASELINE_DIGESTS_MATCH")

    def test_persistence_failure_blocks_first_business_write(self):
        code, _, helper, _, receipt = self.run_integrated("baseline_io")
        self.assertEqual(code, 1)
        self.assertEqual(helper.mutations, [])
        self.assertFalse(helper.sidecar_ready)
        self.assertEqual(receipt["state"], "OFFLINE_REVIEW_REQUIRED")

    def test_preflight_failure_has_no_baseline_or_writes(self):
        code, _, helper, _, receipt = self.run_integrated("schema")
        self.assertEqual(code, 1)
        self.assertFalse(helper.sidecar_ready)
        self.assertEqual(helper.mutations, [])
        self.assertEqual(receipt["state"], "OFFLINE_REVIEW_REQUIRED")

    def test_lost_create_restored_but_run_not_passed(self):
        code, _, _, _, receipt = self.run_integrated("lost_create")
        self.assertEqual(code, 1)
        self.assertEqual(receipt["baselineState"], "BASELINE_DIGESTS_MATCH")
        self.assertEqual(receipt["recoveryState"], "NO_MARKERS_OBSERVED")
        self.assertEqual(receipt["state"], "OFFLINE_REVIEW_REQUIRED")

    def test_failed_cleanup_and_ambiguous_create(self):
        for fault in ("cleanup", "ambiguous"):
            with self.subTest(fault=fault):
                code, _, _, _, receipt = self.run_integrated(fault)
                self.assertEqual(code, 1)
                self.assertEqual(receipt["baselineState"], "BASELINE_DIFFERENCE_OBSERVED")
                self.assertEqual(receipt["recoveryState"], "RECOVERY_REVIEW_REQUIRED")
                self.assertEqual(receipt["state"], "OFFLINE_REVIEW_REQUIRED")

    def test_cross_owner_failure_never_promoted(self):
        code, _, _, _, receipt = self.run_integrated("cross_owner")
        self.assertEqual(code, 1)
        self.assertEqual(receipt["baselineState"], "BASELINE_DIGESTS_MATCH")
        self.assertEqual(receipt["state"], "OFFLINE_REVIEW_REQUIRED")

    def test_drift_after_historical_success(self):
        code, _, _, _, receipt = self.run_integrated("post_baseline_drift")
        self.assertEqual(code, 0)
        self.assertEqual(receipt["baselineState"], "BASELINE_DIFFERENCE_OBSERVED")
        self.assertEqual(receipt["state"], "OFFLINE_REVIEW_REQUIRED")

    def test_corrupt_sidecar_after_historical_success(self):
        code, _, _, _, receipt = self.run_integrated("corrupt_sidecar")
        self.assertEqual(code, 0)
        self.assertEqual(receipt["baselineState"], "INVALID_BASELINE_OBSERVATION")
        self.assertEqual(receipt["state"], "OFFLINE_REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
