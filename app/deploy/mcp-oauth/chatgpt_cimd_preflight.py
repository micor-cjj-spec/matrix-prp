#!/usr/bin/env python3
"""Fixed-origin, read-only CIMD checks. Never registers clients or accepts tokens."""
import json
import ssl
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

ISSUER = 'https://auth-test.micor.top/realms/prp-mcp'
RESOURCE = 'https://prp-test.micor.top/api/mcp'
CLIENT = 'https://chatgpt.com/oauth/client.json'
CALLBACK = 'https://chatgpt.com/connector_platform_oauth_redirect'
JWKS = 'https://chatgpt.com/oauth/jwks.json'
DISCOVERY = ISSUER + '/.well-known/openid-configuration'
ALLOWED = frozenset((CLIENT, JWKS, DISCOVERY))


class Rejected(ValueError):
    """Static error codes only: no response, request, cookie or exception details."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Rejected('METADATA_REDIRECT_FORBIDDEN')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def fetch_json(url):
    if url not in ALLOWED:
        raise Rejected('UNAPPROVED_METADATA_URL')
    opener = build_opener(ProxyHandler({}), NoRedirect(),
                          HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(Request(url, headers={'Accept': 'application/json'}), timeout=12) as response:
            if response.status != 200 or response.headers.get_content_type() != 'application/json':
                raise Rejected('METADATA_RESPONSE_INVALID')
            raw = response.read(65537)
            if len(raw) > 65536:
                raise Rejected('METADATA_TOO_LARGE')
            value = json.loads(raw, object_pairs_hook=unique_object)
            if not isinstance(value, dict):
                raise Rejected('METADATA_OBJECT_REQUIRED')
            return value
    except Rejected:
        raise
    except Exception:
        raise Rejected('METADATA_FETCH_UNVERIFIED') from None


def methods(value):
    if not isinstance(value, list) or not value or any(not isinstance(x, str) for x in value):
        raise Rejected('AUTH_METHODS_INVALID')
    return set(value)


def assess(fetch):
    discovery = fetch(DISCOVERY)
    if discovery.get('issuer') != ISSUER or discovery.get('client_id_metadata_document_supported') is not True:
        raise Rejected('ISSUER_CIMD_NOT_ADVERTISED')
    if discovery.get('authorization_response_iss_parameter_supported') is not True:
        raise Rejected('ISSUER_IDENTIFICATION_NOT_ADVERTISED')
    if 'S256' not in methods(discovery.get('code_challenge_methods_supported')):
        raise Rejected('PKCE_S256_NOT_ADVERTISED')
    client = fetch(CLIENT)
    if client.get('client_id') != CLIENT or client.get('redirect_uris') != [CALLBACK]:
        raise Rejected('CLIENT_ID_OR_CALLBACK_DRIFT')
    if client.get('jwks_uri') != JWKS:
        raise Rejected('CLIENT_JWKS_URL_DRIFT')
    declared = client.get('token_endpoint_auth_methods_supported')
    legacy = client.get('token_endpoint_auth_method')
    if legacy is not None and not isinstance(legacy, str):
        raise Rejected('AUTH_METHODS_INVALID')
    supported = methods(declared) if declared is not None else methods([legacy])
    intersection = supported & methods(discovery.get('token_endpoint_auth_methods_supported')) & {'none', 'private_key_jwt'}
    if not intersection:
        raise Rejected('NO_COMPATIBLE_CIMD_AUTH_METHOD')
    selected = legacy if legacy in intersection else None
    # No invented preference if the real metadata does not decide one.
    if 'private_key_jwt' in intersection:
        keys = fetch(JWKS).get('keys')
        if not isinstance(keys, list) or not keys:
            raise Rejected('CLIENT_JWKS_INVALID')
        if any(not isinstance(k, dict) or any(field in k for field in ('d', 'p', 'q', 'dp', 'dq', 'qi', 'oth', 'k')) for k in keys):
            raise Rejected('CLIENT_JWKS_NOT_PUBLIC')
        if not any(k.get('kty') == 'RSA' and k.get('use', 'sig') == 'sig'
                   and k.get('alg', 'RS256') == 'RS256' and k.get('n') and k.get('e') and k.get('kid') for k in keys):
            raise Rejected('CLIENT_RS256_KEY_MISSING')
    return {'phase': 'metadata_only', 'compatible_auth_methods': sorted(intersection),
            'legacy_preferred_method': selected, 'requested_scopes': ['openid', 'offline_access', 'prp.tasks.read'],
            'realm_policy_verified': False, 'issuer_egress_verified': False,
            'real_oauth_login_verified': False, 'chatgpt_tools_verified': False,
            'ready_for_production': False, 'configuration_changed': False}


if __name__ == '__main__':
    try:
        print(json.dumps(assess(fetch_json), sort_keys=True))
    except Rejected as error:
        print(json.dumps({'phase': 'metadata_only', 'status': 'UNVERIFIED', 'reason': str(error),
                          'configuration_changed': False}))
        raise SystemExit(2)
