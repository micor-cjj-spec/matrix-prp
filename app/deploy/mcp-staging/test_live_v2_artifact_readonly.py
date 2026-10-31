"""Deterministic, no-Docker tests for read-only live V2 OIDC marker inventory."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import warnings
import tarfile
import unittest
import zipfile
from types import SimpleNamespace

import live_v2_artifact_readonly as probe


def archive(members):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as t:
        for path, blob in members.items():
            info = tarfile.TarInfo(path)
            info.size = len(blob)
            t.addfile(info, io.BytesIO(blob))
    return out.getvalue()


def jar_bytes(paths, *, corrupted=(), duplicate=False):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for path in paths:
            raw = b"synthetic"
            if path in probe.REVIEWED_MIGRATION_BLOBS:
                # Synthetic Docker stream, authentic immutable migration bytes.
                source = (Path(__file__).resolve().parents[2] /
                          "backend/src/main/resources/db/migration" /
                          path.rsplit("/", 1)[-1])
                raw = source.read_bytes()
            if path in corrupted:
                raw += b"\n-- unacceptable migration mutation"
            z.writestr(path, raw)
            if duplicate and path.endswith("McpFirstPartyOidcLinkController.class"):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    z.writestr(path, raw)
    return out.getvalue()


class FakeRunner:
    def __init__(self, *, frontend=True, backend=True,
                 missing_js=(), missing_class=(), corrupted=(), duplicate=False):
        self.calls = []
        self.states = {
            probe.GATEWAY: frontend,
            probe.BACKEND: backend,
        }
        js = b"|".join(
            marker for marker, label in probe.JS_MARKERS.items()
            if label not in missing_js
        )
        self.front = archive({
            "assets/vendor.test.js": js,
            "assets/style.css": b"synthetic",
        })
        self.back = archive({
            "app.jar": jar_bytes(
                (path for path, label in probe.CLASSES.items()
                 if label not in missing_class),
                corrupted=corrupted, duplicate=duplicate,
            )
        })

    def __call__(self, argv, *, capture_output, timeout, check):
        self.calls.append(argv)
        assert capture_output is True and check is False
        assert argv[0] == "docker"
        if argv[1] == "inspect":
            return SimpleNamespace(
                returncode=0,
                stdout=b"running\n" if self.states[argv[-1]] else b"exited\n",
                stderr=b"",
            )
        if argv[1] == "cp":
            return SimpleNamespace(
                returncode=0,
                stdout=self.front if argv[2].startswith(probe.GATEWAY + ":")
                else self.back,
                stderr=b"",
            )
        raise AssertionError("Forbidden command reached")


class ReadOnlyV2ArtifactContract(unittest.TestCase):
    def test_success_reports_markers_but_never_claims_live_oauth(self):
        fake = FakeRunner()
        result = probe.check(fake)
        self.assertEqual(result["gateway_oidc"], "ALL_PRESENT")
        self.assertEqual(result["backend_oidc"], "ALL_PRESENT")
        self.assertEqual(result["artifacts_feature_ready"],
                         "SOURCE_MARKERS_PRESENT_REVIEW_ONLY")
        self.assertIs(result["live_oidc_flow_verified"], False)
        self.assertIs(result["g0_b2_install_permitted"], False)
        self.assertIs(result["docker_state_changed"], False)
        self.assertEqual([x[:2] for x in fake.calls],
                         [["docker", "inspect"], ["docker", "inspect"],
                          ["docker", "cp"], ["docker", "cp"]])
        self.assertNotIn("synthetic", json.dumps(result))

    def test_missing_markers_fail_closed(self):
        r = probe.check(FakeRunner(
            missing_js=("finish",), missing_class=("service", "migration_v29")))
        self.assertEqual(r["gateway_oidc"], "PARTIAL_MARKERS")
        self.assertEqual(r["backend_oidc"], "PARTIAL_MARKERS")
        self.assertEqual(r["artifacts_feature_ready"],
                         "BLOCKED_RUNNING_V2_ARTIFACTS_INCOMPLETE")

    def test_reviewed_git_blob_constants_match_immutable_checkout_bytes(self):
        for path, expected in probe.REVIEWED_MIGRATION_BLOBS.items():
            with self.subTest(path=path.rsplit("/", 1)[-1]):
                source = (Path(__file__).resolve().parents[2] /
                          "backend/src/main/resources/db/migration" /
                          path.rsplit("/", 1)[-1])
                raw = source.read_bytes()
                header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
                self.assertEqual(hashlib.sha1(header + raw).hexdigest(), expected)

    def test_correct_sql_name_with_modified_content_fails_closed(self):
        for path in probe.REVIEWED_MIGRATION_BLOBS:
            with self.subTest(migration=path.rsplit("/", 1)[-1]):
                result = probe.check(FakeRunner(corrupted=(path,)))
                self.assertEqual(result["backend_oidc"], "PARTIAL_MARKERS")
                self.assertEqual(result["artifacts_feature_ready"],
                                 "BLOCKED_RUNNING_V2_ARTIFACTS_INCOMPLETE")
                self.assertIs(result["g0_b2_install_permitted"], False)

    def test_duplicate_entries_are_not_misread_as_running_artifact_parity(self):
        result = probe.check(FakeRunner(duplicate=True))
        self.assertEqual(result["artifacts_feature_ready"], "BLOCKED_OR_UNVERIFIED")
        self.assertEqual(result["safe_diagnostic"], "BACKEND_JAR_DUPLICATE_ENTRIES")
        self.assertIs(result["docker_state_changed"], False)

    def test_docker_cp_timeout_yields_bounded_result_not_traceback(self):
        class FailingRead(FakeRunner):
            def __call__(self, argv, **kw):
                if argv[1] == "cp":
                    raise subprocess.TimeoutExpired(cmd=argv, timeout=28)
                return super().__call__(argv, **kw)
        result = probe.check(FailingRead())
        self.assertEqual(result["artifacts_feature_ready"], "BLOCKED_OR_UNVERIFIED")
        self.assertEqual(result["safe_diagnostic"], "DOCKER_COPY_READ_UNAVAILABLE")
        self.assertIs(result["docker_state_changed"], False)

    def test_docker_inspect_timeout_refuses_inventory(self):
        class FailingInspect(FakeRunner):
            def __call__(self, argv, **kw):
                if argv[1] == "inspect":
                    raise subprocess.TimeoutExpired(cmd=argv, timeout=8)
                return super().__call__(argv, **kw)
        result = probe.check(FailingInspect())
        self.assertEqual(result["artifacts_feature_ready"],
                         "BLOCKED_UNAVAILABLE_CONTAINER")
        self.assertEqual(result["gateway_running"], "NO")
        self.assertEqual(result["backend_running"], "NO")

    def test_old_v28_oidc_without_v29_is_not_candidate_ready(self):
        # An old image with the incorrect V28 OIDC SQL name cannot satisfy
        # the canonical immutable lease V28 + first-party OIDC V29 chain.
        from zipfile import ZipFile
        fake = FakeRunner(missing_class=("migration_v28", "migration_v29"))
        with_zip = io.BytesIO()
        with ZipFile(with_zip, "w") as z:
            z.writestr("BOOT-INF/classes/db/migration/"
                       "V28__mcp_first_party_oidc_link_flows.sql", b"synthetic")
            for name, label in probe.CLASSES.items():
                if not label.startswith("migration_"):
                    z.writestr(name, b"synthetic")
        fake.back = archive({"app.jar": with_zip.getvalue()})
        result = probe.check(fake)
        self.assertEqual(result["backend_oidc"], "PARTIAL_MARKERS")
        self.assertEqual(result["artifacts_feature_ready"],
                         "BLOCKED_RUNNING_V2_ARTIFACTS_INCOMPLETE")
        self.assertIs(result["g0_b2_install_permitted"], False)

    def test_each_immutable_migration_is_mandatory(self):
        for missing in ("migration_v28", "migration_v29"):
            with self.subTest(missing=missing):
                result = probe.check(FakeRunner(missing_class=(missing,)))
                self.assertEqual(result["backend_oidc"], "PARTIAL_MARKERS")
                self.assertEqual(result["artifacts_feature_ready"],
                                 "BLOCKED_RUNNING_V2_ARTIFACTS_INCOMPLETE")

    def test_old_artifacts_report_absent_without_calling_backend_apis(self):
        result = probe.check(FakeRunner(
            missing_js=tuple(probe.JS_MARKERS.values()),
            missing_class=tuple(probe.CLASSES.values())))
        self.assertEqual(result["gateway_oidc"], "ABSENT")
        self.assertEqual(result["backend_oidc"], "ABSENT")

    def test_unavailable_container_prevents_copy(self):
        fake = FakeRunner(backend=False)
        result = probe.check(fake)
        self.assertEqual(result["artifacts_feature_ready"],
                         "BLOCKED_UNAVAILABLE_CONTAINER")
        self.assertEqual(len(fake.calls), 2)

    def test_arbitrary_docker_cp_paths_rejected(self):
        for name, source in (("matrix-mysql", "/var/lib/mysql"),
                             (probe.GATEWAY, "/etc/nginx/nginx.conf"),
                             (probe.BACKEND, "/root/.env")):
            with self.subTest(name=name, source=source):
                with self.assertRaisesRegex(probe.InventoryError,
                                            "UNREVIEWED_CONTAINER_OR_PATH"):
                    probe.docker_copy_tar(name, source, 100)

    def test_bad_archive_and_absent_jar_fail_closed(self):
        with self.assertRaises(probe.InventoryError):
            probe.scan_js(b"not tar")
        with self.assertRaises(probe.InventoryError):
            probe.scan_jar(archive({"other.jar": jar_bytes(())}))

    def test_no_secret_names_or_writes_in_source(self):
        from pathlib import Path
        source = Path(probe.__file__).read_text(encoding="utf-8")
        self.assertNotIn("Config.Env", source)
        for forbidden in ("docker exec", "docker restart", "docker run",
                          "docker cp -", "docker inspect .Config.Env",
                          "docker compose", "mysql -", "pg_dump",
                          "nginx -s", "systemctl restart",
                          "docker rm", "curl "):
            # 'docker cp container:path -' is deliberately read-only; only
            # source-independent shell / control verbs must be absent.
            if forbidden != "docker cp -":
                self.assertNotIn(forbidden, source)
        self.assertEqual(probe.GATEWAY, "prp-mcp-v2-gateway-1")
        self.assertEqual(probe.BACKEND, "prp-mcp-v2-backend-1")


if __name__ == "__main__":
    unittest.main()
