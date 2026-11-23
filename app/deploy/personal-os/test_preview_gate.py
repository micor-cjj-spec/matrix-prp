"""No-network synthetic regression checks for the Personal OS preview gate."""
import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from preview_gate import Blocked, main, review, safe_json_file, verify_candidate_migrations

SHA = "a" * 40


def evidence():
    return {
        "schema": "personal-os-preview-v1",
        "stage": {
            "kind": "dedicated-personal-os", "public_host": "pos-stage.example.net",
            "gateway_port": 18531, "database_name": "prp_pos_stage_01",
            "compose_project": "prp-pos-preview-01", "isolated_host": True,
            "fresh_empty_database": True, "synthetic_users_only": True, "owner_approved": True,
            "production_mounts_present": False, "production_data_used": False,
            "existing_v2_modified": False,
        },
        "observed": {
            "source_sha": SHA, "backend_source_sha": SHA, "web_source_sha": SHA,
            "backend_image_digest": "sha256:" + "1" * 64,
            "web_image_digest": "sha256:" + "2" * 64,
            "flyway_version": 31, "flyway_failed_count": 0,
            "https_verified": True, "actual_runtime_observation": True,
            "mcp_enabled": False, "oauth_link_enabled": False,
            "automatic_chat_extraction_enabled": False,
            "model_egress_enabled": False, "mcp_write_enabled": False,
        },
    }


def candidate(root):
    sql = root / "app/backend/src/main/resources/db/migration"
    sql.mkdir(parents=True)
    rules = []
    for number, name in ((30, "V30__wellness_analysis_details.sql"),
                         (31, "V31__personal_os_goals_and_assertions.sql")):
        contents = f"CREATE TABLE prp_test_{number} (id bigint primary key) ENGINE=InnoDB;\n".encode()
        (sql / name).write_bytes(contents)
        rules.append({"version": number, "file": name, "sha256": hashlib.sha256(contents).hexdigest(),
                      "mode": "create-empty", "tables": [f"prp_test_{number}"]})
    folder = root / "app/deploy"
    folder.mkdir(parents=True)
    (folder / "migration-policy.json").write_text(json.dumps({"schema_version": 1, "rules": rules}))


class PreviewGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        candidate(self.root)
        self.doc = evidence()

    def no_go(self, expected, change):
        data = deepcopy(self.doc)
        change(data)
        with self.assertRaises(Blocked) as ctx:
            review(data, SHA, self.root)
        self.assertEqual(str(ctx.exception), expected)

    def test_complete_declared_evidence_never_means_approved(self):
        self.assertEqual(review(self.doc, SHA, self.root),
                         "DECLARED_EVIDENCE_CONSISTENT_REVIEW_REQUIRED")

    def test_production_database(self):
        self.no_go("SHARED_DATABASE", lambda d: d["stage"].update(database_name="matrix_prp"))

    def test_shared_stage_database(self):
        self.no_go("SHARED_DATABASE", lambda d: d["stage"].update(database_name="matrix_prp_mcp_stage"))

    def test_reserved_ports(self):
        for port in (11000, 18080, 18081, 18082, 18083, 18084, 80, True):
            with self.subTest(port=port):
                self.no_go("GATEWAY_PORT_RESERVED", lambda d: d["stage"].update(gateway_port=port))

    def test_reserved_hosts(self):
        for host in ("micor.top", "prp-test.micor.top", "auth-test.micor.top"):
            with self.subTest(host=host):
                self.no_go("RESERVED_OR_IP_HOST", lambda d: d["stage"].update(public_host=host))

    def test_ip_literal_not_a_stage_host(self):
        self.no_go("RESERVED_OR_IP_HOST", lambda d: d["stage"].update(public_host="127.0.0.1"))

    def test_malformed_host(self):
        self.no_go("INVALID_HOST", lambda d: d["stage"].update(public_host="stage"))

    def test_unapproved_owner(self):
        self.no_go("STAGE_GUARD_OWNER_APPROVED", lambda d: d["stage"].update(owner_approved=False))

    def test_missing_isolated_host(self):
        self.no_go("STAGE_GUARD_ISOLATED_HOST", lambda d: d["stage"].update(isolated_host=False))

    def test_existing_v2_modification(self):
        self.no_go("STAGE_GUARD_EXISTING_V2_MODIFIED", lambda d: d["stage"].update(existing_v2_modified=True))

    def test_production_mount(self):
        self.no_go("STAGE_GUARD_PRODUCTION_MOUNTS_PRESENT", lambda d: d["stage"].update(production_mounts_present=True))

    def test_real_data(self):
        self.no_go("STAGE_GUARD_PRODUCTION_DATA_USED", lambda d: d["stage"].update(production_data_used=True))

    def test_source_sha_all_layers(self):
        self.no_go("SOURCE_SHA_MISMATCH", lambda d: d["observed"].update(web_source_sha="b" * 40))

    def test_digest_is_required(self):
        self.no_go("IMAGE_DIGEST_MISSING", lambda d: d["observed"].update(backend_image_digest="missing"))

    def test_flyway_v30_incomplete(self):
        self.no_go("FLYWAY_VERSION_MISMATCH", lambda d: d["observed"].update(flyway_version=30))

    def test_flyway_bool_not_integer(self):
        self.no_go("FLYWAY_VERSION_MISMATCH", lambda d: d["observed"].update(flyway_version=True))

    def test_flyway_failure(self):
        self.no_go("FLYWAY_FAILURE_OR_UNVERIFIED", lambda d: d["observed"].update(flyway_failed_count=1))

    def test_source_only_cannot_certify_runtime(self):
        self.no_go("RUNTIME_GUARD_ACTUAL_RUNTIME_OBSERVATION", lambda d: d["observed"].update(actual_runtime_observation=False))

    def test_all_external_capabilities_off(self):
        for key in ("mcp_enabled", "oauth_link_enabled", "automatic_chat_extraction_enabled",
                    "model_egress_enabled", "mcp_write_enabled"):
            with self.subTest(key=key):
                self.no_go("PREVIEW_FEATURE_MUST_BE_OFF_" + key.upper(),
                           lambda d, k=key: d["observed"].update({k: True}))

    def test_unknown_evidence_fields(self):
        self.no_go("UNRECOGNIZED_STAGE_FIELDS", lambda d: d["stage"].update(other="hello"))

    def test_sensitive_field_rejected_without_value(self):
        self.no_go("SENSITIVE_FIELD_FORBIDDEN", lambda d: d["stage"].update(DB_PASSWORD="dontprint"))

    def test_missing_policy_fails_closed(self):
        (self.root / "app/deploy/migration-policy.json").unlink()
        with self.assertRaisesRegex(Blocked, "EVIDENCE_OR_POLICY_MISSING_OR_OVERSIZE"):
            review(self.doc, SHA, self.root)

    def test_v30_version_collision_fails_closed(self):
        policy = self.root / "app/deploy/migration-policy.json"
        data = json.loads(policy.read_text())
        data["rules"].append(data["rules"][0])
        policy.write_text(json.dumps(data))
        with self.assertRaisesRegex(Blocked, "DUPLICATE_MIGRATION_VERSION"):
            review(self.doc, SHA, self.root)

    def test_mismatched_v31_sql_digest(self):
        path = self.root / "app/backend/src/main/resources/db/migration/V31__personal_os_goals_and_assertions.sql"
        path.write_text("ALTER TABLE something DROP anything;")
        with self.assertRaisesRegex(Blocked, "MIGRATION_SHA256_MISMATCH"):
            review(self.doc, SHA, self.root)

    def test_wrong_v30_filename(self):
        policy = self.root / "app/deploy/migration-policy.json"
        data = json.loads(policy.read_text())
        data["rules"][0]["file"] = "V30__personal_os_goals_and_assertions.sql"
        policy.write_text(json.dumps(data))
        with self.assertRaisesRegex(Blocked, "MIGRATION_POLICY_MISMATCH"):
            review(self.doc, SHA, self.root)

    def test_latest_version_must_be_v31(self):
        policy = self.root / "app/deploy/migration-policy.json"
        data = json.loads(policy.read_text())
        data["rules"].append({"version": 32})
        policy.write_text(json.dumps(data))
        with self.assertRaisesRegex(Blocked, "REVIEWED_V30_V31_MIGRATIONS_REQUIRED"):
            review(self.doc, SHA, self.root)

    def test_extra_v30_sql_filename_is_rejected(self):
        sql = self.root / "app/backend/src/main/resources/db/migration/V30__shadow.sql"
        sql.write_text("CREATE TABLE prp_shadow_30 (id bigint primary key);")
        with self.assertRaisesRegex(Blocked, "MIGRATION_VERSION_COLLISION"):
            review(self.doc, SHA, self.root)

    def test_extra_v31_sql_filename_is_rejected(self):
        sql = self.root / "app/backend/src/main/resources/db/migration/V31__shadow.sql"
        sql.write_text("CREATE TABLE prp_shadow_31 (id bigint primary key);")
        with self.assertRaisesRegex(Blocked, "MIGRATION_VERSION_COLLISION"):
            review(self.doc, SHA, self.root)

    def test_actual_checked_out_candidate_v30_v31_policy_matches_sql_bytes(self):
        # The existing fixtures are synthetic; also validate the REAL Git
        # checkout V30/V31 SQL bytes against their exact policy SHA256.
        checkout_root = Path(__file__).resolve().parents[3]
        self.assertIsNone(verify_candidate_migrations(checkout_root))

    def test_duplicate_evidence_keys(self):
        p = self.root / "dup.json"
        p.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(Blocked, "DUPLICATE_JSON_KEY"):
            safe_json_file(p)

    def test_evidence_size_limit(self):
        p = self.root / "big.json"
        p.write_text("a" * 32769)
        with self.assertRaisesRegex(Blocked, "EVIDENCE_OR_POLICY_MISSING_OR_OVERSIZE"):
            safe_json_file(p)

    def test_cli_exit_code_is_no_go_for_incomplete(self):
        ev = self.root / "evidence.json"
        ev.write_text(json.dumps(self.doc))
        self.assertEqual(main(["--evidence", str(ev), "--expected-sha", SHA,
                               "--candidate-root", str(self.root)]), 0)
        self.doc["stage"]["owner_approved"] = False
        ev.write_text(json.dumps(self.doc))
        self.assertEqual(main(["--evidence", str(ev), "--expected-sha", SHA,
                               "--candidate-root", str(self.root)]), 2)


if __name__ == "__main__":
    unittest.main()
