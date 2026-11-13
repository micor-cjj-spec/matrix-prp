#!/usr/bin/env python3
"""Operator-only, local-browser OAuth PKCE + PRP MCP smoke test.

Never prints access tokens, passwords, authorization codes, PKCE verifiers, or
user task data. Runs only when explicitly invoked by an operator.
"""
import argparse
import base64
from getpass import getpass
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import sys
import urllib.error
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from check_metadata import public_get_json, validate, https_url
from build_realm import staging_redirect_uri
from oauth_token_check import check_token


def pkce_pair():
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorization_url(endpoint, client_id, redirect_uri, resource, challenge, state, nonce):
    https_url(endpoint, "authorization endpoint")
    return endpoint + "?" + urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid prp.tasks.read",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": resource,
        "state": state,
        "nonce": nonce,
    })


def validate_callback(query, state, issuer):
    params = parse_qs(query, keep_blank_values=True)
    if len(params.get("state", [])) != 1 or not secrets.compare_digest(params["state"][0], state):
        raise ValueError("OAuth state does not match the pending browser authorization")
    if "error" in params:
        raise ValueError("OAuth authorization was rejected")
    if "iss" in params and params["iss"] != [issuer]:
        raise ValueError("OAuth authorization response issuer mismatch")
    if len(params.get("code", [])) != 1 or not params["code"][0]:
        raise ValueError("OAuth callback contains no unique authorization code")
    return params["code"][0]


def callback_listener(uri, timeout_seconds=180):
    parsed = urlsplit(staging_redirect_uri(uri))
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1") or not parsed.port:
        raise ValueError("Local browser smoke requires explicit http://127.0.0.1:<port>/callback")
    captured = []
    callback_path = parsed.path
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # Never log OAuth authorization codes from request paths.
        def do_GET(self):
            request = urlsplit(self.path)
            if request.path != callback_path:
                self.send_error(404)
                return
            captured.append(request.query)
            data = b"PRP OAuth callback received. You may close this tab and return to your terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = HTTPServer(("127.0.0.1", parsed.port), Callback)
    server.timeout = timeout_seconds
    return server, captured


def exchange(endpoint, client_id, callback, code, verifier, resource):
    https_url(endpoint, "token endpoint")
    body = urlencode({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": callback,
        "code_verifier": verifier,
        "resource": resource,
    }).encode()
    request = Request(endpoint, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(100001)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"OAuth token exchange failed (HTTP {error.code}); details suppressed") from None
    if len(raw) > 100000:
        raise ValueError("Token response exceeds safe size")
    parsed = json.loads(raw)
    token = parsed.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("OAuth token endpoint returned no access token")
    return token


def mcp_json(endpoint, token, method, params=None, identifier=1):
    body = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if params is not None:
        body["params"] = params
    return post_json(endpoint, token, body, accept="application/json, text/event-stream")


def post_json(endpoint, token, body, accept="application/json"):
    request = Request(endpoint, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": accept,
        "MCP-Protocol-Version": "2025-06-18",
    })
    try:
        with urlopen(request, timeout=25) as response:
            payload = response.read(1000001)
            media = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"PRP endpoint returned HTTP {error.code}; response body suppressed") from None
    if len(payload) > 1000000:
        raise RuntimeError("PRP response exceeds safety limit")
    content = payload.decode("utf-8")
    if "text/event-stream" in media:
        events = [line[5:].strip() for line in content.splitlines() if line.startswith("data:")]
        if not events:
            raise RuntimeError("MCP SSE response contained no data events")
        return json.loads(events[-1])
    return json.loads(content)


def smoke(resource, token, linking_code=None):
    # Linking is a bootstrap-only bearer route, not an MCP tool.
    if linking_code is not None:
        result = post_json(resource.rstrip("/") + "/link", token, {"ticket": linking_code})
        if not result.get("data", {}).get("subject"):
            raise RuntimeError("PRP OAuth identity pairing did not succeed")
        print("PRP identity link: accepted")

    initialize = mcp_json(resource, token, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "prp-oauth-smoke", "version": "1.0"},
    })
    if initialize.get("error") or not initialize.get("result", {}).get("serverInfo"):
        raise RuntimeError("MCP initialize failed")
    print("MCP initialize: accepted")

    listing = mcp_json(resource, token, "tools/list", {}, 2)
    names = [tool.get("name") for tool in listing.get("result", {}).get("tools", [])]
    if "prp_tasks_list" not in names:
        raise RuntimeError("PRP's authenticated task tool is missing from tools/list")
    print(f"MCP tools/list: accepted ({len(names)} tool definitions; names only)")

    read = mcp_json(resource, token, "tools/call",
                    {"name": "prp_tasks_list", "arguments": {}}, 3)
    if read.get("error") or read.get("result", {}).get("isError"):
        raise RuntimeError("Read-only prp_tasks_list rejected the authorized request")
    print("MCP tools/call prp_tasks_list: accepted (personal task contents hidden)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Manual OAuth PKCE + PRP MCP client smoke")
    parser.add_argument("--issuer", required=True, help="Exact HTTPS Keycloak realm issuer")
    parser.add_argument("--resource", required=True, help="Exact HTTPS PRP MCP URI")
    parser.add_argument("--client-id", required=True, help="Pre-registered test OAuth client ID")
    parser.add_argument("--redirect-uri", default="http://127.0.0.1:8765/callback")
    parser.add_argument("--already-linked", action="store_true",
                        help="Skip the PRP OAuth account-link bootstrap step")
    args = parser.parse_args()

    issuer = https_url(args.issuer, "OAuth issuer")
    resource = https_url(args.resource, "MCP resource")
    staging_redirect_uri(args.redirect_uri)
    result = validate(issuer, resource, public_get_json)
    # Keep the issuer byte-exact for JWT iss validation, but never produce
    # a double slash in the discovery request when issuer ends with '/'.
    metadata = public_get_json(issuer.rstrip("/") + "/.well-known/openid-configuration")
    verifier, challenge = pkce_pair()
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    url = authorization_url(metadata["authorization_endpoint"], args.client_id,
                            args.redirect_uri, resource, challenge, state, nonce)
    server, callback = callback_listener(args.redirect_uri)
    try:
        print("Preflight passed: Authorization Code + PKCE S256 + public JWKS.")
        print("Open this URL in a browser ON THIS MACHINE and authorize read-only tasks access:")
        print(url)  # Contains only public client ID and a one-time challenge/state/nonce.
        server.handle_request()
    finally:
        server.server_close()
    if not callback:
        raise RuntimeError("OAuth redirect timed out; no token obtained")
    code = validate_callback(callback[0], state, issuer)
    token = exchange(metadata["token_endpoint"], args.client_id,
                     args.redirect_uri, code, verifier, resource)
    # Signature-verify the REAL bearer and its exact audience before ever
    # presenting it to the account-link or MCP API; no claim content printed.
    result = check_token(
        token, public_get_json(metadata["jwks_uri"]),
        issuer=issuer, resource=resource, client_id=args.client_id,
        required_scope="prp.tasks.read",
    )
    print("OAuth token exchange: accepted; RS256/JWKS + issuer + exact MCP aud + client + task scope verified")
    if result["additional_audiences_present"]:
        print("OAuth review notice: token has additional signed audiences; inspect provider policy before production.")
    pairing_code = None
    if not args.already_linked:
        pairing_code = getpass("Paste one-time code from your own PRP MCP account-link page (hidden): ").strip()
        if not pairing_code:
            raise ValueError("Link code is required")
    smoke(resource, token, pairing_code)
    print("PASS: verified real external OAuth authorization and authenticated read-only PRP MCP round-trip.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"OAuth/MCP smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
