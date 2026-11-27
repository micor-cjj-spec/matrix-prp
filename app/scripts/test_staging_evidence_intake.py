"""Synthetic inputs only: no actual run IDs, artifact bytes, accounts or host access."""
import copy
import unittest
from staging_evidence_intake import (assess_intake, CI_WORKFLOW, WITNESS_WORKFLOW, WITNESS_BRANCH,
    ARTIFACT_NAME, WITNESS_JOBS, CORE_JOBS, MANDATORY, ENV, REPO)

NOW = 1700001000
A, T, H, M = ("a"*40, "b"*40, "c"*40, "d"*40)
def dg(c):
    return "sha256:" + c*64

def fixture():
    c = {"commit": A, "tree": T, "archive_digest": dg("1"), "schema": 31}
    names = sorted(CORE_JOBS | {"extra-job"})
    def run(wf, head, checkout, run_id, event, branch, jobs):
        return {"source": "github_metadata_claim", "repository": REPO, "head_repository": REPO,
            "workflow_id": wf[0], "workflow_path": wf[1], "run_id": run_id, "attempt": 1,
            "latest_run_id": run_id, "latest_attempt": 1, "head": head, "event": event, "branch": branch,
            "status": "completed", "conclusion": "success", "started_at": NOW-500,
            "finished_at": NOW-300, "observed_at": NOW-5, "total_count": len(jobs),
            "checkout": checkout, "tested_tree": T,
            "jobs": [{"id": i+1, "name": n, "run_id": run_id, "attempt": 1, "head": head,
                      "status": "completed", "conclusion": "success"} for i,n in enumerate(sorted(jobs))]}
    p = {"repository": REPO, "environment": ENV, "candidate": c, "expected_ci_jobs": names,
        "ci_context": {"run_id": 1, "attempt": 1, "event": "pull_request",
                       "branch": "review/unified-396-ui-health-20261125", "checkout": M},
        "witness_context": {"run_id": 2, "attempt": 1, "head": H}, "artifact_id": 3}
    images = {"backend": dg("3"), "gateway": dg("4"), "mysql": dg("5")}
    db = {"instance_digest": dg("6"), "image": dg("7"), "schema": 31}
    e = {"schema_version": 1,
        "ci": run(CI_WORKFLOW,A,M,1,"pull_request",p["ci_context"]["branch"],names),
        "witness": run(WITNESS_WORKFLOW,H,A,2,"pull_request",WITNESS_BRANCH,WITNESS_JOBS),
        "artifact_metadata": {"source": "github_metadata_claim", "repository": REPO, "artifact_id": 3,
            "name": ARTIFACT_NAME, "run_id": 2, "attempt": 1, "witness_head": H,
            "zip_digest": dg("2"), "created_at": NOW-350, "expires_at": NOW+1000,
            "observed_at": NOW-5, "expired": False},
        "archive_review": {"source": "independent_archive_review_claim", "artifact_id": 3,
            "zip_digest": dg("2"), **c, "images": images, "observed_at": NOW-250,
            "checksum_status": "pass", "source_status": "pass", "image_status": "pass"},
        "operator": {"source": "operator_report_claim", "repository": REPO, "environment": ENV,
            "issue": 396, "cutover_comment_id": 4, "smoke_comment_id": 5, **c, "artifact_id": 3,
            "images": {k: images[k] for k in ("backend", "gateway")}, "mysql_before": dict(db),
            "mysql_after": dict(db), "cutover_at": NOW-150, "smoke_at": NOW-100, "observed_at": NOW-5,
            "cutover_status": "pass", "read_smoke_status": "API_SMOKE_PASS", "api_passed": 9,
            "checks_executed": 11, "ordinary_nonadmin": True, "mcp_grant_rows": 0, "account_reused": True}}
    return p,e

class IntakeTests(unittest.TestCase):
    def check(self, p, e, finding=None):
        out = assess_intake(p,e,NOW)
        self.assertEqual(out["state"], "BLOCKED")
        self.assertTrue(set(MANDATORY) <= set(out["findings"]))
        for key in ("source_authenticated","artifact_bytes_verified","runtime_verified",
                    "business_uat_verified","approval_authorized","release_eligible",
                    "deployment_authorized","production_authorized","live_verified"):
            self.assertIs(out[key],False)
        if finding:
            self.assertIn(finding,out["findings"])
            self.assertFalse(out["candidate_match_claimed"])
        return out

    def test_distinct_witness_checkout_and_preserved_mysql(self):
        p,e = fixture()
        out = self.check(p,e)
        self.assertTrue(out["candidate_match_claimed"])
        self.assertEqual(out["findings"],MANDATORY)
        self.assertTrue(out["p36_build_review"]["candidate_match_claimed"])
        self.assertNotEqual(e["archive_review"]["images"]["mysql"],e["operator"]["mysql_after"]["image"])

    def test_dev_push_requires_exact_checkout(self):
        p,e=fixture()
        p["ci_context"].update(event="push",branch="dev",checkout=A)
        e["ci"].update(event="push",branch="dev",checkout=A)
        self.assertTrue(self.check(p,e)["candidate_match_claimed"])
        e["ci"]["checkout"]=M
        self.check(p,e,"CI_REVIEW_CONTEXT_MISMATCH")

    def test_missing_each_section(self):
        for k in ("ci","witness","artifact_metadata","archive_review","operator"):
            p,e=fixture()
            e[k]=None
            self.check(p,e,k.upper()+"_MISSING")

    def test_ci_and_witness_superseded(self):
        for k in ("ci","witness"):
            for field in ("latest_run_id","latest_attempt"):
                p,e=fixture()
                e[k][field]+=1
                self.check(p,e,k.upper()+"_SUPERSEDED")

    def test_missing_duplicate_and_unknown_inventory(self):
        for k in ("ci","witness"):
            for change in (lambda j:j.pop(),lambda j:j.append(dict(j[0])),
                           lambda j:j[0].update(name="wrong")):
                p,e=fixture()
                change(e[k]["jobs"])
                self.check(p,e,k.upper()+"_JOB_INVENTORY_MISMATCH")

    def test_wrong_job_binding_or_skipped(self):
        for k in ("ci","witness"):
            for f,v in (("head","f"*40),("attempt",2),("run_id",99),("conclusion","skipped")):
                p,e=fixture()
                e[k]["jobs"][0][f]=v
                self.check(p,e,k.upper()+"_JOB_NOT_EXACT_SUCCESS")

    def test_non_success_run(self):
        for k in ("ci","witness"):
            for state in ("failure","cancelled","skipped","timed_out"):
                p,e=fixture()
                e[k]["conclusion"]=state
                self.check(p,e,k.upper()+"_NOT_SUCCESS")

    def test_ci_candidate_checkout_or_tree_mismatch(self):
        for f,v in (("head",H),("checkout",H),("tested_tree",H),("run_id",99)):
            p,e=fixture()
            e["ci"][f]=v
            self.check(p,e,"CI_REVIEW_CONTEXT_MISMATCH")

    def test_witness_source_not_witness_head(self):
        for f,v in (("head",A),("checkout",H),("tested_tree",H),("branch","dev")):
            p,e=fixture()
            e["witness"][f]=v
            self.check(p,e,"WITNESS_SOURCE_MAPPING_MISMATCH")

    def test_event_and_branch_types_are_normalized_before_digest(self):
        for field, value in (("event", {"production_authorized": True, "raw_body": "x"}),
                             ("event", ["push"]), ("event", "workflow_dispatch"),
                             ("branch", {"production_authorized": True, "raw_body": "x"}),
                             ("branch", ["dev"]), ("branch", 7),
                             ("branch", "x" * 201), ("branch", "dev\\nraw_body"),
                             ("branch", "../production")):
            for section in ("ci", "witness"):
                p, e = fixture()
                e[section][field] = value
                with self.assertRaises(ValueError):
                    self.check(p, e)
            p, e = fixture()
            p["ci_context"][field] = value
            with self.assertRaises(ValueError):
                self.check(p, e)

    def test_repository_workflow_environment_rejected(self):
        for k,f,v in (("ci","repository","other/repo"),("ci","head_repository","fork/repo"),
                      ("witness","workflow_id",5),("witness","workflow_path",".github/workflows/deploy-prp.yml"),
                      ("operator","environment","production"),("operator","issue",323)):
            p,e=fixture()
            e[k][f]=v
            with self.assertRaises(ValueError): self.check(p,e)
        p,e=fixture()
        p["environment"]="production"
        with self.assertRaises(ValueError): self.check(p,e)

    def test_artifact_metadata_not_same_as_inner_archive(self):
        p,e=fixture()
        e["artifact_metadata"]["zip_digest"]=dg("9")
        self.check(p,e,"ARCHIVE_ZIP_METADATA_MISMATCH")
        p,e=fixture()
        e["archive_review"]["archive_digest"]=e["artifact_metadata"]["zip_digest"]
        self.check(p,e,"ARCHIVE_SOURCE_OR_CANDIDATE_MISMATCH")

    def test_artifact_witness_id_and_attempt(self):
        for f,v in (("artifact_id",6),("run_id",8),("attempt",2),("witness_head",A)):
            p,e=fixture()
            e["artifact_metadata"][f]=v
            self.check(p,e,"ARTIFACT_WITNESS_CONTEXT_MISMATCH")

    def test_artifact_expiry_future_and_run_chronology(self):
        for f,v in (("expires_at",NOW),("expired",True),("observed_at",NOW+1)):
            p,e=fixture()
            e["artifact_metadata"][f]=v
            self.check(p,e,"ARTIFACT_STALE_OR_EXPIRED")
        p,e=fixture()
        e["artifact_metadata"]["created_at"]=NOW-600
        self.check(p,e,"ARTIFACT_OUTSIDE_WITNESS_RUN")

    def test_archive_review_mismatch_and_failed(self):
        for f,v in (("commit",H),("tree",H),("schema",30),("artifact_id",7)):
            p,e=fixture()
            e["archive_review"][f]=v
            self.check(p,e,"ARCHIVE_SOURCE_OR_CANDIDATE_MISMATCH")
        for f in ("checksum_status","source_status","image_status"):
            p,e=fixture()
            e["archive_review"][f]="fail"
            self.check(p,e,"ARCHIVE_REVIEW_INCOMPLETE")

    def test_archive_review_time(self):
        p,e=fixture()
        e["archive_review"]["observed_at"]=NOW+1
        self.check(p,e,"ARCHIVE_REVIEW_FUTURE")
        p,e=fixture()
        e["archive_review"]["observed_at"]=NOW-1
        self.check(p,e,"ARCHIVE_REVIEW_AFTER_CUTOVER")
        p,e=fixture()
        e["archive_review"]["observed_at"]=NOW-600
        self.check(p,e,"ARCHIVE_REVIEW_OUTSIDE_ARTIFACT_LIFETIME")

    def test_stage_different_candidate_and_images(self):
        for f,v in (("commit",H),("tree",H),("schema",30),("archive_digest",dg("9")),("artifact_id",7)):
            p,e=fixture()
            e["operator"][f]=v
            self.check(p,e,"OPERATOR_CANDIDATE_MISMATCH")
        p,e=fixture()
        e["operator"]["images"]["backend"]=dg("9")
        self.check(p,e,"OPERATOR_IMAGE_MISMATCH")

    def test_mysql_preservation_not_archive_mysql(self):
        for f,v in (("instance_digest",dg("9")),("image",dg("9")),("schema",30)):
            p,e=fixture()
            e["operator"]["mysql_after"][f]=v
            self.check(p,e,"MYSQL_PRESERVATION_NOT_ESTABLISHED")

    def test_smoke_incomplete_or_elevated(self):
        for f,v in (("api_passed",8),("checks_executed",10),("read_smoke_status","API_SMOKE_INCOMPLETE")):
            p,e=fixture()
            e["operator"][f]=v
            self.check(p,e,"READ_SMOKE_NOT_PASS")
        for f,v in (("ordinary_nonadmin",False),("account_reused",False),("mcp_grant_rows",1)):
            p,e=fixture()
            e["operator"][f]=v
            self.check(p,e,"READ_SMOKE_IDENTITY_NOT_ORDINARY_REUSED")

    def test_stale_or_unordered_observation(self):
        for k in ("ci","witness"):
            p,e=fixture()
            e[k]["observed_at"]=NOW-901
            self.check(p,e,k.upper()+"_STALE_OR_INVALID_CHRONOLOGY")
        p,e=fixture()
        e["operator"]["smoke_at"]=NOW-151
        self.check(p,e,"OPERATOR_STALE_OR_INVALID_CHRONOLOGY")
        p,e=fixture()
        e["operator"]["observed_at"]=NOW+1
        self.check(p,e,"OPERATOR_STALE_OR_INVALID_CHRONOLOGY")

    def test_policy_and_input_type_bounds(self):
        for change in (lambda p,e:p.update(expected_ci_jobs=["bad"]*6),
                       lambda p,e:p.update(artifact_id=True),
                       lambda p,e:e.update(schema_version=True),
                       lambda p,e:e["ci"].update(total_count=101),
                       lambda p,e:e["operator"].update(mcp_grant_rows=False),
                       lambda p,e:e["archive_review"].update(images={"backend":dg("3")})):
            p,e=fixture()
            change(p,e)
            with self.assertRaises(ValueError): self.check(p,e)

    def test_injected_authority_and_sensitive_fields_rejected(self):
        for k in ("ci","witness","artifact_metadata","archive_review","operator"):
            p,e=fixture()
            e[k]["production_authorized"]=True
            with self.assertRaises(ValueError): self.check(p,e)
        p,e=fixture()
        e["operator"]["raw_body"]="private"
        with self.assertRaises(ValueError): self.check(p,e)

    def test_binding_deterministic_and_complete(self):
        p,e=fixture()
        out=self.check(p,e)
        p["expected_ci_jobs"].reverse()
        e["ci"]["jobs"].reverse()
        e["witness"]["jobs"].reverse()
        self.assertEqual(out["binding_digest"],self.check(p,e)["binding_digest"])
        for k,f,v in (("operator","smoke_comment_id",8),("ci","observed_at",NOW-6),
                      ("archive_review","observed_at",NOW-251),("artifact_metadata","expires_at",NOW+999)):
            q,x=copy.deepcopy(p),copy.deepcopy(e)
            x[k][f]=v
            self.assertNotEqual(out["binding_digest"],self.check(q,x)["binding_digest"])

    def test_no_mutation(self):
        p,e=fixture()
        pp,ee=copy.deepcopy(p),copy.deepcopy(e)
        out=self.check(p,e)
        self.assertEqual((p,e),(pp,ee))
        out["p36_build_review"]["findings"].append("tampered")
        self.assertEqual((p,e),(pp,ee))
