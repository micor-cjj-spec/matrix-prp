import unittest
import ci_pkce_browser as flow
from urllib.parse import urlencode


class CallbackBoundaryTests(unittest.TestCase):
    def test_exact_callback_and_state_required(self):
        query=urlencode({'state':'expected','code':'example','iss':flow.ISSUER})
        self.assertEqual(flow.parse_callback(flow.CALLBACK+'?'+query, 'expected'), 'example')
        for url in [flow.CALLBACK+'/other?state=expected&code=example',
                    flow.CALLBACK+'?state=expected&code=example',
                    flow.CALLBACK+'?state=attacker&code=example',
                    flow.CALLBACK+'?state=expected&code=a&code=b',
                    flow.CALLBACK+'?state=expected&code=a&iss=https://wrong.example']:
            with self.assertRaises(RuntimeError):
                flow.parse_callback(url, 'expected')
