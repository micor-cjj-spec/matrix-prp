import copy
import unittest
from build_realm import build
from contract import *
from render_auth_nginx import render


class ProductionHealthCandidateTests(unittest.TestCase):
    def test_exact_client_is_confidential_native_jwt_and_no_synthetic_credential(self):
        realm=build();clients={c['clientId']:c for c in realm['clients']}
        c=clients[CLIENT]
        self.assertFalse(c['publicClient']);self.assertEqual(c['clientAuthenticatorType'],'client-jwt')
        self.assertEqual(c['attributes']['jwks.url'],JWKS)
        self.assertEqual(c['attributes']['use.jwks.url'],'true')
        self.assertNotIn('secret',c);self.assertNotIn('jwt.credential.certificate',c['attributes'])
        self.assertEqual(c['redirectUris'],[REDIRECT]);self.assertFalse(c['fullScopeAllowed'])
        for key in ('implicitFlowEnabled','directAccessGrantsEnabled','serviceAccountsEnabled'):
            self.assertFalse(c[key])
        self.assertEqual(c['attributes']['pkce.code.challenge.method'],'S256')
        self.assertEqual(set(c['optionalClientScopes']),set(SCOPES))
        self.assertEqual(c['defaultClientScopes'],['basic'])
        self.assertFalse(realm.get('users'));self.assertNotIn('components',realm)

    def test_independent_realm_and_first_party_are_not_test_identities(self):
        r=build();self.assertEqual(r['realm'],REALM);self.assertFalse(r['registrationAllowed'])
        self.assertEqual(r['defaultOptionalClientScopes'],[])
        self.assertEqual({s['name'] for s in r['clientScopes']},set(SCOPES)|{'basic'})
        first=next(c for c in r['clients'] if c['clientId']==FIRST_PARTY)
        self.assertTrue(first['publicClient']);self.assertEqual(first['redirectUris'],[FIRST_REDIRECT])
        self.assertEqual(first['optionalClientScopes'],[])
        self.assertEqual(len([c for c in r['clients'] if c['enabled']]),3)
        self.assertNotIn('any-client',str(r));self.assertNotIn('offline_access',str(r))
        self.assertNotIn('prp-test',str(r));self.assertNotIn('auth-test',str(r))

    def test_vhost_has_no_admin_master_dcr_or_open_ended_proxy(self):
        s=render()
        self.assertIn('server_name auth.micor.top;',s)
        self.assertIn('if ($ssl_server_name != auth.micor.top) { return 421; }',s)
        self.assertIn('location / { return 404; }',s)
        for value in ('/admin','/realms/master','clients-registrations','proxy_pass https','www.auth'):
            self.assertNotIn(value,s)
        self.assertEqual(s.count('proxy_pass http://127.0.0.1:18084;'),7)
        self.assertIn('proxy_set_header X-Forwarded-Proto https;',s)
        self.assertIn('access_log off;',s)
        self.assertIn('proxy_buffer_size 16k;',s)

    def test_renderer_rejects_arbitrary_port_and_injected_certificate_path(self):
        for changes in ({'port':80},{'upstream':3306},{'cert':'/etc/file;include secret;'},{'key':'/a/../b'}):
            with self.assertRaises(ValueError):render(**changes)


class EgressBoundaryTests(unittest.TestCase):
    def test_private_reserved_and_mapped_addresses_are_denied(self):
        from egress_proxy import is_public_address
        for address in ('127.0.0.1','10.0.0.1','169.254.169.254','192.168.1.1','0.0.0.0','224.0.0.1','::1','fe80::1','fc00::1','::ffff:127.0.0.1'):
            self.assertFalse(is_public_address(address), address)
        self.assertTrue(is_public_address('1.1.1.1'))

if __name__=='__main__':unittest.main()
