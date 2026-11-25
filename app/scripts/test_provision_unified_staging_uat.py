import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).with_name("provision_unified_staging_uat.py")
SPEC = importlib.util.spec_from_file_location("provision_uat", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def item(env, ports=None, state="running"):
    return {"state": state, "project": MOD.PROJECT, "env": env, "ports": ports or {}}

def metadata():
    return {
        "backend": item({
            "MATRIX_PRP_DB_URL": "jdbc:mysql://mysql:3306/matrix_prp_unified_stage?useSSL=false",
            "MATRIX_PRP_DB_USER": "prp_unified",
        }),
        "gateway": item(
            {"PRP_STAGE_HOST": "prp-test.micor.top"},
            {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "23080"}]},
        ),
        "mysql": item({
            "MYSQL_DATABASE": "matrix_prp_unified_stage",
            "MYSQL_USER": "prp_unified",
            "MYSQL_ROOT_PASSWORD": "NOT-A-REAL-SECRET",
        }),
    }

class ProvisionUatTests(unittest.TestCase):
    def test_exact_stage_target_passes(self):
        self.assertTrue(MOD.validate_target(metadata()))

    def test_wrong_project_or_stopped_container_blocks(self):
        for mutate in (
            lambda m: m["backend"].update(project="production"),
            lambda m: m["mysql"].update(state="exited"),
            lambda m: m["gateway"]["env"].update(PRP_STAGE_HOST="prp.micor.top"),
            lambda m: m["backend"]["env"].update(MATRIX_PRP_DB_URL="jdbc:mysql://mysql:3306/matrix_prp"),
            lambda m: m["mysql"]["env"].update(MYSQL_DATABASE="matrix_prp"),
        ):
            m = metadata()
            mutate(m)
            with self.assertRaises(MOD.ProvisionError):
                MOD.validate_target(m)

    def test_backend_or_database_host_publish_blocks(self):
        for key in ("backend", "mysql"):
            m = metadata()
            m[key]["ports"] = {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}
            with self.assertRaises(MOD.ProvisionError):
                MOD.validate_target(m)

    def test_gateway_must_be_exact_loopback_binding(self):
        m = metadata()
        m["gateway"]["ports"]["8080/tcp"][0]["HostIp"] = "0.0.0.0"
        with self.assertRaises(MOD.ProvisionError):
            MOD.validate_target(m)

    def test_smoke_uses_only_get_and_returns_redacted_summary(self):
        calls = []
        expected = {"id": 71, "username": "prp_uat_test"}
        lists = {
            "/api/modules/domains", "/api/wellness/summary/nutrition-trends",
            "/api/video/folders", "/api/practice/subjects", "/api/goals",
        }
        def fake(path, *, method="GET", payload=None, token=None):
            calls.append((path, method, payload, token))
            key = path.split("?", 1)[0]
            data = expected | {"administrator": False} if key == "/api/users/me" else ([] if key in lists else {})
            return 200, "application/json", {"code": "SUCCESS", "data": data}
        original = MOD.http_json
        MOD.http_json = fake
        try:
            report = MOD.run_readonly_smoke("synthetic.jwt.value", expected)
        finally:
            MOD.http_json = original
        self.assertEqual(report["state"], "API_SMOKE_PASS")
        self.assertEqual(sum(len(c["checks"]) for c in report["cases"]), 11)
        self.assertTrue(all(c[1] == "GET" and c[2] is None for c in calls))
        self.assertNotIn("synthetic.jwt.value", str(report))
        self.assertNotIn("prp_uat_test", str(report))
        self.assertFalse(report["liveVerified"])
        self.assertFalse(report["deploymentAuthorized"])
        self.assertFalse(report["productionAuthorized"])

    def test_identity_mismatch_stops_all_business_reads(self):
        calls = []
        def fake(path, *, method="GET", payload=None, token=None):
            calls.append(path)
            return 200, "application/json", {
                "code": "SUCCESS",
                "data": {"id": 999, "username": "other", "administrator": False},
            }
        original = MOD.http_json
        MOD.http_json = fake
        try:
            report = MOD.run_readonly_smoke("synthetic.jwt.value", {"id": 71, "username": "prp_uat_test"})
        finally:
            MOD.http_json = original
        self.assertEqual(calls, ["/api/users/me"])
        self.assertEqual(report["cases"][0]["checks"][0]["result"], "IDENTITY_MISMATCH")
        self.assertTrue(all(c["state"] == "PENDING" for c in report["cases"][1:]))

    def test_401_and_429_stop_following_requests(self):
        for code in (401, 429):
            calls = []
            def fake(path, *, method="GET", payload=None, token=None):
                calls.append(path)
                return code, "application/json", None
            original = MOD.http_json
            MOD.http_json = fake
            try:
                report = MOD.run_readonly_smoke("synthetic.jwt.value", {"id": 71, "username": "prp_uat_test"})
            finally:
                MOD.http_json = original
            self.assertEqual(len(calls), 1)
            self.assertEqual(report["state"], "API_SMOKE_INCOMPLETE")
            self.assertTrue(all(c["state"] == "PENDING" for c in report["cases"][1:]))

    def test_missing_root_secret_blocks(self):
        m = metadata()
        del m["mysql"]["env"]["MYSQL_ROOT_PASSWORD"]
        with self.assertRaises(MOD.ProvisionError):
            MOD.validate_target(m)

    def test_u09_non_auth_failure_stops_all_business_reads(self):
        calls = []
        def fake(path, *, method="GET", payload=None, token=None):
            calls.append(path)
            return 503, "application/json", None
        original = MOD.http_json
        MOD.http_json = fake
        try:
            report = MOD.run_readonly_smoke("synthetic.jwt.value", {"id": 71, "username": "prp_uat_test"})
        finally:
            MOD.http_json = original
        self.assertEqual(calls, ["/api/users/me"])
        self.assertTrue(all(c["state"] == "PENDING" for c in report["cases"][1:]))

if __name__ == "__main__":
    unittest.main()
