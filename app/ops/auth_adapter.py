"""D-M05 authenticated request candidate, deliberately pinned to .invalid.

A real issuer/client/resource configuration requires separate M06 approval.
No listener, discovery registration, grant writer, or live credential is here.
"""
import base64
import http.client
import os
import re
import ssl
import stat
from pathlib import Path
from urllib.parse import quote_plus, urlencode, urlsplit

from mcp_adapter import ServerVerifiedContext
from query_contract import (ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPE, SCOPES,
    Policy, CurrentGrant, VerifiedIdentity, QueryDenied, check_grant,
    check_identity, grant_id_valid, instant, require)
from snapshot_contract import ENV, strict_json, utc

GRANT_DIR = Path("/etc/matrix-prp-ops")
GRANT_NAME = "grant.json"
GRANT_LIMIT = 2048
TOKEN_LIMIT = 8192
RESPONSE_LIMIT = 8192
# Pin endpoint to the synthetic issuer already used by the M03 contract.
INTROSPECTION_URL = ISSUER + "/protocol/openid-connect/token/introspect"
GRANT_KEYS = {"version", "grantId", "issuer", "resource", "client", "subject",
              "environment", "scope", "issuedAt", "expiresAt", "active"}

def bearer_token(header):
    require(type(header) is str and len(header) <= TOKEN_LIMIT + 7)
    match = re.fullmatch(r"Bearer ([A-Za-z0-9._~+/-]+={0,2})", header, re.ASCII | re.IGNORECASE)
    require(match is not None and len(match.group(1)) <= TOKEN_LIMIT)
    return match.group(1)

class IntrospectionClient:
    """Fixed HTTPS RFC 7662 adapter; tests replace HTTPSConnection.

    Basic auth identifies a separately provisioned confidential resource-server
    client, not the ChatGPT OAuth client. The TLS trust store is system-owned.
    Socket timeout is per operation, not a hard end-to-end deadline.
    """
    def __init__(self, client_id, client_secret):
        require(type(client_id) is str and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", client_id) is not None)
        require(type(client_secret) is str and 1 <= len(client_secret) <= 512
                and all(33 <= ord(c) <= 126 for c in client_secret))
        self._client_id = client_id
        self._client_secret = client_secret

    def __call__(self, token):
        connection = None
        try:
            require(bearer_token("Bearer " + token) == token)
            endpoint = urlsplit(INTROSPECTION_URL)
            require(endpoint.scheme == "https" and endpoint.hostname == "issuer.invalid"
                    and endpoint.port is None and endpoint.username is None
                    and endpoint.password is None and not endpoint.query and not endpoint.fragment)
            auth = quote_plus(self._client_id) + ":" + quote_plus(self._client_secret)
            encoded = base64.b64encode(auth.encode("ascii")).decode("ascii")
            body = urlencode({"token": token, "token_type_hint": "access_token"}).encode("ascii")
            connection = http.client.HTTPSConnection(endpoint.hostname, 443, timeout=2,
                context=ssl.create_default_context())
            connection.request("POST", endpoint.path, body=body, headers={
                "Authorization": "Basic " + encoded,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json", "Accept-Encoding": "identity",
                "Connection": "close",
            })
            response = connection.getresponse()
            require(response.status == 200)
            content_type = response.getheader("Content-Type", "")
            require(content_type.split(";", 1)[0].strip().lower() == "application/json")
            require(response.getheader("Content-Encoding", "identity").lower() == "identity")
            raw = response.read(RESPONSE_LIMIT + 1)
            require(type(raw) is bytes and 0 < len(raw) <= RESPONSE_LIMIT)
            return raw
        except Exception:
            raise QueryDenied("query denied") from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

def parse_grant(raw):
    """Admin-owned independent grant record; no token/credential storage."""
    value = strict_json(raw, GRANT_LIMIT)
    require(type(value) is dict and set(value) == GRANT_KEYS)
    require(type(value["version"]) is int and value["version"] == 1)
    require(grant_id_valid(value["grantId"]) and value["issuer"] == ISSUER
            and value["resource"] == RESOURCE and value["client"] == CLIENT
            and value["subject"] == SUBJECT and value["environment"] == ENV
            and value["scope"] == SCOPE and type(value["active"]) is bool)
    utc(value["issuedAt"])
    utc(value["expiresAt"])
    require(value["issuedAt"] < value["expiresAt"])
    return CurrentGrant(value["grantId"], ISSUER, RESOURCE, CLIENT, SUBJECT,
                        ENV, SCOPES, value["issuedAt"], value["expiresAt"], value["active"])

class GrantFile:
    """Read-only provider; admin must atomically replace/revoke the record.

    Default owner is root. Tests may inject a trusted fixture directory and
    owner UID. No write/create/repair API and no model-supplied path.
    """
    def __init__(self, directory=GRANT_DIR, *, reader_gid, owner_uid=0):
        self.directory = Path(directory)
        self.reader_gid = reader_gid
        self.owner_uid = owner_uid

    def current(self):
        fd = source = None
        try:
            require(self.directory.is_absolute() and type(self.owner_uid) is int
                    and type(self.reader_gid) is int and os.geteuid() != self.owner_uid)
            groups = set(os.getgroups()) | {os.getegid()}
            require(self.reader_gid in groups)
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            fd = os.open("/", flags)
            for part in self.directory.parts[1:]:
                require(part not in ("", ".", ".."))
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == self.owner_uid
                    and stat.S_IMODE(info.st_mode) == 0o755)
            source = os.open(GRANT_NAME, os.O_RDONLY | os.O_NOFOLLOW |
                os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
            info = os.fstat(source)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == self.owner_uid
                    and info.st_gid == self.reader_gid and stat.S_IMODE(info.st_mode) == 0o640
                    and info.st_nlink == 1 and 0 < info.st_size <= GRANT_LIMIT)
            with os.fdopen(source, "rb") as stream:
                source = None
                return parse_grant(stream.read(GRANT_LIMIT + 1))
        except Exception:
            raise QueryDenied("query denied") from None
        finally:
            if source is not None:
                os.close(source)
            if fd is not None:
                os.close(fd)

    def lookup(self, grant_id):
        value = self.current()
        require(value.grant_id == grant_id)
        return value

def verify_introspection(raw, grant, now):
    """Trust only bytes from the independently authenticated TLS adapter.

    No grant ID is inferred from JWT claims or model input: the current local
    grant supplies its generation. A replaced grant rejects old token iat.
    """
    try:
        p = strict_json(raw, RESPONSE_LIMIT)
        require(type(p) is dict and p.get("active") is True)
        require(p.get("iss") == ISSUER and p.get("sub") == SUBJECT
                and p.get("token_type") == "Bearer" and p.get("scope") == SCOPE
                and "scp" not in p)
        aud = p.get("aud")
        require(aud == RESOURCE or (type(aud) is list and aud == [RESOURCE]))
        require("client_id" in p or "azp" in p)
        for field in ("client_id", "azp"):
            if field in p:
                require(type(p[field]) is str and p[field] == CLIENT)
        if "nbf" in p:
            utc(p["nbf"])
            require(p["nbf"] <= now)
        require(type(grant) is CurrentGrant)
        identity = VerifiedIdentity(ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPES,
                                    grant.grant_id, p["iat"], p["exp"])
        check_identity(identity, now)
        check_grant(grant, identity, now)
        return identity
    except Exception:
        raise QueryDenied("query denied") from None

def authorize_request(header, *, policy, introspect, grants, trusted_clock, store):
    """One context per request; M03 independently rereads grant before/after snapshot."""
    try:
        require(type(policy) is Policy and policy.enabled is True)
        require(type(grants) is GrantFile and callable(introspect) and callable(trusted_clock))
        token = bearer_token(header)
        start = instant(trusted_clock)
        raw = introspect(token)
        grant = grants.current()
        now = instant(trusted_clock, start)
        identity = verify_introspection(raw, grant, now)
        return ServerVerifiedContext(policy, lambda: identity, grants.lookup, trusted_clock, store)
    except Exception:
        raise QueryDenied("query denied") from None
