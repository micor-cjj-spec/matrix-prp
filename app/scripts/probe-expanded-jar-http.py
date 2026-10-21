#!/usr/bin/env python3
"""ENG-03E localhost-only HTTP probe for real packaged PRP JARs.

Never log bearer tokens, credentials or response bodies. Refuse arbitrary
targets, production domains and non-synthetic CI use.
"""
import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ALLOWED_PORTS = {4181: "baseline", 4182: "candidate"}


def request(port, method, endpoint, *, body=None, token=None):
    if port not in ALLOWED_PORTS or not endpoint.startswith("/api/"):
        raise ValueError("Only local synthetic API traffic is permitted")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{endpoint}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            code = response.status
            raw = response.read(131072)
    except urllib.error.HTTPError as error:
        code = error.code
        raw = error.read(131072)
    if len(raw) >= 131072:
        raise AssertionError("Oversized API response")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        payload = {}
    return code, payload


def success(port, method, path, *, body=None, token=None):
    status, payload = request(port, method, path, body=body, token=token)
    if status != 200 or payload.get("code") != "SUCCESS":
        raise AssertionError(f"Unexpected HTTP/API status at {path}: {status}")
    return payload.get("data")


def probe(port, jar, source_commit, output):
    if (os.environ.get("CI") != "true"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("PRP_EXPANDED_APP_TEST") != "synthetic-only"):
        raise RuntimeError("Synthetic CI-only probe")
    if port not in ALLOWED_PORTS:
        raise ValueError("Unexpected port")
    if not re.fullmatch("[0-9a-f]{40}", source_commit):
        raise ValueError("Invalid source commit identity")
    artifact = Path(jar).resolve(strict=True)
    if artifact.suffix != ".jar" or "target" not in artifact.parts:
        raise ValueError("Only local compiled JAR target is allowed")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    # The probe does not claim this JAR came from a specific production release.
    deadline = time.monotonic() + 85
    while True:
        try:
            health = success(port, "GET", "/api/health")
            if health.get("status") != "UP":
                raise AssertionError("Health not UP")
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if time.monotonic() >= deadline:
                raise RuntimeError("JAR failed to respond to localhost health")
            time.sleep(2)

    unauth, _ = request(port, "GET", "/api/finance/transactions")
    if unauth != 401:
        raise AssertionError("Unauthenticated finance endpoint was not denied")
    login = success(port, "POST", "/api/auth/login", body={
        "username": "video_admin",
        "password": "video-test-admin-password-2026",
    })
    if not isinstance(login, dict) or not isinstance(login.get("token"), str):
        raise AssertionError("Missing synthetic session token")
    admin_token = login["token"]
    user = success(port, "GET", "/api/users/me", token=admin_token)
    if not user or user.get("username") != "video_admin":
        raise AssertionError("Authenticated identity mismatch")

    marker = "ci-jar-" + uuid.uuid4().hex[:18]
    created = success(port, "POST", "/api/finance/transactions", token=admin_token, body={
        "type": "expense", "amount": 7.35, "category": "meal",
        "account": "http-compat-fixture", "merchant": "synthetic",
        "note": marker, "transactionDate": "2026-10-21",
    })
    if created.get("note") != marker:
        raise AssertionError("Finance transaction write/read mismatch")
    finance_id = created.get("id")
    if not isinstance(finance_id, int) or finance_id <= 0:
        raise AssertionError("Missing transaction ID")
    listed = success(port, "GET", "/api/finance/transactions", token=admin_token)
    if not isinstance(listed, list) or not any(row.get("id") == finance_id for row in listed):
        raise AssertionError("Created private row not returned to owner")

    invitation = success(port, "POST", "/api/auth/invitations", token=admin_token, body={})
    if not invitation or not invitation.get("code"):
        raise AssertionError("Synthetic invitation was not issued")
    second = success(port, "POST", "/api/auth/register", body={
        "username": "fixture_" + uuid.uuid4().hex[:10],
        "password": "synthetic-second-password-2026",
        "displayName": "Synthetic Second",
        "invitationCode": invitation["code"],
    })
    second_token = second.get("token")
    if not second_token:
        raise AssertionError("Second synthetic user registration failed")
    other_rows = success(port, "GET", "/api/finance/transactions", token=second_token)
    if not isinstance(other_rows, list) or any(row.get("id") == finance_id for row in other_rows):
        raise AssertionError("Finance row disclosed to another user")

    # Evidence contains hashes and coarse checks only; no tokens/rows/secrets.
    receipt = {
        "schema_version": 1,
        "classification": "CI_SYNTHETIC_JAR_HTTP_PROBE",
        "production_deployment_attested": False,
        "production_authorized": False,
        "label": ALLOWED_PORTS[port],
        "source_commit": source_commit,
        "jar_sha256": digest,
        "checks": {
            "localhost_health": "PASS",
            "unauthorized_rejected": "PASS",
            "login_and_user_identity": "PASS",
            "finance_write_read": "PASS",
            "tenant_isolation": "PASS",
        },
    }
    output_path = Path(output)
    if output_path.name != f"prp-{ALLOWED_PORTS[port]}-jar-http.json":
        raise ValueError("Nonstandard receipt filename")
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(f"ENG-03E {ALLOWED_PORTS[port]} JAR HTTP PASS: synthetic health/auth/finance/isolation")
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--jar", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    probe(args.port, args.jar, args.commit, args.output)


if __name__ == "__main__":
    main()
