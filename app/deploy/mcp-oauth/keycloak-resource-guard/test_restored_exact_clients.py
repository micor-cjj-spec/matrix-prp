"""Offline execution of the PRIVATE restored Realm exact-two-client block.

No Docker/HTTP/network/credential operations. A fake 13-client Keycloak
Admin API runs the real extracted clone Python logic including its rollback.
This does NOT assert any historical or current production backup was restored.
"""
import copy
from pathlib import Path
import re
import subprocess
import textwrap
import unittest
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "verify_restored_realm_spi_clone.sh"
PROPOSAL = HERE.parent / "review_exact_client_registrations.py"
START = "    # The ORIGINAL 13-client snapshot is exercised here"
END = '    print("=== RESTORED CLONE-ONLY CLIENT POLICY SPI COMPATIBILITY ===")'


class FakeKeycloak:
    def __init__(self, fail_on_target=None):
        self.docs = {}
        self.next_id = 0
        self.fail_on_target = fail_on_target
        self.created = []
        self.removed = []
        self.profiles = {"profiles": []}
        self.policies = {"policies": []}
        self.scope_defs = [{"name": s} for s in ("basic", "offline_access", "prp.tasks.read")]
        for n in range(13):
            self.create({"clientId": "existing-client-" + str(n),
                         "publicClient": True, "standardFlowEnabled": False,
                         "name": "Existing client unchanged"})

    def create(self, doc):
        self.next_id += 1
        uid = "fake-uuid-" + str(self.next_id)
        value = copy.deepcopy(doc)
        value["id"] = uid
        self.docs[uid] = value
        self.created.append(value["clientId"])
        return uid

    def inventory(self):
        return [{"id": uid, "clientId": doc["clientId"]}
                for uid, doc in self.docs.items()]

    def api(self, path, *, token=None, method="GET", payload=None):
        assert path.startswith("/admin/realms/prp-mcp/")
        sub = path.removeprefix("/admin/realms/prp-mcp")
        if sub == "/client-scopes":
            return copy.deepcopy(self.scope_defs)
        if sub == "/client-policies/profiles":
            return copy.deepcopy(self.profiles)
        if sub == "/client-policies/policies":
            return copy.deepcopy(self.policies)
        if sub == "/clients?max=100":
            return self.inventory()
        if sub.startswith("/clients?clientId="):
            wanted = unquote(sub[len("/clients?clientId="):])
            return [c for c in self.inventory() if c["clientId"] == wanted]
        if sub == "/clients" and method == "POST":
            name = payload["clientId"]
            if name == self.fail_on_target:
                raise RuntimeError("SYNTHETIC_FAIL_BEFORE_POST")
            if name in (d["clientId"] for d in self.docs.values()):
                raise RuntimeError("DUPLICATE_ID")
            self.create(payload)
            return None
        if sub.startswith("/clients/"):
            part = sub.removeprefix("/clients/").split("/")
            key = unquote(part[0])
            if method == "DELETE":
                self.removed.append(self.docs[key]["clientId"])
                del self.docs[key]
                return None
            doc = self.docs[key]
            if len(part) == 1:
                return copy.deepcopy(doc)
            if part[1:] == ["optional-client-scopes"]:
                return [{"name": s} for s in doc.get("optionalClientScopes", [])]
            if part[1:] == ["default-client-scopes"]:
                return [{"name": s} for s in doc.get("defaultClientScopes", [])]
            if part[1:] == ["protocol-mappers", "models"]:
                return copy.deepcopy(doc.get("protocolMappers", []))
        raise RuntimeError("UNSUPPORTED_FAKE_ADMIN_ROUTE")


class RestoredExactTwoClientTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text()
        self.assertEqual(self.script.count(START), 1)
        self.assertEqual(self.script.count(END), 1)
        between = self.script.split(START, 1)[1].split(END, 1)[0]
        self.code = textwrap.dedent(START + between)
        compile(self.code, str(SCRIPT) + "#exact-clone-python", "exec")

    def execute(self, mock, *, baseline_count=13):
        inventory = mock.inventory()
        if baseline_count != 13:
            inventory = set((x["id"], x["clientId"]) for x in inventory[:baseline_count])
        else:
            inventory = set((x["id"], x["clientId"]) for x in inventory)
        context = {
            "__builtins__": __builtins__,
            "Path": Path,
            "verifier_file": str(PROPOSAL.with_name("oauth_token_check.py")),
            "root": "/admin/realms/prp-mcp",
            "token": "synthetic-never-network",
            "inventory": inventory,
            "clients_before": mock.inventory(),
            "api": mock.api,
            "resource": "https://prp-test.micor.top/api/mcp",
            "profiles": copy.deepcopy(mock.profiles),
            "policies": copy.deepcopy(mock.policies),
        }
        exec(self.code, context)

    def test_host_guard_and_pinned_unchanged_proposals(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        self.assertIn("EXACT_CLIENT_REVIEW_PIN=602e2e6a91a2b072fc9f025272081c2f5c04376c", self.script)
        self.assertIn('git -C "$SOURCE_REPO" show "$EXACT_CLIENT_REVIEW_PIN:$EXACT_CLIENT_REVIEW_PATH"', self.script)
        self.assertIn("RESTORED_EXACT_CLIENT_B2_RECEIPT=NOT_ISSUED", self.code)
        self.assertIn("13-client snapshot", self.code)
        self.assertIn("attempted_names.append(client_name)", self.code)
        self.assertIn("finally:", self.code)
        self.assertNotIn("auth-test.micor.top/admin", self.code)

    def test_true_13_fake_originals_preserved_after_two_client_add_rollback(self):
        mock = FakeKeycloak()
        original = copy.deepcopy(mock.docs)
        self.execute(mock)
        self.assertEqual(mock.docs, original)
        self.assertEqual(mock.created[-2:],
                         ["prp-first-party-link", "https://chatgpt.com/oauth/client.json"])
        self.assertEqual(mock.removed,
                         ["https://chatgpt.com/oauth/client.json", "prp-first-party-link"])

    def test_one_failed_create_still_rolls_back_first(self):
        mock = FakeKeycloak(fail_on_target="https://chatgpt.com/oauth/client.json")
        original = copy.deepcopy(mock.docs)
        with self.assertRaisesRegex(RuntimeError, "SYNTHETIC_FAIL_BEFORE_POST"):
            self.execute(mock)
        self.assertEqual(mock.docs, original)
        self.assertEqual(mock.removed, ["prp-first-party-link"])

    def test_reject_wrong_baseline_cardinality_before_creations(self):
        mock = FakeKeycloak()
        original = copy.deepcopy(mock.docs)
        with self.assertRaises(AssertionError):
            self.execute(mock, baseline_count=12)
        self.assertEqual(mock.docs, original)
        self.assertEqual(len(mock.created), 13)


if __name__ == "__main__":
    unittest.main()
