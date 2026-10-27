#!/usr/bin/env python3
"""Pure no-network tests for temporary raw-URI protection hypothesis."""
import unittest
import sandbox_v2_raw_uri_overlay as mod

SAMPLE = b"""server {
 listen 443 ssl;
 location = /api/mcp {
     proxy_pass http://127.0.0.1:18082;
 }
 location = /.well-known/oauth-protected-resource/api/mcp {
     proxy_pass http://127.0.0.1:18082;
 }
 location = /public/status { return 200; }
 location / { return 404; }
}
server {
 listen 80;
 return 421;
}
"""

class RawUriOverlayTests(unittest.TestCase):
    def test_only_two_exact_v2_locations_get_raw_uri_guards(self):
        transformed, report = mod.overlay(SAMPLE)
        self.assertEqual(report["raw_uri_guards_inserted_in_disposable_vhost"], 2)
        self.assertIn(b'if ($request_uri != /api/mcp) { return 404; }', transformed)
        self.assertIn(
            b'if ($request_uri != /.well-known/oauth-protected-resource/api/mcp) { return 404; }',
            transformed)
        self.assertNotIn(b'if ($request_uri != /public/status)', transformed)
        self.assertEqual(transformed.count(b'proxy_pass http://127.0.0.1:18082;'), 2)
        self.assertFalse(report["original_candidate_modified"])
        self.assertFalse(report["release_approved"])
        self.assertEqual(SAMPLE.count(b"if ($request_uri"), 0)

    def test_inclusion_does_not_accept_nonexact_v2_route(self):
        drift = SAMPLE.replace(b"location = /api/mcp {", b"location /api/mcp {")
        with self.assertRaisesRegex(ValueError, "EXACT_TWO_V2_PROXY_LOCATIONS_REQUIRED"):
            mod.overlay(drift)

    def test_missing_or_duplicate_proxy_is_refused(self):
        one = SAMPLE.replace(
            b"proxy_pass http://127.0.0.1:18082;",
            b"return 403;", 1)
        with self.assertRaisesRegex(ValueError, "EXACT_TWO_V2_PROXY_LOCATIONS_REQUIRED"):
            mod.overlay(one)
        duplicate = SAMPLE.replace(
            b"proxy_pass http://127.0.0.1:18082;",
            b"proxy_pass http://127.0.0.1:18082;\n"
            b" proxy_pass http://127.0.0.1:18082;", 1)
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_MULTIPLE_V2_PROXIES"):
            mod.overlay(duplicate)

    def test_tricky_source_format_must_not_be_silently_rewritten(self):
        multiline = SAMPLE.replace(
            b"location = /api/mcp {",
            b"location = /api/mcp\n{")
        with self.assertRaisesRegex(ValueError, "EXACT_LOCATION_SOURCE_SCAN_MISMATCH"):
            mod.overlay(multiline)

    def test_comment_does_not_forge_location(self):
        comment = SAMPLE.replace(
            b"server {",
            b"# location = /notreal { proxy_pass http://127.0.0.1:18082; }\nserver {", 1)
        result, report = mod.overlay(comment)
        self.assertEqual(report["raw_uri_guards_inserted_in_disposable_vhost"], 2)
        self.assertNotIn(b'if ($request_uri != /notreal)', result)

    def test_unreviewed_path_rejected(self):
        weird = SAMPLE.replace(
            b"location = /api/mcp {", b"location = /api/$tenant/mcp {")
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_EXACT_LOCATION_PATH"):
            mod.overlay(weird)

if __name__ == "__main__":
    unittest.main()
