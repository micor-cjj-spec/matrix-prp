import json
import unittest
from unittest.mock import patch
import chatgpt_cimd_preflight as m


class CimdPreflightTests(unittest.TestCase):
    def fixture(self):
        return {m.DISCOVERY: {'issuer': m.ISSUER, 'client_id_metadata_document_supported': True,
                 'authorization_response_iss_parameter_supported': True,
                 'code_challenge_methods_supported': ['S256'],
                 'token_endpoint_auth_methods_supported': ['none', 'private_key_jwt']},
                m.CLIENT: {'client_id': m.CLIENT, 'redirect_uris': [m.CALLBACK], 'jwks_uri': m.JWKS,
                 'token_endpoint_auth_method': 'private_key_jwt',
                 'token_endpoint_auth_methods_supported': ['none', 'private_key_jwt']},
                m.JWKS: {'keys': [{'kty': 'RSA', 'kid': 'fixture', 'n': 'fixture', 'e': 'AQAB'}]}}

    def test_current_transition_prefers_real_legacy_method_without_claiming_login(self):
        r = m.assess(self.fixture().__getitem__)
        self.assertEqual(r['legacy_preferred_method'], 'private_key_jwt')
        self.assertFalse(r['real_oauth_login_verified'])
        self.assertFalse(r['realm_policy_verified'])
        self.assertFalse(r['ready_for_production'])

    def test_public_client_is_supported_when_actual_method_intersection_requires_it(self):
        f = self.fixture(); f[m.DISCOVERY]['token_endpoint_auth_methods_supported'] = ['none']
        del f[m.JWKS]
        r = m.assess(f.__getitem__)
        self.assertEqual(r['compatible_auth_methods'], ['none'])
        self.assertIsNone(r['legacy_preferred_method'])

    def test_wrong_client_callback_or_jwks_does_not_trigger_arbitrary_fetch(self):
        for key, value in [('client_id', 'https://evil.example/client.json'),
                           ('redirect_uris', [m.CALLBACK, 'https://evil.example/cb']),
                           ('jwks_uri', 'http://127.0.0.1/private')]:
            f = self.fixture(); f[m.CLIENT][key] = value
            with self.subTest(key=key), self.assertRaises(m.Rejected):
                m.assess(f.__getitem__)

    def test_discovery_support_is_not_truthy_or_issuer_normalized(self):
        for key, value in [('issuer', m.ISSUER + '/'), ('client_id_metadata_document_supported', 'true'),
                           ('authorization_response_iss_parameter_supported', False),
                           ('code_challenge_methods_supported', ['plain'])]:
            f = self.fixture(); f[m.DISCOVERY][key] = value
            with self.subTest(key=key), self.assertRaises(m.Rejected):
                m.assess(f.__getitem__)

    def test_secret_authentication_cannot_silently_replace_cimd_methods(self):
        f = self.fixture(); f[m.DISCOVERY]['token_endpoint_auth_methods_supported'] = ['client_secret_basic']
        with self.assertRaises(m.Rejected): m.assess(f.__getitem__)

    def test_malformed_discovery_or_preference_fails_closed(self):
        f = self.fixture(); f[m.DISCOVERY]['code_challenge_methods_supported'] = 'S256'
        with self.assertRaises(m.Rejected): m.assess(f.__getitem__)
        f = self.fixture(); f[m.CLIENT]['token_endpoint_auth_method'] = {'not': 'a method'}
        with self.assertRaises(m.Rejected): m.assess(f.__getitem__)

    def test_private_or_non_signing_jwks_rejected(self):
        for change in [{'d': 'never-log-this'}, {'use': 'enc'}, {'alg': 'HS256'}]:
            f = self.fixture(); f[m.JWKS]['keys'][0].update(change)
            with self.subTest(change=change), self.assertRaises(m.Rejected) as e:
                m.assess(f.__getitem__)
            self.assertNotIn('never-log-this', str(e.exception))

    def test_no_unapproved_url_or_redirect_fetch(self):
        with patch.object(m, 'build_opener') as opener:
            with self.assertRaises(m.Rejected): m.fetch_json('https://chatgpt.com.evil.example/oauth/client.json')
            opener.assert_not_called()
        with self.assertRaises(m.Rejected): m.NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_duplicate_json_keys_fail_closed(self):
        with self.assertRaises(m.Rejected): json.loads('{"client_id":"a","client_id":"b"}', object_pairs_hook=m.unique_object)


if __name__ == '__main__':
    unittest.main()
