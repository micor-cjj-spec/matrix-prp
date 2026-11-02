"""No-network regression for the optional public staging metadata preflight."""
import unittest

from ci_public_readonly_probe import (
    ISSUER, RESOURCE, resource_check, oidc_check, classify,
)


def resource(scopes=None):
    return {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": ["prp.tasks.read"] if scopes is None else scopes,
        "bearer_methods_supported": ["header"],
    }


def discovery():
    return {
        "issuer": ISSUER,
        "token_endpoint": ISSUER + "/protocol/openid-connect/token",
        "code_challenge_methods_supported": ["S256"],
    }


class PublicReadOnlyProbeTests(unittest.TestCase):
    def test_task_only_public_resource_passes(self):
        self.assertIsNone(resource_check(resource()))
        self.assertIsNone(oidc_check(discovery()))

    def test_extra_read_and_write_scopes_fail_with_static_categories(self):
        cases = [
            (["prp.tasks.read", "prp.finance.read"], "FINANCE_ADVERTISED"),
            (["prp.tasks.read", "prp.wellness.read"], "WELLNESS_ADVERTISED"),
            (["prp.tasks.read", "prp.write.create"], "WRITE_ADVERTISED"),
            (["prp.tasks.read", "unknown.other"], "UNKNOWN_SCOPE_ADVERTISED"),
            (["prp.tasks.read", "prp.finance.read", "prp.wellness.read",
              "prp.write.create"], "WRITE_ADVERTISED_FINANCE_ADVERTISED_WELLNESS_ADVERTISED"),
        ]
        for scopes, category in cases:
            with self.subTest(scopes=scopes), self.assertRaises(ValueError) as error:
                resource_check(resource(scopes))
            self.assertIn(category, str(error.exception))

    def test_missing_task_scope_and_malformed_scopes_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "TASK_READ_MISSING"):
            resource_check(resource(["prp.finance.read"]))
        with self.assertRaisesRegex(ValueError, "MALFORMED_PUBLIC_SCOPES"):
            resource_check(resource("prp.tasks.read"))
        with self.assertRaisesRegex(ValueError, "MALFORMED_PUBLIC_SCOPES"):
            resource_check(resource(["prp.tasks.read", 42]))

    def test_spoofed_resource_or_issuer_is_denied(self):
        bad = resource()
        bad["resource"] = "https://evil.invalid/api/mcp"
        with self.assertRaisesRegex(ValueError, "RESOURCE_URI_MISMATCH"):
            resource_check(bad)
        bad = resource()
        bad["authorization_servers"] = ["https://evil.invalid"]
        with self.assertRaisesRegex(ValueError, "ISSUER_LIST_MISMATCH"):
            resource_check(bad)
        bad = discovery()
        bad["issuer"] = ISSUER + "/tampered"
        with self.assertRaisesRegex(ValueError, "ISSUER_MISMATCH"):
            oidc_check(bad)

    def test_s256_and_exact_token_endpoint_are_mandatory(self):
        bad = discovery()
        bad["code_challenge_methods_supported"] = ["plain"]
        with self.assertRaisesRegex(ValueError, "S256_NOT_ADVERTISED"):
            oidc_check(bad)
        bad = discovery()
        bad["token_endpoint"] = "https://other.invalid/token"
        with self.assertRaisesRegex(ValueError, "TOKEN_ENDPOINT_MISMATCH"):
            oidc_check(bad)

    def test_unexpected_error_never_reports_public_metadata_verified(self):
        self.assertEqual(classify(RuntimeError("unexpected")), "UNKNOWN_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
