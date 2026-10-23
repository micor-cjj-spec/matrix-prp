import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit, urlencode
import ci_pkce_browser as flow


class ExistingSessionTests(unittest.TestCase):
    def exercise(self, direct=False, bad_issuer=False):
        calls=[]
        state=None
        def request(opener,url,**kwargs):
            nonlocal state
            calls.append(kwargs.get('data',{}))
            if state is None:
                state=parse_qs(urlsplit(url).query)['state'][0]
                if not direct:
                    return 200,{},'<form id="kc-consent" action="/realms/prp-mcp/login-actions/consent"><input name="accept" value="Yes"></form>'
            callback=flow.CALLBACK+'?'+urlencode({'state':state,'code':'synthetic-code',
                'iss':'https://wrong.example/realms/prp-mcp' if bad_issuer else flow.ISSUER})
            raise flow.CallbackReceived(callback)
        with patch.object(flow,'request',side_effect=request):
            result=flow.code_pkce(object(),'synthetic-user','PASSWORD-CANARY')
        self.assertEqual(result[0],'synthetic-code')
        self.assertTrue(all('password' not in data for data in calls))
    def test_existing_session_can_go_directly_to_consent(self):self.exercise()
    def test_existing_consent_can_redirect_immediately(self):self.exercise(direct=True)
    def test_existing_session_still_requires_correct_issuer(self):
        with self.assertRaisesRegex(RuntimeError,'issuer mismatch'):self.exercise(direct=True,bad_issuer=True)

if __name__=='__main__':unittest.main()
