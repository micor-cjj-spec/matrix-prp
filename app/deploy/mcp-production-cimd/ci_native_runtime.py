#!/usr/bin/env python3
"""Runtime smoke for an actual official, disposable Keycloak+native CIMD JAR.

Uses a CI-only imported Realm and temporary bootstrap admin; never touches the
user's live Keycloak/PostgreSQL, backups, or ChatGPT assertion. Report only
fixed non-secret booleans/status categories. No raw HTTP response logging.
"""
import json
import os
import secrets
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from http.client import HTTPException
from urllib.parse import urlencode
from urllib.request import Request, urlopen, build_opener, ProxyHandler, HTTPRedirectHandler

LOCAL = "http://127.0.0.1:18880"
REALM = "prp-mcp-prod"
CLIENT = "https://chatgpt.com/oauth/client.json"
JWKS = "https://chatgpt.com/oauth/jwks.json"
ISSUER = "https://auth.micor.top/realms/" + REALM
PASSWORD = os.environ["PRP_CIMD_CLONE_PASSWORD"]
NAME = os.environ["PRP_CIMD_CLONE_NAME"]
VERSION = os.environ["PRP_CIMD_CLONE_VERSION"]
CLIENT_POLICY = "prp-health-exact"
CIMD_EXECUTOR = "prp-health-cimd-metadata"
PASS = []

def check(name, condition):
    if not condition:
        raise RuntimeError(name)
    PASS.append(name)
    print("PASS CIMD_NATIVE " + name, flush=True)

def query(path, method="GET", token=None, body=None, form=False):
    if not path.startswith("/") or "://" in path or "?" in path:
        raise RuntimeError("DISALLOWED_PATH")
    headers = {
        "Host": "auth.micor.top",
        "X-Forwarded-Host": "auth.micor.top",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Port": "443"
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        data = (urlencode(body) if form else json.dumps(body)).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    req = Request(LOCAL + path, headers=headers, data=data, method=method)
    try:
        response = urlopen(req, timeout=7)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read(200001)
        if len(raw) > 200000:
            raise RuntimeError("HTTP_SIZE_LIMIT")
        obj = json.loads(raw) if raw else None
        return response.status, obj

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_OS") != "Linux":
        raise RuntimeError("GITHUB_RUNNER_ONLY")
    if not NAME.startswith("prp-cimd-runtime-") or VERSION not in {"26.8.1", "26.8.2"}:
        raise RuntimeError("INVALID_CLONE_NAME")
    print("CI_KEYCLOAK_VERSION=" + VERSION, flush=True)
    ready = False
    for _ in range(100):
        try:
            code, doc = query("/realms/" + REALM + "/.well-known/openid-configuration")
            if code == 200 and isinstance(doc, dict):
                ready = True
                break
        except (OSError, HTTPException, TimeoutError, json.JSONDecodeError):
            # Docker's published port can accept early while Keycloak is still
            # loading providers/database; a reset is not a Realm failure.
            pass
        time.sleep(2)
    check("keycloak_real_process_started", ready)
    check("cimd_discovery_issuer", doc.get("issuer") == ISSUER)
    check("private_key_jwt_advertised", "private_key_jwt" in doc.get("token_endpoint_auth_methods_supported", []))
    check("pkce_s256_advertised", "S256" in doc.get("code_challenge_methods_supported", []))
    check("native_cimd_advertised", doc.get("client_id_metadata_document_supported") is True)
    check("no_dynamic_registration_endpoint", not doc.get("registration_endpoint"))

    code, oauth = query("/realms/" + REALM + "/.well-known/oauth-authorization-server")
    check("oauth_as_metadata_available", code == 200 and isinstance(oauth, dict))
    check("oauth_as_native_cimd_advertised", oauth.get("client_id_metadata_document_supported") is True)

    # Use the CI-only bootstrap administrator to read and modify the clone
    # policy. The API call is HTTP loopback on the runner, never production.
    code, t = query("/realms/master/protocol/openid-connect/token",
                    method="POST", form=True,
                    body={"grant_type": "password", "client_id": "admin-cli",
                          "username": "prp-ci-admin", "password": PASSWORD})
    check("clone_admin_token_received", code == 200 and isinstance(t, dict) and bool(t.get("access_token")))
    access = t["access_token"]
    prefix = "/admin/realms/" + REALM
    code, clients = query(prefix + "/clients", token=access)
    exact = [c for c in clients if c.get("clientId") == CLIENT] if isinstance(clients, list) else []
    check("pre_registered_chatgpt_client_unique", code == 200 and len(exact) == 1)
    cid = exact[0]["id"]
    code, original = query(prefix + "/clients/" + cid, token=access)
    check("pre_registered_client_private_jwt",
          code == 200 and original.get("clientAuthenticatorType") == "client-jwt"
          and original.get("publicClient") is False)
    attr = original.get("attributes") or {}
    check("original_jwks_source_and_pkce",
          attr.get("use.jwks.url") == "true" and attr.get("jwks.url") == JWKS
          and attr.get("pkce.code.challenge.method") == "S256")
    check("original_health_scopes_not_default_write",
          set(original.get("defaultClientScopes") or []) == {"basic"}
          and set(original.get("optionalClientScopes") or []) ==
              {"prp.wellness.read", "prp.wellness.write.create",
               "prp.wellness.write.update", "prp.wellness.write.delete",
               "prp.wellness.write.status", "prp.wellness.write.confirm"})

    code, profiles = query(prefix + "/client-policies/profiles", token=access)
    entries = profiles.get("profiles", []) if isinstance(profiles, dict) else []
    selected = [p for p in entries if p.get("name") == CLIENT_POLICY]
    check("existing_precise_client_policy_profile", code == 200 and len(selected) == 1)
    p = selected[0]
    executors = list(p.get("executors") or [])
    check("native_candidate_not_preinstalled", all(e.get("executor") != CIMD_EXECUTOR for e in executors))
    # Native CIMD options are locked to exact domain/resource and confidential
    # clients. This tests Keycloak's *real* provider registration/validation.
    config = {
        "cimd-allow-http-scheme": "false",
        "cimd-allow-permitted-domains": ["chatgpt.com", "persistent.oaistatic.com"],
        "cimd-restrict-same-domain": "false",
        "only-allow-confidential-client": "true",
        "cimd-resource-indicator-allow-list": ["https://micor.top/api/mcp"]
    }
    p["executors"] = [{"executor": CIMD_EXECUTOR, "configuration": config}] + executors
    # GET can include Keycloak-managed read-only globalProfiles. PUT accepts
    # only the Realm-owned profiles; never replay server-owned global profiles.
    code, rejected = query(prefix + "/client-policies/profiles", method="PUT",
                           token=access, body={"profiles": entries})
    if code not in (200, 204):
        detail = json.dumps(rejected).lower() if rejected is not None else ""
        categories = {
            "INVALID_EXECUTOR": any(x in detail for x in ("unknown executor", "invalid executor", "unsupported executor")),
            "INVALID_CONFIGURATION": any(x in detail for x in ("configuration", "invalid property", "validation")),
            "GLOBAL_PROFILE": "global" in detail,
            "BAD_REQUEST": code == 400
        }
        print("CIMD_POLICY_PUT_HTTP_STATUS=" + str(code), flush=True)
        print("CIMD_POLICY_PUT_SAFE_CATEGORIES=" + json.dumps(categories, sort_keys=True), flush=True)
        # Clone-only logs: collect fixed diagnostic class names, NEVER raw lines,
        # request bodies, environment, URLs, bearer tokens or stack text.
        proc = subprocess.run(["docker", "logs", "--since", "2m", NAME],
                              capture_output=True, text=True, timeout=10, check=False)
        logs = (proc.stdout + proc.stderr)[-100000:]
        flags = {
            "NullPointerException": "NullPointerException" in logs,
            "ClassCastException": "ClassCastException" in logs,
            "IllegalArgumentException": "IllegalArgumentException" in logs,
            "IllegalStateException": "IllegalStateException" in logs,
            "NoClassDefFoundError": "NoClassDefFoundError" in logs,
            "ProviderException": "ProviderException" in logs,
            "ClientPolicyException": "ClientPolicyException" in logs
        }
        frames = sorted(set(re.findall(r"at ((?:io|org)\\.keycloak\\.[A-Za-z0-9_.$]+|io\\.micor\\.prp\\.health\\.[A-Za-z0-9_.$]+)", logs)))
        print("CLONE_POLICY_ERROR_FLAGS=" + json.dumps(flags, sort_keys=True), flush=True)
        print("CLONE_POLICY_STACK_CLASSES=" + json.dumps(frames[:12]), flush=True)
        # Error messages are read only from our CI-created disposable Realm.
        # Emit a bounded, letter-only classifier: never dump log lines or data.
        reasons = []
        for line in logs.splitlines():
            if "java.lang.IllegalArgumentException:" in line:
                tail = line.split("java.lang.IllegalArgumentException:", 1)[1][:120]
                safe = re.sub(r"[^A-Za-z _.-]", "_", tail).strip()
                reasons.append(safe)
        print("CLONE_IAE_REASONS=" + json.dumps(list(dict.fromkeys(reasons))[:3]), flush=True)
    check("native_cimd_executor_accepted_by_keycloak", code in (200, 204))
    code, updated = query(prefix + "/client-policies/profiles", token=access)
    selected = [p for p in updated.get("profiles", []) if p.get("name") == CLIENT_POLICY] if isinstance(updated, dict) else []
    check("cimd_executor_policy_persisted",
          code == 200 and len(selected) == 1 and any(
              e.get("executor") == CIMD_EXECUTOR for e in selected[0].get("executors") or []))
    code, after = query(prefix + "/clients/" + cid, token=access)
    check("pre_registered_client_uuid_and_security_preserved",
          code == 200 and after.get("id") == cid and after.get("clientId") == CLIENT
          and after.get("clientAuthenticatorType") == original.get("clientAuthenticatorType")
          and after.get("attributes") == original.get("attributes"))
    # Execute a real pre-authorization request with the exact URL client_id.
    # It must trigger the Keycloak JVM's native CIMD policy and the custom
    # metadata/JWKS HTTPS fetch through the fixed-destination CONNECT broker.
    # No login and no signed assertion are sent by this probe.
    counters = Path(os.environ["PRP_CIMD_EGRESS_COUNTERS"])
    def allowed_connect_count():
        try:
            return int(json.loads(counters.read_text()).get("allowed_connect", 0))
        except (OSError, ValueError, TypeError):
            return 0
    before = allowed_connect_count()
    params = {
        "client_id": CLIENT,
        "redirect_uri": "https://chatgpt.com/connector_platform_oauth_redirect",
        "response_type": "code",
        "scope": "prp.wellness.read",
        "resource": "https://micor.top/api/mcp",
        "code_challenge_method": "S256",
        "code_challenge": "A" * 43,
        "state": secrets.token_urlsafe(20)
    }
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    client = build_opener(ProxyHandler({}), NoRedirect())
    req = Request(LOCAL + "/realms/" + REALM + "/protocol/openid-connect/auth?" +
                  urlencode(params), headers={
                      "Host": "auth.micor.top",
                      "X-Forwarded-Host": "auth.micor.top",
                      "X-Forwarded-Proto": "https",
                      "X-Forwarded-Port": "443"
                  })
    try:
        response = client.open(req, timeout=22)
    except HTTPError as exc:
        response = exc
    with response:
        auth_status = response.status
        response.read(16384)  # Never print a response body, URL, or redirect.
    after_fetch = allowed_connect_count()
    print("NATIVE_CIMD_AUTHORIZATION_HTTP_STATUS=" + str(auth_status), flush=True)
    print("NATIVE_CIMD_PUBLIC_TLS_CONNECTIONS=" + str(after_fetch - before), flush=True)
    check("keycloak_jvm_real_cimd_public_fetch", after_fetch - before >= 2)
    check("real_cimd_authorization_reaches_login", auth_status in (200, 302, 303))
    code, adopted = query(prefix + "/clients/" + cid, token=access)
    required_attrs = ("use.jwks.url", "jwks.url", "pkce.code.challenge.method", "token.endpoint.auth.signing.alg")
    check("cimd_existing_client_id_preserved", code == 200 and adopted.get("id") == cid)
    check("cimd_existing_client_auth_config_preserved",
          code == 200 and adopted.get("clientAuthenticatorType") == "client-jwt"
          and adopted.get("publicClient") is False and
          all((adopted.get("attributes") or {}).get(a) == attr.get(a)
              for a in required_attrs))
    check("cimd_health_scopes_not_broadened",
          set(adopted.get("defaultClientScopes") or []) == {"basic"}
          and set(adopted.get("optionalClientScopes") or []) ==
              set(original.get("optionalClientScopes") or []))
    print("PUBLIC_CIMD_METADATA_FETCH_VERIFIED=True", flush=True)
    print("NATIVE_CIMD_RUNTIME_SUCCESS checks=" + str(len(PASS)), flush=True)
    print("PRODUCTION_CHANGED=False", flush=True)
    print("ACTUAL_CHATGPT_ASSERTION_VERIFIED=False", flush=True)
    print("PRODUCTION_REALM_RESTORE_VERIFIED_BY_THIS_RUN=False", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print HTTP body, URL query, bearer token, admin credential,
        # Keycloak container environment, or raw exception messages.
        label = str(exc)
        if not label.isidentifier() or len(label) > 90:
            label = type(exc).__name__
        print("FAIL CIMD_NATIVE " + label, flush=True)
        raise SystemExit(1) from None
