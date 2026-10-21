"""Offline RSA/JWKS verifier for STAGING OAuth token interoperability tests.

This is a test diagnostic, NOT a replacement for PRP's Nimbus JWT verifier.
Never prints, saves or logs an access token or decoded personal claims.
"""
import base64
import hashlib
import hmac
import json
import time


_DIGEST_INFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Missing JWT/JWK field")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def check_token(token, jwks, *, issuer, resource, client_id, required_scope="prp.tasks.read",
                clock=None):
    """Cryptographically verify RS256 and the exact signed OAuth claims.

    Test-only use. Fails closed on malformed tokens, untrusted key IDs,
    wrong issuer/audience, client ID disagreement, timestamps and scopes.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3 or any(not p for p in parts):
            raise ValueError("Malformed compact access token")
        header = json.loads(_b64url(parts[0]))
        claims = json.loads(_b64url(parts[1]))
        if not isinstance(header, dict) or not isinstance(claims, dict):
            raise ValueError("Malformed JWT claims")
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise ValueError("Expected trusted RS256 access token")
        keys = jwks.get("keys", [])
        if not isinstance(keys, list):
            raise ValueError("Malformed OAuth JWKS")
        matches = [k for k in keys if isinstance(k, dict)
                   and k.get("kid") == header["kid"] and k.get("kty") == "RSA"
                   and k.get("use", "sig") == "sig"
                   and k.get("alg", "RS256") == "RS256"]
        if len(matches) != 1:
            raise ValueError("Unknown or ambiguous JWKS signing key")
        key = matches[0]
        n = int.from_bytes(_b64url(key["n"]), "big")
        e = int.from_bytes(_b64url(key["e"]), "big")
        if n.bit_length() < 2048 or e < 3 or e % 2 == 0:
            raise ValueError("Unacceptable OAuth RSA signing key")
        signature = _b64url(parts[2])
        size = (n.bit_length() + 7) // 8
        if len(signature) != size:
            raise ValueError("Invalid RSA signature length")
        digest = hashlib.sha256((parts[0] + "." + parts[1]).encode("ascii")).digest()
        padded = b"\x00\x01" + b"\xff" * (size - 3 - len(_DIGEST_INFO_SHA256) - 32)
        padded += b"\x00" + _DIGEST_INFO_SHA256 + digest
        actual = pow(int.from_bytes(signature, "big"), e, n).to_bytes(size, "big")
        if not hmac.compare_digest(padded, actual):
            raise ValueError("JWT RS256 signature failed")

        if claims.get("iss") != issuer or not claims.get("sub"):
            raise ValueError("JWT issuer or subject mismatch")
        aud = claims.get("aud")
        audiences = [aud] if isinstance(aud, str) else aud
        if not isinstance(audiences, list) or audiences != [resource]:
            raise ValueError("JWT audience must be the exact single MCP resource")
        azp, client_claim = claims.get("azp"), claims.get("client_id")
        if azp is not None and client_claim is not None and azp != client_claim:
            raise ValueError("Conflicting signed OAuth client claims")
        if (azp or client_claim) != client_id:
            raise ValueError("JWT signed OAuth client mismatch")
        now = int(time.time()) if clock is None else int(clock)
        if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] <= now:
            raise ValueError("Expired or missing OAuth access token")
        if not isinstance(claims.get("iat"), (int, float)) or claims["iat"] > now + 60:
            raise ValueError("Future or missing OAuth issue time")
        scopes = claims.get("scope", "")
        if isinstance(scopes, str):
            granted = set(scopes.split())
        elif isinstance(claims.get("scp"), list):
            granted = set(claims["scp"])
        else:
            granted = set()
        if not granted or required_scope not in granted:
            raise ValueError("Required OAuth task-read scope missing")
        return {"signature": "RS256 verified", "issuer": "verified",
                "audience": "exact MCP resource", "client": "verified",
                "scope": required_scope}
    except (KeyError, OverflowError, UnicodeError, TypeError, json.JSONDecodeError) as exc:
        # Deliberately suppress untrusted field values/token contents.
        raise ValueError("Invalid external OAuth access token or JWKS") from None
