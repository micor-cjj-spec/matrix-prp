#!/usr/bin/env python3
"""Ephemeral CI ONLY: test exact two-client addition and rollback with 13 legacy fixtures.

Not a restored 13-client production/test Realm, not a backup, not a deployment
installer, and not authorization to write to active Keycloak. Uses the
throwaway localhost Keycloak started by mcp-oauth-keycloak-smoke.yml.
"""
import json
import os
import secrets
from urllib.parse import quote

import ci_chatgpt_cimd_pkce as kc
from review_exact_client_registrations import (
    CHATGPT, FIRST_PARTY, CHATGPT_CALLBACK, CHATGPT_JWKS,
    RESOURCE, PRP_CALLBACK, client_proposals, validate_proposals,
)

LEGACY_COUNT = 13
REQUIRED_SCOPES = {"basic", "offline_access", "prp.tasks.read"}


def require_disposable():
    if not (os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("CI_EXACT_CLIENT_PRESERVE") == "1"
            and os.environ.get("RUNNER_TEMP")
            and len(os.environ.get("MCP_TEST_ADMIN_PASSWORD", "")) >= 24
            and kc.BASE == "http://127.0.0.1:18080"
            and kc.REALM_ADMIN == kc.BASE + "/admin/realms/prp-mcp"):
        raise RuntimeError("REFUSED_NON_DISPOSABLE_KEYCLOAK")


def endpoint(suffix):
    if not suffix.startswith("/") or "//" in suffix:
        raise RuntimeError("REFUSED_UNTRUSTED_ADMIN_PATH")
    return kc.REALM_ADMIN + suffix


def read(token, suffix):
    status, _, raw = kc.request(endpoint(suffix), bearer=token)
    if status != 200:
        raise RuntimeError("CI_ADMIN_READ_FAILED")
    obj = json.loads(raw)
    if not isinstance(obj, (list, dict)):
        raise RuntimeError("CI_ADMIN_JSON_INVALID")
    return obj


def write(token, suffix, method, document=None):
    status, _, _ = kc.request(endpoint(suffix), method=method,
                             json_body=document, bearer=token)
    if status != (201 if method == "POST" else 204):
        raise RuntimeError("CI_EXACT_CLIENT_ADMIN_WRITE_REJECTED")


def clients(token):
    items = read(token, "/clients?max=100")
    if not isinstance(items, list):
        raise RuntimeError("CI_CLIENTS_NOT_LIST")
    ids = [x.get("clientId") for x in items]
    if len(ids) != len(set(ids)) or any(not isinstance(x, str) for x in ids):
        raise RuntimeError("CI_EXISTING_CLIENT_IDS_INVALID")
    return {x["clientId"]: x for x in items}


def details(token, inventory):
    return {client_id: read(token, "/clients/" + quote(item["id"], safe=""))
            for client_id, item in inventory.items()}


def created_one(token, client_id, payload, created_ids):
    before = clients(token)
    if client_id in before:
        raise RuntimeError("CI_CREATE_ONLY_CLIENT_COLLISION")
    write(token, "/clients", "POST", payload)
    after = clients(token)
    difference = set(after) - set(before)
    if difference != {client_id} or set(before) - set(after):
        raise RuntimeError("CI_CREATE_ONLY_INVENTORY_DRIFT")
    key = after[client_id].get("id")
    if not isinstance(key, str) or not key:
        raise RuntimeError("CI_NEW_CLIENT_ID_UNVERIFIED")
    created_ids.append((client_id, key))


def fixture(client_id):
    return {
        "clientId": client_id,
        "name": "Disposable preexisting client preservation fixture",
        "enabled": False,
        "protocol": "openid-connect",
        "publicClient": True,
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "fullScopeAllowed": False,
        "consentRequired": True,
        "defaultClientScopes": ["basic"],
        "optionalClientScopes": [],
        "redirectUris": [],
        "webOrigins": [],
    }


def verify_two(token, inventory):
    if CHATGPT not in inventory or FIRST_PARTY not in inventory:
        raise RuntimeError("CI_EXACT_CLIENT_ADDITION_MISSING")
    expected = {
        CHATGPT: (False, CHATGPT_CALLBACK, {"prp.tasks.read", "offline_access"}),
        FIRST_PARTY: (True, PRP_CALLBACK, set()),
    }
    for client_id, (public, callback, optional_expected) in expected.items():
        key = inventory[client_id]["id"]
        record = read(token, "/clients/" + quote(key, safe=""))
        if (record.get("clientId") != client_id
                or record.get("publicClient") is not public
                or record.get("redirectUris") != [callback]
                or record.get("standardFlowEnabled") is not True
                or record.get("implicitFlowEnabled") is not False
                or record.get("directAccessGrantsEnabled") is not False
                or record.get("serviceAccountsEnabled") is not False
                or record.get("fullScopeAllowed") is not False
                or record.get("consentRequired") is not True
                or record.get("attributes", {}).get("pkce.code.challenge.method") != "S256"):
            raise RuntimeError("CI_EXACT_CLIENT_SECURITY_DRIFT")
        optional = read(token, "/clients/" + quote(key, safe="") + "/optional-client-scopes")
        default = read(token, "/clients/" + quote(key, safe="") + "/default-client-scopes")
        if ({v.get("name") for v in optional} != optional_expected
                or "basic" not in {v.get("name") for v in default}):
            raise RuntimeError("CI_EXACT_CLIENT_SCOPE_DRIFT")
        if client_id == CHATGPT:
            attrs = record.get("attributes", {})
            if (record.get("clientAuthenticatorType") != "client-jwt"
                    or attrs.get("use.jwks.url") != "true"
                    or attrs.get("jwks.url") != CHATGPT_JWKS):
                raise RuntimeError("CI_EXACT_CLIENT_JWKS_DRIFT")
            mappers = read(token, "/clients/" + quote(key, safe="")
                           + "/protocol-mappers/models")
            if len([m for m in mappers if m.get("protocolMapper") == "oidc-audience-mapper"
                    and m.get("config", {}).get("included.custom.audience") == RESOURCE
                    and m.get("config", {}).get("access.token.claim") == "true"]) != 1:
                raise RuntimeError("CI_EXACT_CLIENT_AUDIENCE_DRIFT")


def main():
    require_disposable()  # Guard BEFORE token retrieval, network, or mutation.
    token = kc.admin_token()
    baseline = clients(token)
    if CHATGPT in baseline or FIRST_PARTY in baseline:
        raise RuntimeError("CI_EXACT_CLIENT_ALREADY_EXISTS")
    baseline_docs = details(token, baseline)
    policies = read(token, "/client-policies/policies")
    profiles = read(token, "/client-policies/profiles")
    scope_names = {s.get("name") for s in read(token, "/client-scopes")}
    if not REQUIRED_SCOPES.issubset(scope_names):
        raise RuntimeError("CI_REQUIRED_SCOPES_MISSING")

    created = []
    run_id = secrets.token_hex(8)
    original_exception = None
    try:
        # Thirteen synthetic *disabled* fixtures, not actual owner clients.
        legacy = ["ci-legacy-preserve-" + run_id + "-" + str(i)
                  for i in range(LEGACY_COUNT)]
        for client_id in legacy:
            created_one(token, client_id, fixture(client_id), created)
        with_legacy = clients(token)
        legacy_docs = details(token, with_legacy)
        if len(with_legacy) != len(baseline) + LEGACY_COUNT:
            raise RuntimeError("CI_LEGACY_FIXTURE_COUNT_DRIFT")

        proposals = client_proposals()
        validate_proposals(proposals)
        for proposal in proposals:
            created_one(token, proposal["clientId"], proposal, created)
        with_exact = clients(token)
        if len(with_exact) != len(with_legacy) + 2:
            raise RuntimeError("CI_EXACT_CLIENT_COUNT_DRIFT")
        if details(token, {x: with_exact[x] for x in with_legacy}) != legacy_docs:
            raise RuntimeError("CI_EXISTING_CLIENT_CONFIG_MUTATED")
        if (read(token, "/client-policies/policies") != policies
                or read(token, "/client-policies/profiles") != profiles):
            raise RuntimeError("CI_CLIENT_POLICY_DRIFT")
        verify_two(token, with_exact)
        print("PASS CLONE-STYLE CI: 13 disabled legacy fixtures retained across two exact client creations.")
        print("PASS CLONE-STYLE CI: official client JWKS, exact redirects, PKCE, task scope and audience verified.")
    except Exception as exc:
        original_exception = exc
    finally:
        cleanup_error = False
        for client_id, key in reversed(created):
            try:
                write(token, "/clients/" + quote(key, safe=""), "DELETE")
            except Exception:
                cleanup_error = True
        if cleanup_error or clients(token) != baseline or details(token, baseline) != baseline_docs:
            raise RuntimeError("CI_EXACT_CLIENT_ROLLBACK_INCOMPLETE") from None
        if (read(token, "/client-policies/policies") != policies
                or read(token, "/client-policies/profiles") != profiles):
            raise RuntimeError("CI_EXACT_CLIENT_POLICY_ROLLBACK_DRIFT")
        print("PASS CLONE-STYLE CI: all temporary clients removed; original clients and policies unchanged.")
    if original_exception is not None:
        raise RuntimeError("CI_EXACT_CLIENT_PRESERVATION_REHEARSAL_FAILED") from None
    print("NOT A BACKUP RESTORE: 13 fixtures are synthetic; active Realm untouched.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Admin REST responses and OAuth state may contain secrets; never echo.
        print("FAIL CLONE-STYLE CI: exact client preservation unverified.")
        raise SystemExit(1) from None
