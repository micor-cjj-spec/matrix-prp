#!/usr/bin/env python3
"""CI-only comparison of Keycloak 26.8.1 and the official JWT error patch.

Entirely disposable: no real OAuth assertion, keys, accounts, URLs or databases.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parent
COMMIT = "0b48783ead3b9ad8cb72428c1263c649ad43633a"
PATHS = [
    "services/src/main/java/org/keycloak/authentication/AuthenticationProcessor.java",
    "services/src/main/java/org/keycloak/authentication/ClientAuthenticationFlow.java",
    "services/src/main/java/org/keycloak/authentication/authenticators/client/AbstractJWTClientValidator.java",
]
KC_IMAGE = "quay.io/keycloak/keycloak:26.8.1"
KC_JAR = "org.keycloak.keycloak-services-26.8.1.jar"
PORT, REALM, CLIENT = 18188, "prp-jwt-diag-ci", "jwt-event-ci"
OPENER = build_opener(ProxyHandler({}))


def run(args, *, cwd=None, stdin=None, timeout=240, echo=False):
    p = subprocess.run(args, cwd=cwd, input=stdin, text=True,
                       capture_output=not echo, timeout=timeout)
    if p.returncode:
        raise RuntimeError("ISOLATED_COMMAND_FAILED_" + Path(args[0]).name)
    return p.stdout if not echo else ""


def req(method, path, data=None, bearer=None):
    headers = {}
    payload = None
    if data is not None:
        payload = urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    url = "http://127.0.0.1:" + str(PORT) + path
    try:
        response = OPENER.open(Request(url, data=payload, headers=headers,
                                       method=method), timeout=8)
    except HTTPError as e:
        response = e
    with response:
        raw = response.read(30000)
        try:
            body = json.loads(raw) if raw else {}
        except (ValueError, UnicodeDecodeError):
            body = {}
        return response.status, body


def bad_assertion():
    stamp = int(time.time())
    enc = lambda d: base64.urlsafe_b64encode(
        json.dumps(d, separators=(",", ":")).encode()).decode().rstrip("=")
    return enc({"alg": "none", "typ": "JWT"}) + "." + enc({
        "iss": CLIENT, "sub": CLIENT,
        "aud": "http://127.0.0.1:" + str(PORT) + "/realms/" +
               REALM + "/protocol/openid-connect/token",
        "iat": stamp, "nbf": stamp - 2, "exp": stamp + 60,
        "jti": secrets.token_urlsafe(20)}) + "."


def probe(image, label, realm_file, admin_password):
    container = "prp-jwt-diag-ci"
    try:
        run(["docker", "run", "-d", "--name", container,
             "--memory", "1200m", "--pids-limit", "128",
             "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
             "-p", "127.0.0.1:" + str(PORT) + ":8080",
             "-e", "KC_BOOTSTRAP_ADMIN_USERNAME=ci-jwt-admin",
             "-e", "KC_BOOTSTRAP_ADMIN_PASSWORD=" + admin_password,
             "-v", str(realm_file) + ":/opt/keycloak/data/import/realm.json:ro",
             image, "start-dev", "--import-realm", "--http-port=8080",
             "--hostname=http://127.0.0.1:" + str(PORT)], timeout=60)
        for i in range(180):
            try:
                status, _ = req("GET", "/realms/" + REALM +
                                "/.well-known/openid-configuration")
                if status == 200:
                    break
            except (OSError, TimeoutError):
                # Startup may briefly accept TCP and reset it during Quarkus
                # augmentation; that is not an OAuth diagnostic failure.
                pass
            time.sleep(1)
        else:
            raise RuntimeError("CI_KEYCLOAK_NOT_READY_" + label)
        status, token = req("POST",
            "/realms/master/protocol/openid-connect/token", {
                "grant_type": "password", "client_id": "admin-cli",
                "username": "ci-jwt-admin", "password": admin_password})
        if status != 200 or not token.get("access_token"):
            raise RuntimeError("CI_ADMIN_LOGIN_FAILED_" + label)
        status, body = req("POST",
            "/realms/" + REALM + "/protocol/openid-connect/token", {
                "grant_type": "client_credentials",
                "client_id": CLIENT,
                "client_assertion_type":
                    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": bad_assertion()})
        if status not in (400, 401) or body.get("error") != "invalid_client":
            raise RuntimeError("INVALID_JWT_NOT_REJECTED_" + label)
        for i in range(15):
            status, records = req("GET",
                "/admin/realms/" + REALM + "/events?max=20",
                bearer=token["access_token"])
            if status != 200 or not isinstance(records, list):
                raise RuntimeError("CI_EVENTS_API_FAILED_" + label)
            failures = [e for e in records
                if e.get("type") in ("CLIENT_LOGIN_ERROR", "CODE_TO_TOKEN_ERROR")
                and e.get("error") == "invalid_client_credentials"]
            if failures:
                break
            time.sleep(.3)
        if not failures:
            raise RuntimeError("CI_CLIENT_ERROR_EVENT_MISSING_" + label)
        details = [x.get("details") or {} for x in failures]
        has_detail = any(bool(x.get("authentication_error_detail"))
                         for x in details if isinstance(x, dict))
        exact = any(x.get("authentication_error_detail") ==
                    "Invalid signature algorithm"
                    for x in details if isinstance(x, dict))
        return {"invalid_jwt_rejected": True, "event_observed": True,
                "error_detail_present": has_detail,
                "expected_algorithm_detail": exact}
    finally:
        subprocess.run(["docker", "rm", "-f", container],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def patched_image(temp):
    base, fixed = Path("upstream-base").resolve(), Path("upstream-fixed").resolve()
    if not all((base / p).is_file() and (fixed / p).is_file() for p in PATHS):
        raise RuntimeError("PINNED_UPSTREAM_SOURCES_MISSING")
    patch = run(["git", "diff", COMMIT + "^", COMMIT, "--", *PATHS], cwd=fixed)
    if not patch.strip():
        raise RuntimeError("UPSTREAM_PATCH_EMPTY")
    run(["git", "apply", "--check", "-"], cwd=base, stdin=patch)
    run(["git", "apply", "-"], cwd=base, stdin=patch)

    classpath = temp / "classpath"
    run(["mvn", "-B", "-ntp", "-f", str(ROOT / "auth-policy/pom.xml"),
         "dependency:build-classpath",
         "-Dmdep.outputFile=" + str(classpath)], timeout=360)
    classes = temp / "classes"
    classes.mkdir()
    run(["javac", "--release", "21",
         "-cp", classpath.read_text().strip(), "-d", str(classes),
         *[str(base / p) for p in PATHS]], timeout=180)
    count = len(list(classes.rglob("*.class")))
    if count < 3:
        raise RuntimeError("PATCH_CLASSES_MISSING")
    print("UPSTREAM_PATCH_COMPILED_CLASSES=", count)

    run(["docker", "pull", KC_IMAGE], timeout=240, echo=True)
    info = json.loads(run(["docker", "image", "inspect", KC_IMAGE]))[0]
    digests = [x for x in info.get("RepoDigests", [])
               if x.startswith("quay.io/keycloak/keycloak@sha256:")]
    if not digests:
        raise RuntimeError("KEYCLOAK_REPO_DIGEST_MISSING")
    cid = run(["docker", "create", KC_IMAGE]).strip()
    original = temp / KC_JAR
    try:
        run(["docker", "cp",
             cid + ":/opt/keycloak/lib/lib/main/" + KC_JAR, str(original)])
    finally:
        subprocess.run(["docker", "rm", "-f", cid],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    overlay = temp / "patched-services.jar"
    overlay.write_bytes(original.read_bytes())
    run(["jar", "uf", str(overlay), "-C", str(classes), "."])
    dockerfile = temp / "Dockerfile"
    dockerfile.write_text(
        "ARG KC_BASE=quay.io/keycloak/keycloak:26.8.1\nFROM $KC_BASE\n"
        "COPY --chown=1000:0 patched-services.jar "
        "/opt/keycloak/lib/lib/main/" + KC_JAR + "\n"
        "RUN /opt/keycloak/bin/kc.sh build --db=dev-file\n"
        "ENTRYPOINT [\"/opt/keycloak/bin/kc.sh\"]\n")
    tag = "prp-keycloak-jwt-error-detail:ci"
    run(["docker", "build", "--pull=false", "--build-arg",
         "KC_BASE=" + digests[0], "-t", tag,
         "-f", str(dockerfile), str(temp)], timeout=600, echo=True)
    return tag


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true" or
        os.environ.get("RUNNER_OS") != "Linux" or
        os.environ.get("PRP_DISPOSABLE_JWT_DIAG") != "1" or
        not os.environ.get("RUNNER_TEMP")):
        raise RuntimeError("DISPOSABLE_RUNNER_REQUIRED")
    for name in ("KC_DB_PASSWORD", "MATRIX_PRP_DB_PASSWORD",
                 "PRP_HEALTH_AUTH_IMAGE", "PRP_HEALTH_POSTGRES_IMAGE"):
        if os.environ.get(name):
            raise RuntimeError("PRODUCTION_ENV_PRESENT")
    with tempfile.TemporaryDirectory(prefix="ci-jwt-detail-",
                                     dir=os.environ["RUNNER_TEMP"]) as td:
        temp = Path(td)
        temp.chmod(0o700)
        password = secrets.token_urlsafe(36)
        key, cert = temp / "ci.key", temp / "ci.crt"
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048",
             "-nodes", "-days", "1", "-keyout", str(key),
             "-out", str(cert), "-subj", "/CN=jwt-diagnostic-ci"])
        key.chmod(0o600)
        realm = temp / "realm.json"
        realm.write_text(json.dumps({
            "realm": REALM, "enabled": True, "eventsEnabled": True,
            "eventsExpiration": 600,
            "enabledEventTypes": ["CLIENT_LOGIN_ERROR", "CODE_TO_TOKEN_ERROR"],
            "clients": [{
                "clientId": CLIENT, "enabled": True,
                "protocol": "openid-connect", "publicClient": False,
                "clientAuthenticatorType": "client-jwt",
                "standardFlowEnabled": True, "serviceAccountsEnabled": True,
                "directAccessGrantsEnabled": False,
                "attributes": {
                    "use.jwks.url": "false",
                    "jwt.credential.certificate": cert.read_text(),
                    "token.endpoint.auth.signing.alg": "RS256"
                }
            }]
        }))
        # The realm contains public synthetic client settings only. Make
        # the bind-mounted file readable by Keycloak's unprivileged UID.
        realm.chmod(0o644)
        overlay_tag = patched_image(temp)
        base_result = probe(KC_IMAGE, "baseline", realm, password)
        fixed_result = probe(overlay_tag, "patched", realm, password)
        print("JWT_ERROR_COMPARE_SAFE " + json.dumps({
            "base_version": "26.8.1",
            "upstream_commit": COMMIT[:12],
            "baseline": base_result, "patched": fixed_result
        }))
        if (base_result["error_detail_present"] or
            not fixed_result["expected_algorithm_detail"]):
            raise RuntimeError("UPSTREAM_PATCH_RUNTIME_DETAIL_NOT_VERIFIED")
        print("PINNED_UPSTREAM_JWT_ERROR_DETAIL_COMPARISON_PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Only static, self-generated error codes; no arbitrary tool logs,
        # OAuth data, tokens, assertions, credentials or raw event content.
        print("CI_DIAG_ERROR_CLASS=", type(exc).__name__,
              "REASON=", str(exc)[:90])
        sys.exit(1)
