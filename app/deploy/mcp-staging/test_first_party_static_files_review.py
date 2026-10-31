"""Review-only contract: /prp/ public files must be exact GETs.

This detects source-level PWA/HTML dependencies missed when disposable
Chromium blocks service workers, without expanding to a generic /prp/**.
"""
from pathlib import Path
import re
import unittest

from approval_routes_pending import READONLY_LINK_EXACT, READONLY_LINK_REGEX


class FirstPartyStaticFilesReview(unittest.TestCase):
    def test_html_and_web_service_worker_sources_match_exact_gets(self):
        app = Path(__file__).resolve().parents[2]
        index = (app / "web/index.html").read_text(encoding="utf-8")
        main = (app / "web/src/main.ts").read_text(encoding="utf-8")
        expected = {
            "favicon.svg": 'href="%BASE_URL%favicon.svg"',
            "icon.svg": 'href="%BASE_URL%icon.svg"',
            "manifest.webmanifest": 'href="%BASE_URL%manifest.webmanifest"',
            "sw.js": "import.meta.env.BASE_URL}sw.js",
        }
        for file, marker in expected.items():
            with self.subTest(file=file):
                source = main if file == "sw.js" else index
                self.assertIn(marker, source)
                self.assertTrue((app / "web/public" / file).is_file())
                self.assertEqual(READONLY_LINK_EXACT["/prp/" + file], "GET")

    def test_static_asset_route_exactly_one_no_wildcard(self):
        self.assertEqual(len(READONLY_LINK_REGEX), 1)
        pattern, allowed = next(iter(READONLY_LINK_REGEX.items()))
        self.assertEqual(allowed, "GET")
        for valid in (
            "/prp/assets/index.3fdA.js",
            "/prp/assets/vendor.element-plus.A73d9.js",
            "/prp/assets/index-AB87.css",
        ):
            self.assertIsNotNone(re.fullmatch(pattern, valid))
        for invalid in (
            "/prp/assets/../.env",
            "/prp/assets/script..js",
            "/prp/assets/js%2Ftest.js",
            "/prp/assets/nested/file.js",
            "/prp/assets/file.js.map",
        ):
            self.assertIsNone(re.fullmatch(pattern, invalid))
        self.assertNotIn("/prp/", READONLY_LINK_EXACT)
        self.assertNotIn("/api/", READONLY_LINK_EXACT)


if __name__ == "__main__":
    unittest.main()
