#!/usr/bin/env python3
"""Review-only exact ChatGPT client inline-JWKS candidate; no network or writes."""
import json
import base64
import binascii
from copy import deepcopy
from review_exact_client_registrations import CHATGPT, CHATGPT_JWKS, client_proposals

PRIVATE_FIELDS = {"d", "p", "q", "dp", "dq", "qi", "oth"}

def review_inline_candidate(jwks):
    if not isinstance(jwks, dict) or set(jwks) != {"keys"}:
        raise ValueError("JWKS_SHAPE_INVALID")
    keys = jwks["keys"]
    if not isinstance(keys, list) or not keys or len(keys) > 16:
        raise ValueError("JWKS_KEY_COUNT_INVALID")
    seen = set()
    material_seen = set()
    for key in keys:
        if not isinstance(key, dict) or PRIVATE_FIELDS.intersection(key):
            raise ValueError("JWKS_PRIVATE_OR_INVALID_KEY")
        if key.get("kty") != "RSA" or key.get("alg") != "RS256" or key.get("use") != "sig":
            raise ValueError("JWKS_KEY_TYPE_INVALID")
        kid = key.get("kid")
        if not isinstance(kid, str) or not kid or kid in seen:
            raise ValueError("JWKS_KID_INVALID_OR_DUPLICATE")
        seen.add(kid)
        decoded = {}
        for name in ("n", "e"):
            value = key.get(name)
            if not isinstance(value, str) or not value or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in value):
                raise ValueError("JWKS_RSA_PARAMETER_INVALID")
            try:
                raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
            except (ValueError, binascii.Error):
                raise ValueError("JWKS_RSA_PARAMETER_INVALID") from None
            if not raw or raw[0] == 0 or base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != value:
                raise ValueError("JWKS_RSA_PARAMETER_NOT_CANONICAL")
            decoded[name] = int.from_bytes(raw, "big")
        if decoded["n"].bit_length() < 2048 or decoded["n"].bit_length() > 8192:
            raise ValueError("JWKS_RSA_MODULUS_SIZE_INVALID")
        if decoded["e"] < 3 or decoded["e"] % 2 == 0 or decoded["e"] > 2**32 - 1:
            raise ValueError("JWKS_RSA_EXPONENT_INVALID")
        material = (decoded["n"], decoded["e"])
        if material in material_seen:
            raise ValueError("JWKS_DUPLICATE_KEY_MATERIAL")
        material_seen.add(material)
    baseline = next(c for c in client_proposals() if c["clientId"] == CHATGPT)
    candidate = deepcopy(baseline)
    attrs = candidate["attributes"]
    if attrs.pop("jwks.url", None) != CHATGPT_JWKS or attrs.get("use.jwks.url") != "true":
        raise ValueError("BASELINE_JWKS_URL_CHANGED")
    attrs.update({"use.jwks.url": "false", "use.jwks.string": "true",
                  "jwks.string": json.dumps(jwks, separators=(",", ":"), sort_keys=True)})
    return {"status": "REVIEW_ONLY_B2_NO_GO", "deployable": False,
            "client_count": 1, "client_id": CHATGPT,
            "candidate": candidate}

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("USAGE: review_chatgpt_inline_jwks.py <LOCAL_PUBLIC_JWKS_JSON>")
    with open(sys.argv[1], encoding="utf-8") as stream:
        source = json.load(stream)
    reviewed = review_inline_candidate(source)
    # Do not print key material to logs.
    print(json.dumps({k: v for k, v in reviewed.items() if k != "candidate"}, sort_keys=True))
