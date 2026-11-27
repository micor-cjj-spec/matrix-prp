"""Synthetic adapter tests only: never contact GitHub or SSH."""
import unittest
from unittest.mock import patch, Mock
import uuid

import actions_bridge as adapter
from protocol import InvalidJob, REPOSITORY

TOKEN = "synthetic_token_only_123456"
def event():
    actor = {"login":"micor-cjj-spec","id":123868412,"type":"User"}
    return {"action":"created","repository":{"full_name":REPOSITORY},
            "sender":actor.copy(),"issue":{"number":506,"state":"open"},
            "comment":{"id":1,"user":actor.copy(),"author_association":"OWNER",
                       "body":"/prp-remote-v11-approve "+str(uuid.uuid4())+" "+"a"*64+" "+"b"*16}}

def receipt():
    return "/prp-remote-result-v11 "+str(uuid.uuid4())+" "+"c"*16

class ActionsAdapterTests(unittest.TestCase):
    def test_default_off_and_wrong_scope(self):
        with patch("actions_bridge.relay_over_ssh") as relay, patch("actions_bridge.post_receipt") as post:
            with self.assertRaises(InvalidJob):
                adapter.dispatch(event(), REPOSITORY, "refs/heads/main", token=TOKEN)
            for e, ref in [(event(), "refs/heads/dev"), (event(), "refs/heads/main")]:
                if ref.endswith("main"):
                    e["issue"]["number"] = 277
                with self.assertRaises(InvalidJob):
                    adapter.dispatch(e, REPOSITORY, ref, enabled=True, token=TOKEN)
            e = event()
            e["comment"]["author_association"] = "MEMBER"
            with self.assertRaises(InvalidJob):
                adapter.dispatch(e, REPOSITORY, "refs/heads/main", enabled=True, token=TOKEN)
            relay.assert_not_called()
            post.assert_not_called()

    def test_fixed_route_and_no_artifact_allowlist(self):
        e = event()
        value = receipt()
        with patch("actions_bridge.relay_over_ssh", return_value=value) as relay, patch("actions_bridge.post_receipt") as post:
            adapter.dispatch(e, REPOSITORY, "refs/heads/main", enabled=True, token=TOKEN)
            self.assertEqual(relay.call_args.args, (e, REPOSITORY, "refs/heads/main", 506))
            self.assertEqual(relay.call_args.kwargs["approved_producers"], frozenset())
            post.assert_called_once_with(value, TOKEN)

    def test_relay_failure_no_publication(self):
        with patch("actions_bridge.relay_over_ssh", side_effect=InvalidJob("synthetic")) as relay, patch("actions_bridge.post_receipt") as post:
            with self.assertRaises(InvalidJob):
                adapter.dispatch(event(), REPOSITORY, "refs/heads/main", enabled=True, token=TOKEN)
            relay.assert_called_once()
            post.assert_not_called()

    def test_post_only_ciphertext_and_no_redirect(self):
        value = receipt()
        with patch("actions_bridge.http.client.HTTPSConnection") as https:
            conn = https.return_value
            response = conn.getresponse.return_value
            response.status = 201
            adapter.post_receipt(value, TOKEN)
            self.assertEqual(conn.request.call_args.args, ("POST", "/repos/"+REPOSITORY+"/issues/506/comments"))
            self.assertEqual(__import__("json").loads(conn.request.call_args.kwargs["body"]), {"body":value})
            response.status = 302
            with self.assertRaises(InvalidJob):
                adapter.post_receipt(value, TOKEN)
            self.assertEqual(conn.request.call_count, 2)
        with patch("actions_bridge.http.client.HTTPSConnection") as https:
            with self.assertRaises(InvalidJob):
                adapter.post_receipt("plaintext", TOKEN)
            https.assert_not_called()

    def test_environment_default_denial(self):
        with patch.dict("os.environ", {}, clear=True), patch("actions_bridge.dispatch") as dispatch:
            with self.assertRaises(InvalidJob):
                adapter.main()
            dispatch.assert_not_called()

if __name__ == "__main__":
    unittest.main()
