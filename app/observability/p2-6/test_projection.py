"""Synthetic fixtures only. No live API, token, executor or network."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import unittest
from unittest.mock import patch

from projection import (REPO, WORKFLOW, MCP_GROUPS, MODULES, FALSE_FLAGS, CHECKS,
                        STATES, MAX_BYTES, project, prometheus)

NOW = 1795680000
SHA = "a" * 40
OTHER = "b" * 40


def ts(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dump(v):
    return json.dumps(v, separators=(",", ":")).encode()


def page(key, items, total=None, number=1, status=200, at=NOW-1):
    return {"page": number, "http_status": status, "received_at": at,
            "body": {"total_count": len(items) if total is None else total, key: items}}


def run(id=101, attempt=1, status="completed", conclusion="success", created=NOW-80):
    return {"id": id, "run_attempt": attempt, "path": WORKFLOW, "head_sha": SHA,
            "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO},
            "created_at": ts(created), "updated_at": ts(NOW-3), "status": status,
            "conclusion": conclusion, "html_url": "private-marker-url"}


def job(i, name, status="completed", conclusion="success", run_id=101, attempt=1):
    return {"id": i, "name": name, "run_id": run_id, "run_attempt": attempt, "head_sha": SHA,
            "status": status, "conclusion": conclusion,
            "started_at": ts(NOW-60) if status != "queued" else None,
            "completed_at": ts(NOW-30) if status == "completed" else None,
            "steps": [{"name": "private-marker-token"}]}


def bind_receipt(v):
    v.pop("binding_digest", None)
    encoded = json.dumps({"domain": "PRP_S63_S5_ADVISORY_V1", "evidence": v},
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    v["binding_digest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return v


def regression():
    return bind_receipt({"schema_version": 1, "source": "offline_simulation", "state": "BLOCKED",
            "repository": REPO, "environment": "prp-unified-396", "issue": 396,
            "execution_mode": "OFFLINE_SIMULATION", "candidate": {"repository": REPO,
                "commit": SHA, "artifact_digest": "sha256:" + "d"*64, "schema": 31},
            "window": dict(zip(("runtime_before_at", "started_at", "finished_at", "runtime_after_at"),
                               (NOW-90, NOW-80, NOW-20, NOW-10))),
            "module_results": dict.fromkeys(MODULES, "pass"),
            "cleanup_results": {a+"_"+m:"pass" for a in ("A","B") for m in MODULES|{"account","category"}},
            "api_visible_baseline_matched_claimed": True,
            "journal_recorded_mutation_outcomes": {"recorded": 58, "http_200": 38, "http_denied": 20,
                                                  "unknown_or_pending": 0, "other": 0},
            "regression_complete_claimed": True, **dict.fromkeys(FALSE_FLAGS, False)})


def fixture():
    jobs = [job(i+1, n) for i,n in enumerate(MCP_GROUPS)]
    jobs.append(job(6, "backend-tests private-marker-branch"))
    return {"expected_sha": SHA, "observed_at": NOW-1,
            "run_pages": [page("workflow_runs", [run()])],
            "job_pages": [page("jobs", jobs[:3], 6), page("jobs", jobs[3:], 6, 2)],
            "release": {"commit": SHA, "checks": {**dict.fromkeys(CHECKS, "pass"),
                         "production_smoke": "pending"}, "publication_hold": True,
                         "deployed_commit": None}, "regression": regression()}


class ProjectionTests(unittest.TestCase):
    def result(self, v):
        return project(dump(v), NOW)

    def bad(self, v, reason="invalid"):
        a = self.result(v)
        self.assertFalse(a["fresh"])
        self.assertEqual(a["reason"], reason)
        self.assertNotIn("jobs", a)
        self.assertNotIn("release_state_claim", a)
        self.assertIs(a["live_verified"], False)
        self.assertNotIn("prp_ci_jobs{", prometheus(dump(v), NOW))

    def test_baseline(self):
        v = self.result(fixture())
        self.assertTrue(v["fresh"])
        self.assertEqual(v["jobs"]["all"]["success"], 6)
        self.assertEqual(v["jobs"]["mcp"]["success"], 5)
        self.assertEqual(v["duration_seconds"], {"all":180,"mcp":150})
        self.assertEqual(v["run_state"], "success")
        self.assertEqual(v["release_state_claim"], "HELD")
        self.assertEqual(v["regression_claim"], "offline_claim_complete")
        self.assertFalse(v["deployment_authorized"])

    def test_release_ready_is_not_live(self):
        v = fixture(); v["release"]["publication_hold"] = False
        a = self.result(v)
        self.assertEqual(a["release_state_claim"], "READY_NOT_LIVE")
        self.assertFalse(a["live_verified"])

    def test_live_claim_never_verified(self):
        v = fixture(); v["release"].update(publication_hold=False, deployed_commit=SHA)
        v["release"]["checks"]["production_smoke"] = "pass"
        a = self.result(v)
        self.assertEqual(a["release_state_claim"], "LIVE_CLAIMED_UNVERIFIED")
        self.assertFalse(a["runtime_verified"])
        self.assertFalse(a["live_verified"])

    def test_unmatched_deployed_commit_blocked(self):
        v = fixture(); v["release"].update(publication_hold=False, deployed_commit=OTHER)
        v["release"]["checks"]["production_smoke"] = "pass"
        self.assertEqual(self.result(v)["release_state_claim"], "BLOCKED")

    def test_missing_release_and_regression(self):
        v = fixture(); v.update(release=None, regression=None)
        a = self.result(v)
        self.assertTrue(a["fresh"])
        self.assertEqual(a["release_state_claim"], "missing")
        self.assertEqual(a["regression_claim"], "missing")

    def test_status_mapping(self):
        for s,c,expected in [("queued",None,"queued"),("waiting",None,"queued"),
                ("in_progress",None,"in_progress"),("completed","failure","failure"),
                ("completed","cancelled","cancelled"),("completed","skipped","skipped"),
                ("completed","timed_out","timed_out"),("completed","neutral","neutral"),
                ("completed","action_required","action_required"),("completed","stale","stale"),
                ("completed","startup_failure","startup_failure"),("new_state",None,"unknown"),
                ("completed","new_conclusion","unknown"),("queued","success","unknown")]:
            with self.subTest(s=s,c=c):
                v=fixture(); v["release"]=None
                v["run_pages"][0]["body"]["workflow_runs"][0].update(status=s,conclusion=c)
                v["job_pages"][0]["body"]["jobs"][0]=job(1,MCP_GROUPS[0],s,c)
                a=self.result(v)
                self.assertTrue(a["fresh"])
                self.assertEqual(a["run_state"],expected)
                self.assertEqual(a["jobs"]["all"][expected],1)

    def test_run_green_with_failed_job_is_unknown(self):
        v=fixture(); v["release"]=None
        v["job_pages"][0]["body"]["jobs"][0]["conclusion"]="failure"
        self.assertEqual(self.result(v)["run_state"],"unknown")

    def test_run_green_with_skipped_never_promotes_release(self):
        v=fixture(); v["job_pages"][0]["body"]["jobs"][0]["conclusion"]="skipped"
        self.bad(v)
        v["release"]["checks"]["ci"]="pending"
        v["release"]["publication_hold"]=False
        self.assertEqual(self.result(v)["release_state_claim"],"BLOCKED")

    def test_release_ci_mismatch(self):
        v=fixture(); v["release"]["checks"]["ci"]="fail"
        self.bad(v)

    def test_release_wrong_sha(self):
        v=fixture(); v["release"]["commit"]=OTHER
        self.bad(v)

    def test_latest_run_and_attempt(self):
        v=fixture()
        v["run_pages"]=[page("workflow_runs",[run(created=NOW-100),run(102,2)])]
        for p in v["job_pages"]:
            for j in p["body"]["jobs"]:
                j.update(run_id=102,run_attempt=2)
        self.assertTrue(self.result(v)["fresh"])
        v["job_pages"][0]["body"]["jobs"][0]["run_attempt"]=1
        self.bad(v)

    def test_wrong_job_sha_or_run(self):
        for k,val in [("head_sha",OTHER),("run_id",999),("run_attempt",2)]:
            with self.subTest(k=k):
                v=fixture(); v["job_pages"][0]["body"]["jobs"][0][k]=val
                self.bad(v)

    def test_wrong_run_identity(self):
        for k,val in [("head_sha",OTHER),("path",".github/workflows/other.yml"),
                      ("repository",{"full_name":"other/repo"}),("head_repository",{"full_name":"fork/repo"})]:
            with self.subTest(k=k):
                v=fixture(); v["run_pages"][0]["body"]["workflow_runs"][0][k]=val
                self.bad(v)

    def test_job_pagination_incomplete(self):
        v=fixture(); v["job_pages"].pop()
        self.bad(v)

    def test_run_pagination_incomplete(self):
        v=fixture(); v["run_pages"][0]["body"]["total_count"]=2
        self.bad(v)

    def test_duplicate_job(self):
        v=fixture(); v["job_pages"][1]["body"]["jobs"][0]["id"]=1
        self.bad(v)

    def test_duplicate_run(self):
        v=fixture(); v["run_pages"]=[page("workflow_runs",[run(),run()])]
        self.bad(v)

    def test_page_order_or_total_change(self):
        for k,val in [("page",1),("total_count",7)]:
            with self.subTest(k=k):
                v=fixture()
                if k=="page": v["job_pages"][1][k]=val
                else: v["job_pages"][1]["body"][k]=val
                self.bad(v)

    def test_empty_run(self):
        v=fixture(); v["run_pages"]=[page("workflow_runs",[])]
        self.bad(v)

    def test_missing_mcp_group(self):
        v=fixture(); v["job_pages"][0]["body"]["jobs"][0]["name"]="ordinary"
        self.bad(v)

    def test_oversize_or_malformed(self):
        for raw in [b" "* (MAX_BYTES+1),b"{}",b"\xff",b'{"a":1,"a":2}',b'{"a":NaN}',b"["*1500]:
            with self.subTest(raw_len=len(raw)):
                self.assertFalse(project(raw,NOW)["fresh"])

    def test_invalid_id_type(self):
        v=fixture(); v["job_pages"][0]["body"]["jobs"][0]["id"]=True
        self.bad(v)

    def test_invalid_timestamp_order(self):
        v=fixture(); v["job_pages"][0]["body"]["jobs"][0]["completed_at"]=ts(NOW-61)
        self.bad(v)

    def test_missing_required_completed_timestamp(self):
        v=fixture(); v["job_pages"][0]["body"]["jobs"][0]["completed_at"]=None
        self.bad(v)

    def test_stale_boundary_and_future(self):
        v=fixture(); v["observed_at"]=NOW-120
        self.bad(v,"stale")
        v["observed_at"]=NOW+6
        self.bad(v,"future")
        v["observed_at"]=NOW+5
        self.assertTrue(self.result(v)["fresh"])

    def test_stale_page_even_fresh_envelope(self):
        v=fixture(); v["job_pages"][1]["received_at"]=NOW-120
        self.bad(v,"stale")

    def test_future_page(self):
        v=fixture(); v["job_pages"][1]["received_at"]=NOW+6
        self.bad(v,"future")

    def test_api_errors_and_recovery(self):
        for status,reason in [(429,"rate_limit"),(503,"api_error"),(403,"api_error"),(None,"timeout")]:
            with self.subTest(status=status):
                v=fixture(); v["job_pages"][1]["http_status"]=status
                self.bad(v,reason)
                self.assertIn('prp_ci_projection_state{state="'+reason+'"} 1',prometheus(dump(v),NOW))
                self.assertTrue(self.result(fixture())["fresh"])

    def test_old_run_age_not_endpoint_health(self):
        v=fixture(); r=v["run_pages"][0]["body"]["workflow_runs"][0]
        r["created_at"]=ts(NOW-2000);r["updated_at"]=ts(NOW-1000)
        a=self.result(v)
        self.assertTrue(a["fresh"])
        self.assertEqual(a["run_age_seconds"],1000)
        self.assertFalse(a["runtime_verified"])

    def test_receipt_incomplete(self):
        v=fixture(); q=v["regression"]; q["module_results"]["task"]="pending"
        q["regression_complete_claimed"]=False;bind_receipt(q)
        self.assertEqual(self.result(v)["regression_claim"],"offline_claim_incomplete")

    def test_receipt_digest_tamper(self):
        v=fixture();v["regression"]["module_results"]["task"]="pending"
        self.bad(v)

    def test_receipt_wrong_candidate(self):
        v=fixture();q=v["regression"];q["candidate"]["commit"]=OTHER;bind_receipt(q)
        self.bad(v)

    def test_receipt_authority_and_source_denied(self):
        for k,val in [("live_verified",True),("production_authorized",True),("source","operator_regression_claim"),
                      ("state","VERIFIED"),("execution_mode","OPERATOR_LIVE")]:
            with self.subTest(k=k):
                v=fixture();q=v["regression"];q[k]=val;bind_receipt(q)
                self.bad(v)

    def test_receipt_stale_or_future(self):
        for value in (NOW-1000,NOW+6):
            v=fixture();q=v["regression"];q["window"]["runtime_after_at"]=value;bind_receipt(q)
            self.bad(v)

    def test_receipt_cleanup_and_counts(self):
        for k in ("cleanup_results","journal_recorded_mutation_outcomes"):
            with self.subTest(k=k):
                v=fixture();q=v["regression"];q[k]={};bind_receipt(q)
                self.bad(v)

    def test_projection_no_arbitrary_labels_and_bounded(self):
        v=fixture(); output=prometheus(dump(v),NOW)
        for marker in (SHA, "private-marker", REPO, WORKFLOW, "101", "sha256:", "http://"):
            self.assertNotIn(marker,output)
        self.assertIn('prp_ci_jobs{group="mcp",state="success"} 5',output)
        self.assertLessEqual(len(output.splitlines()),65)

    def test_network_and_process_calls_forbidden(self):
        with patch("socket.create_connection",side_effect=AssertionError("network")), \
             patch("subprocess.Popen",side_effect=AssertionError("process")):
            self.assertTrue(self.result(fixture())["fresh"])


if __name__ == "__main__":
    unittest.main()
