"""Production health Realm CANDIDATE. Exact pre-registration, NOT dynamic CIMD.

Only emits first-import JSON; never calls a live admin API or creates users/keys.
"""
import argparse
import json
from pathlib import Path
from contract import *


def build():
    basic = {'name': 'basic', 'protocol': 'openid-connect', 'attributes': {
        'include.in.token.scope': 'false', 'display.on.consent.screen': 'false'},
        'protocolMappers': [{'name': 'Subject', 'protocol': 'openid-connect',
            'protocolMapper': 'oidc-sub-mapper', 'config': {'access.token.claim': 'true',
            'introspection.token.claim': 'true', 'lightweight.claim': 'false'}}]}
    health = [{'name': s, 'protocol': 'openid-connect', 'attributes': {
        'include.in.token.scope': 'true', 'display.on.consent.screen': 'true', 'consent.screen.text': s}}
        for s in SCOPES]
    common = {'protocol': 'openid-connect', 'enabled': True, 'standardFlowEnabled': True,
        'implicitFlowEnabled': False, 'directAccessGrantsEnabled': False,
        'serviceAccountsEnabled': False, 'fullScopeAllowed': False,
        'defaultClientScopes': ['basic'], 'webOrigins': []}
    client = dict(common, clientId=CLIENT, publicClient=False, clientAuthenticatorType='client-jwt',
        consentRequired=True, redirectUris=[REDIRECT], optionalClientScopes=list(SCOPES),
        attributes={'pkce.code.challenge.method': 'S256', 'use.jwks.url': 'true',
            'jwks.url': JWKS, 'token.endpoint.auth.signing.alg': 'RS256',
            'use.refresh.tokens': 'true', 'client.session.idle.timeout': '1800',
            'client.session.max.lifespan': '28800'},
        protocolMappers=[{'name': 'Exact health resource', 'protocol': 'openid-connect',
            'protocolMapper': 'oidc-audience-mapper', 'config': {
                'included.custom.audience': RESOURCE, 'id.token.claim': 'false', 'access.token.claim': 'true'}}])
    first = dict(common, clientId=FIRST_PARTY, publicClient=True, consentRequired=False,
        redirectUris=[FIRST_REDIRECT], optionalClientScopes=[],
        attributes={'pkce.code.challenge.method': 'S256', 'use.refresh.tokens': 'false'})
    resource = {'clientId': 'prp-production-health-resource', 'protocol': 'openid-connect',
        'enabled': True, 'bearerOnly': True, 'publicClient': False,
        'standardFlowEnabled': False, 'directAccessGrantsEnabled': False,
        'serviceAccountsEnabled': False, 'attributes': {'resource_url': RESOURCE}}
    disabled = [{'clientId': c, 'protocol': 'openid-connect', 'enabled': False}
        for c in ('account', 'account-console', 'admin-cli', 'broker', 'realm-management', 'security-admin-console')]
    return {'realm': REALM, 'enabled': True, 'sslRequired': 'all',
        'registrationAllowed': False, 'resetPasswordAllowed': False,
        'loginWithEmailAllowed': False, 'duplicateEmailsAllowed': False,
        'bruteForceProtected': True, 'permanentLockout': False, 'failureFactor': 5,
        'accessTokenLifespan': 300, 'ssoSessionIdleTimeout': 1800, 'ssoSessionMaxLifespan': 28800,
        'revokeRefreshToken': True, 'refreshTokenMaxReuse': 0,
        'defaultDefaultClientScopes': [], 'defaultOptionalClientScopes': [],
        'clientScopes': [basic] + health, 'clients': [resource, client, first] + disabled,
        'clientProfiles': {'profiles': [{'name': 'prp-health-exact', 'executors': [
            {'executor': 'prp-production-health-policy', 'configuration': {}}]}]},
        'clientPolicies': {'policies': [{'name': 'prp-health-exact', 'enabled': True,
            'conditions': [{'condition': 'prp-production-health-client', 'configuration': {}}],
            'profiles': ['prp-health-exact']}]} }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(build(), f, indent=2)
    print('HEALTH_REALM_CANDIDATE_CREATED_NO_LIVE_CHANGES')
