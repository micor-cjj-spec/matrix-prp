#!/usr/bin/env python3
"""Strict read-only inventory of deployed V2 frontend/backend OIDC artifacts.

No Docker exec, docker inspect environment, MySQL, network requests, token,
settings, migrations, deployment, source checkout, or Nginx reload.
Read only TWO named running containers' fixed files via docker cp - (tar stream),
inspect marker PRESENCE locally in memory, emit only bounded status labels.
Never print image/JAR/asset contents, filenames, credentials or metadata.
This is NOT a release gate or evidence of real login/API functionality.
"""
import hashlib
import io
import json
import subprocess
import tarfile
import zipfile

GATEWAY = "prp-mcp-v2-gateway-1"
BACKEND = "prp-mcp-v2-backend-1"
ASSETS = "/usr/share/nginx/html/assets"
JAR = "/opt/prp/app.jar"
MAX_ASSET_TAR = 45 * 1024 * 1024
MAX_JAR_TAR = 180 * 1024 * 1024
MAX_JAR_ZIP_ENTRIES = 50000
MAX_MIGRATION_SQL_BYTES = 1024 * 1024
# Git blob identities pinned to PR #131's immutable V28/V29 SQL. This check
# is offline byte parity, not independent signing or release authorization.
REVIEWED_MIGRATION_BLOBS = {
    "BOOT-INF/classes/db/migration/V28__mcp_temporary_client_grant_expiry.sql":
        "3492e186c46f7eeee16942d43a23b219bec81c8d",
    "BOOT-INF/classes/db/migration/V29__mcp_first_party_oidc_link_flows.sql":
        "73d306ea3cc6e2f0d0806ea58ec8f11883621bea",
}
JS_MARKERS = {
    b"/me/mcp-link/callback": "callback",
    b"/mcp/identity/oidc/start": "start",
    b"/mcp/identity/oidc/finish": "finish",
}
CLASSES = {
    "BOOT-INF/classes/com/matrix/prp/mcp/McpFirstPartyOidcLinkController.class":
        "controller",
    "BOOT-INF/classes/com/matrix/prp/mcp/McpFirstPartyOidcLinkService.class":
        "service",
    # V28 is the immutable 10-minute pairing lease migration; the
    # first-party OIDC table was moved to V29 in the reconciled lineage.
    "BOOT-INF/classes/db/migration/V28__mcp_temporary_client_grant_expiry.sql":
        "migration_v28",
    "BOOT-INF/classes/db/migration/V29__mcp_first_party_oidc_link_flows.sql":
        "migration_v29",
}


class InventoryError(Exception):
    pass


def running(container, runner=subprocess.run):
    # Fixed names only. Never inspect container environment or other containers.
    try:
        result = runner(
            ["docker", "inspect", "-f", "{{.State.Status}}", container],
            capture_output=True, timeout=8, check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == b"running"
    except (subprocess.TimeoutExpired, OSError):
        return False


def docker_copy_tar(container, source, maximum, runner=subprocess.run):
    if (container, source) not in ((GATEWAY, ASSETS), (BACKEND, JAR)):
        raise InventoryError("UNREVIEWED_CONTAINER_OR_PATH")
    # docker cp container:/abs/path - writes a TAR stream to stdout, not to
    # the host file system. Never use an arbitrary container, path or shell.
    try:
        process = runner(
            ["docker", "cp", container + ":" + source, "-"],
            capture_output=True, timeout=28, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise InventoryError("DOCKER_COPY_READ_UNAVAILABLE") from exc
    if process.returncode != 0:
        raise InventoryError("DOCKER_COPY_READ_FAILED")
    if len(process.stdout) > maximum:
        raise InventoryError("DOCKER_COPY_STREAM_TOO_LARGE")
    return process.stdout


def tar_regular_members(tar_bytes, *, max_total=180*1024*1024):
    try:
        output = []
        expanded = 0
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as archive:
            for member in archive:
                # Never follow symlinks, device nodes or hostile names.
                if not member.isfile() or member.name.startswith("/") or ".." in member.name.split("/"):
                    continue
                if member.size < 0 or member.size > max_total:
                    raise InventoryError("ARCHIVE_MEMBER_TOO_LARGE")
                expanded += member.size
                if expanded > max_total:
                    raise InventoryError("ARCHIVE_TOTAL_TOO_LARGE")
                stream = archive.extractfile(member)
                if stream is None:
                    continue
                output.append((member.name, stream.read(member.size + 1)))
        return output
    except (tarfile.TarError, OSError, EOFError, ValueError) as e:
        raise InventoryError("INVALID_DOCKER_TAR") from e


def scan_js(tar_bytes):
    entries = tar_regular_members(tar_bytes, max_total=MAX_ASSET_TAR)
    js = [blob for name, blob in entries if name.endswith(".js")]
    if not js:
        raise InventoryError("NO_FRONTEND_JAVASCRIPT_ASSETS")
    return {label: any(marker in blob for blob in js)
            for marker, label in JS_MARKERS.items()}


def scan_jar(tar_bytes):
    matches = [(name, blob) for name, blob in tar_regular_members(tar_bytes)
               if name.rsplit("/", 1)[-1] == "app.jar"]
    if len(matches) != 1:
        raise InventoryError("BACKEND_JAR_NOT_EXACTLY_ONE")
    try:
        with zipfile.ZipFile(io.BytesIO(matches[0][1])) as zf:
            entries = zf.infolist()
            if len(entries) > MAX_JAR_ZIP_ENTRIES:
                raise InventoryError("BACKEND_JAR_TOO_MANY_ENTRIES")
            filenames = [entry.filename for entry in entries]
            if len(set(filenames)) != len(filenames):
                raise InventoryError("BACKEND_JAR_DUPLICATE_ENTRIES")
            names = set(filenames)
            observed = {label: path in names for path, label in CLASSES.items()}
            for path, expected_blob in REVIEWED_MIGRATION_BLOBS.items():
                if path not in names:
                    continue
                entry = zf.getinfo(path)
                if not (0 < entry.file_size <= MAX_MIGRATION_SQL_BYTES):
                    raise InventoryError("BACKEND_JAR_SQL_SIZE_NOT_TRUSTED")
                raw = zf.read(entry)
                # Git blob object: SHA1("blob " + byte length + NUL + SQL bytes).
                # Never print or export SQL bytes or archive contents.
                header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
                actual_blob = hashlib.sha1(header + raw).hexdigest()
                observed[CLASSES[path]] = actual_blob == expected_blob
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError) as e:
        raise InventoryError("BACKEND_JAR_INVALID") from e
    return observed


def status(observed):
    if not observed or not any(observed.values()):
        return "ABSENT"
    if all(observed.values()):
        return "ALL_PRESENT"
    return "PARTIAL_MARKERS"


def check(runner=subprocess.run):
    report = {
        "purpose": "RUNNING_V2_OIDC_ARTIFACTS_READ_ONLY",
        "gateway_running": "UNKNOWN",
        "backend_running": "UNKNOWN",
        "gateway_oidc": "UNVERIFIED",
        "backend_oidc": "UNVERIFIED",
        "artifacts_feature_ready": "UNVERIFIED",
        "live_oidc_flow_verified": False,
        "g0_b2_install_permitted": False,
        "docker_state_changed": False,
    }
    report["gateway_running"] = "YES" if running(GATEWAY, runner) else "NO"
    report["backend_running"] = "YES" if running(BACKEND, runner) else "NO"
    if report["gateway_running"] != "YES" or report["backend_running"] != "YES":
        report["artifacts_feature_ready"] = "BLOCKED_UNAVAILABLE_CONTAINER"
        return report
    try:
        assets = scan_js(docker_copy_tar(GATEWAY, ASSETS, MAX_ASSET_TAR, runner))
        jar = scan_jar(docker_copy_tar(BACKEND, JAR, MAX_JAR_TAR, runner))
        report["gateway_oidc"] = status(assets)
        report["backend_oidc"] = status(jar)
        report["artifacts_feature_ready"] = (
            "SOURCE_MARKERS_PRESENT_REVIEW_ONLY"
            if all(assets.values()) and all(jar.values())
            else "BLOCKED_RUNNING_V2_ARTIFACTS_INCOMPLETE"
        )
    except InventoryError as exc:
        report["artifacts_feature_ready"] = "BLOCKED_OR_UNVERIFIED"
        report["safe_diagnostic"] = str(exc)
    return report


if __name__ == "__main__":
    print(json.dumps(check(), sort_keys=True))
