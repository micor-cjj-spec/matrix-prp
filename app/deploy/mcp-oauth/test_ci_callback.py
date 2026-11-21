import unittest
from unittest.mock import patch
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


    def test_disposable_https_opener_never_inherits_runner_proxy(self):
        # Only the ephemeral CA is trusted; system HTTP(S)_PROXY is ignored.
        with patch.object(flow.ssl, "create_default_context") as trust:
            opener = flow.disposable_https_opener("/tmp/ci-disposable-ca.pem")
        trust.assert_called_once_with(cafile="/tmp/ci-disposable-ca.pem")
        # urllib skips registering a ProxyHandler({}) because it supplies no
        # proxy_open methods; absence of any proxy handler is the safe outcome.
        self.assertFalse(any(isinstance(h, flow.ProxyHandler) for h in opener.handlers))
        self.assertTrue(any(isinstance(h, flow.SafeRedirect) for h in opener.handlers))
        self.assertTrue(any(isinstance(h, flow.HTTPCookieProcessor) for h in opener.handlers))
