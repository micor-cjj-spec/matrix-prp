import re
import unittest
from approval_routes_pending import (
    READONLY_LINK_EXACT, READONLY_LINK_REGEX, V2_APPROVAL_REGEX,
    render_readonly_link_routes, render_v2_write_routes,
)


class V2WriteRoutesTests(unittest.TestCase):
    def test_page_and_api_are_inseparable_in_explicit_write_renderer(self):
        text = render_v2_write_routes()
        for pattern, methods in V2_APPROVAL_REGEX.items():
            self.assertIn('location ~ "' + pattern + '" {\n    limit_except ' + methods, text)
        count = len(READONLY_LINK_EXACT) + len(READONLY_LINK_REGEX) + 3
        self.assertEqual(text.count('proxy_pass http://127.0.0.1:18082;'), count)
        self.assertEqual(text.count('access_log off;'), count)
        self.assertEqual(text.count('proxy_cache off;'), count)
        self.assertEqual(text.count('if ($request_uri !~ '), count)
        self.assertEqual(text.count('if ($request_method !~ '), count)
        self.assertNotIn('127.0.0.1:18443', text)
        self.assertNotIn('127.0.0.1:18081', text)
        self.assertNotIn('location /api/', text)

    def test_read_only_renderer_never_exposes_approval(self):
        self.assertNotIn('/api/mcp/approval', render_readonly_link_routes())
        self.assertNotIn('/prp/me/mcp-approve', render_readonly_link_routes())

    def test_only_uuid_and_two_mutation_verbs_match(self):
        draft = '00000000-0000-4000-8000-00000000000a'
        api = '/api/mcp/approval/drafts/' + draft
        patterns = list(V2_APPROVAL_REGEX)
        for path, expected in [(api, 'GET'), (api+'/approve', 'POST'), (api+'/reject', 'POST')]:
            matches = [verbs for pattern, verbs in V2_APPROVAL_REGEX.items() if re.fullmatch(pattern, path)]
            self.assertEqual(matches, [expected])
        self.assertTrue(any(re.fullmatch(p, api.upper().replace('/API/MCP/APPROVAL/DRAFTS/', '/api/mcp/approval/drafts/')) for p in patterns))
        for bad in [api+'/delete', api+'/approve/extra', api+'/', api.replace(draft, 'not-a-uuid'), api.replace('-', '%2d')]:
            self.assertFalse(any(re.fullmatch(p, bad) for p in patterns))

    def test_cannot_redirect_writes_to_old_or_external_stack(self):
        for port in (18081, 18443, True, None, '18082', 443, 65536):
            with self.assertRaises(ValueError): render_v2_write_routes(port)


if __name__ == '__main__': unittest.main()
