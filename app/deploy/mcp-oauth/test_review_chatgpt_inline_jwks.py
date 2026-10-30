#!/usr/bin/env python3
"""Offline, no-network tests for the exact-client JWKS review helper."""
import base64
import copy
import unittest
from cryptography.hazmat.primitives.asymmetric import rsa
from review_chatgpt_inline_jwks import review_inline_candidate

def b64(value):
    return base64.urlsafe_b64encode(value.to_bytes((value.bit_length()+7)//8, "big")).rstrip(b"=").decode()

class InlineJwksReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pub = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_numbers()
        cls.key = {"kty":"RSA","use":"sig","alg":"RS256","kid":"test-key",
                   "n":b64(pub.n),"e":b64(pub.e)}

    def test_valid_review_only(self):
        result = review_inline_candidate({"keys":[self.key]})
        self.assertFalse(result["deployable"])
        self.assertEqual(result["client_count"],1)
        self.assertEqual(result["candidate"]["attributes"]["use.jwks.string"],"true")
        self.assertEqual(result["candidate"]["attributes"]["use.jwks.url"],"false")
        self.assertNotIn("jwks.url",result["candidate"]["attributes"])

    def test_reject_invalid(self):
        mutations = [
            {"keys":[]}, {"keys":[self.key,self.key]},
            {"keys":[dict(self.key,kid="different"),self.key]},
            {"keys":[dict(self.key,d="private")]},
            {"keys":[dict(self.key,alg="HS256")]},
            {"keys":[dict(self.key,kid="")]},
            {"keys":[dict(self.key,n="!!!")]},
            {"keys":[dict(self.key,n="AQ")]},
            {"keys":[dict(self.key,e="Ag")]},
            {"keys":[dict(self.key,e="AQ")]},
            {"keys":[dict(self.key,n="AA"+self.key["n"])]},
            {"keys":[dict(self.key,e="AAEAAQ")]},
            {"keys":[dict(self.key,n=self.key["n"]+"=")]},
            {"keys":[dict(self.key,kty="EC")]},
            {"keys":[dict(self.key,use="enc")]},
        ]
        for value in mutations:
            with self.subTest(value=str(value)[:90]):
                with self.assertRaises(ValueError):
                    review_inline_candidate(value)

if __name__ == "__main__":
    unittest.main()
