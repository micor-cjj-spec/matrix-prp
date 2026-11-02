#!/usr/bin/env python3
"""Fail-closed read-only validation of a *proposed* fresh-database Compose.

No Docker service is started. A unique ephemeral env file is generated in
the local caller's private tempfile, never written to the Git checkout.
The rendered Compose JSON is captured in memory, not printed (secrets).
"""
import json
from pathlib import Path
import subprocess
import tempfile

from check_env import check
from prepare_env import make_config, write_secrets_file


NAME = "prp-mcp-newdb-review"
DATABASE = "matrix_prp_mcp_newdb_review"
PORT = "18083"
PROFILE = "newdb-review"
EXPECTED_VOLUMES = {
    "mysql": {"newdb_mysql": "/var/lib/mysql"},
    "backend": {"newdb_video": "/data/video", "newdb_vocal": "/data/vocal"},
    "gateway": {},
}
EXPECTED_NETWORKS = {
    "mysql": {"newdb_private"},
    "backend": {"newdb_private", "newdb_egress"},
    "gateway": {"newdb_private", "newdb_egress"},
}
OFF_FLAGS = (
    "MATRIX_PRP_MCP_ENABLED",
    "MATRIX_PRP_MCP_OAUTH_ENABLED",
    "MATRIX_PRP_MCP_WRITE_ENABLED",
    "MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_ENABLED",
    "MATRIX_PRP_AI_SPRING_AI_ENABLED",
    "MATRIX_PRP_AI_SPRING_AI_TOOLS_ENABLED",
)


def require(condition, code):
    if not condition:
        raise AssertionError(code)


def validate(candidate, env):
    """Validate parsed Compose structure, never its raw secret-bearing JSON."""
    checked = check(env)
    require(not any((checked["mcp_enabled"], checked["oauth_enabled"],
                     checked["first_party_enabled"])), "REVIEW_ENV_FEATURES_NOT_OFF")
    require(candidate.get("name") == NAME, "REVIEW_WRONG_PROJECT")
    services = candidate.get("services")
    require(isinstance(services, dict) and set(services) == set(EXPECTED_VOLUMES),
            "REVIEW_UNEXPECTED_SERVICES")
    volumes = candidate.get("volumes")
    require(isinstance(volumes, dict) and set(volumes) == {
        "newdb_mysql", "newdb_video", "newdb_vocal"}, "REVIEW_VOLUME_TOPOLOGY")
    for short, volume in volumes.items():
        require(volume.get("name") == NAME + "_" + short
                and not volume.get("external", False), "REVIEW_VOLUME_COLLISION")
    networks = candidate.get("networks")
    require(isinstance(networks, dict) and set(networks) == {
        "newdb_private", "newdb_egress"}, "REVIEW_NETWORK_TOPOLOGY")
    for short, network in networks.items():
        require(network.get("name") == NAME + "_" + short
                and not network.get("external", False), "REVIEW_NETWORK_COLLISION")
    require(networks["newdb_private"].get("internal") is True,
            "REVIEW_MYSQL_NETWORK_MUST_BE_INTERNAL")

    for name, svc in services.items():
        require(svc.get("profiles") == [PROFILE], "REVIEW_PROFILE_REQUIRED")
        for unsafe in ("network_mode", "privileged", "devices", "pid", "ipc",
                       "uts", "cgroup", "volumes_from", "extra_hosts"):
            require(unsafe not in svc, "REVIEW_HOST_BOUNDARY")
        require(set(svc.get("networks", {})) == EXPECTED_NETWORKS[name],
                "REVIEW_NETWORK_BOUNDARY")
        entries = svc.get("volumes", [])
        require(len(entries) == len(EXPECTED_VOLUMES[name]),
                "REVIEW_VOLUME_COUNT")
        actual = {}
        for v in entries:
            require(v.get("type") == "volume" and
                    v.get("read_only", False) is not True,
                    "REVIEW_NO_HOST_BINDS")
            actual[v["source"]] = v["target"]
        require(actual == EXPECTED_VOLUMES[name], "REVIEW_VOLUME_REUSED")
        ports = svc.get("ports", [])
        if name == "gateway":
            require(len(ports) == 1, "REVIEW_GATEWAY_PORT_COUNT")
            port = ports[0]
            require(str(port.get("published")) == PORT
                    and int(port.get("target", 0)) == 8080
                    and port.get("host_ip") == "127.0.0.1"
                    and port.get("protocol", "tcp") == "tcp",
                    "REVIEW_GATEWAY_NOT_LOOPBACK_18083")
        else:
            require(not ports and not svc.get("expose"),
                    "REVIEW_BACKEND_OR_MYSQL_EXPOSED")

    mysql = services["mysql"]
    require(mysql.get("image") == "mysql:8.4", "REVIEW_MYSQL_IMAGE")
    mysql_env = mysql.get("environment", {})
    require(mysql_env.get("MYSQL_DATABASE") == DATABASE and
            mysql_env.get("MYSQL_USER") == "prp_newdb"
            and mysql_env.get("MYSQL_PASSWORD") == env["PRP_STAGE_DB_PASSWORD"]
            and mysql_env.get("MYSQL_ROOT_PASSWORD") ==
            env["PRP_STAGE_DB_ROOT_PASSWORD"], "REVIEW_MYSQL_IDENTITY")
    backend = services["backend"]
    backend_env = backend.get("environment", {})
    require(backend_env.get("MATRIX_PRP_DB_URL", "").startswith(
        "jdbc:mysql://mysql:3306/" + DATABASE + "?")
        and backend_env.get("MATRIX_PRP_DB_USER") == "prp_newdb"
        and backend_env.get("MATRIX_PRP_DB_PASSWORD") ==
        env["PRP_STAGE_DB_PASSWORD"], "REVIEW_BACKEND_DATABASE_CROSSOVER")
    require(backend_env.get("MATRIX_PRP_FLYWAY_ENABLED") == "true",
            "REVIEW_FLYWAY_NOT_ENABLED")
    for flag in OFF_FLAGS:
        require(backend_env.get(flag) == "false", "REVIEW_FEATURE_PREMATURE_" + flag)
    for service, dockerfile in (
        ("backend", "app/deploy/mcp-staging/Dockerfile.backend"),
        ("gateway", "app/deploy/mcp-staging/Dockerfile.web"),
    ):
        build = services[service].get("build") or {}
        require(build.get("dockerfile") == dockerfile
                and str(build.get("context", "")).endswith("/matrix-prp"),
                "REVIEW_SOURCE_BUILD_CHANGED_" + service)
    gateway = services["gateway"]
    require(gateway.get("environment", {}).get("PRP_STAGE_HOST") ==
            env["PRP_STAGE_PUBLIC_HOST"], "REVIEW_HOST_DRIFT")
    require(gateway["build"]["args"].get(
        "VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT") ==
        env["PRP_STAGE_AUTH_ISSUER"] + "/protocol/openid-connect/auth",
        "REVIEW_OIDC_BROWSER_ISSUER_DRIFT")
    return True


def main():
    # This is intentionally an isolated CI-safe renderer, never a deployment.
    base = Path(__file__).resolve().parent
    env = make_config("prp-test.micor.top", "auth-test.micor.top", "stage_admin")
    with tempfile.TemporaryDirectory(prefix="prp-newdb-config-review-") as tmp:
        env_path = Path(tmp) / ".env"
        write_secrets_file(env_path, env)
        result = subprocess.run(
            ["docker", "compose", "--profile", PROFILE,
             "--env-file", str(env_path),
             "-f", str(base / "compose.newdb.review.yaml"),
             "config", "--format", "json"],
            capture_output=True, text=True, timeout=35, check=False)
        if result.returncode != 0:
            raise SystemExit("REVIEW_NEWDB_COMPOSE_RENDER_FAILED")
        try:
            validate(json.loads(result.stdout), env)
        except (AssertionError, ValueError, TypeError, KeyError):
            raise SystemExit("REVIEW_NEWDB_ISOLATION_CONTRACT_FAILED") from None
    print("PASS NEWDB REVIEW: fresh separate MySQL, loopback 18083, named volumes and networks.")
    print("PASS NEWDB REVIEW: all MCP/OAuth/write flags OFF; profile required; no Docker start.")
    print("NO_G0_B2_AUTHORIZATION_NO_INSTALL_NO_SECRETS_EXPORTED=YES")


if __name__ == "__main__":
    main()
