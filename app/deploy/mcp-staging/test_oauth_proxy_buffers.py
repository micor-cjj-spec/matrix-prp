import unittest
from prepare_env import make_config
from render_tls import render as outer
from render_internal_oauth_tls import render as inner


class OAuthBufferTests(unittest.TestCase):
    def test_both_hops_have_identical_bounded_auth_buffers(self):
        config = make_config('prp-test.micor.top', 'auth-test.micor.top', 'stage_admin')
        for text in (outer(config), inner(config)):
            for line in ('proxy_buffer_size 16k;', 'proxy_buffers 4 16k;', 'proxy_busy_buffers_size 32k;'):
                self.assertEqual(text.count(line), 1)
            auth = text.split('server_name auth-test.micor.top;')[1].split('location /')[0]
            self.assertIn('proxy_buffer_size 16k;', auth)
            self.assertIn('return 421;', text)
            self.assertNotIn('proxy_ssl_verify off', text)
            self.assertNotIn('proxy_pass http://127.0.0.1:11000', text)
        self.assertIn('ssl_reject_handshake on;', inner(config))


if __name__ == '__main__': unittest.main()
