import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from mcp_adapter import TOOL, ServerVerifiedContext, tools_list, tools_call
from query_contract import (ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPES, Policy,
                            VerifiedIdentity, CurrentGrant)
from snapshot_contract import SnapshotStore, unavailable
from test_snapshot_contract import NOW, sample

class MCPAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=SnapshotStore(Path(self.tmp.name))
        self.store.write(sample())
        self.grant_id=str(uuid.uuid4())
        self.identity=VerifiedIdentity(ISSUER,RESOURCE,CLIENT,SUBJECT,SCOPES,
                                       self.grant_id,NOW-10,NOW+300)
        self.grant=CurrentGrant(self.grant_id,ISSUER,RESOURCE,CLIENT,SUBJECT,
                                "staging",SCOPES,NOW-20,NOW+600,True)
        self.identity_provider=Mock(return_value=self.identity)
        self.grant_provider=Mock(return_value=self.grant)
        self.context=ServerVerifiedContext(Policy(True),self.identity_provider,
            self.grant_provider,lambda:NOW,self.store)

    def test_tools_list_exposes_only_one_fixed_readonly_tool(self):
        result=tools_list()
        self.assertEqual(len(result["tools"]),1)
        tool=result["tools"][0]
        self.assertEqual(tool["name"],TOOL)
        self.assertEqual(tool["inputSchema"],{"type":"object","properties":{},"additionalProperties":False})
        self.assertEqual(tool["annotations"],{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False})
        tool["annotations"]["readOnlyHint"]=False
        self.assertTrue(tools_list()["tools"][0]["annotations"]["readOnlyHint"])

    def test_empty_call_returns_only_snapshot_projection(self):
        result=tools_call({"name":TOOL,"arguments":{}},self.context)
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["status"],"fresh")
        self.assertEqual(result["structuredContent"]["environment"],"staging")
        self.assertEqual(json.loads(result["content"][0]["text"]),result["structuredContent"])
        self.assertEqual(self.identity_provider.call_count,1)
        self.assertEqual(self.grant_provider.call_count,2)

    def test_request_metadata_is_ignored_not_identity(self):
        result=tools_call({"name":TOOL,"arguments":{},"_meta":{"progressToken":"synthetic","subject":"attacker","scope":"prp.write.create"}},self.context)
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["status"],"fresh")
        self.assertEqual(self.identity_provider.call_count,1)

    def test_missing_or_invalid_server_context_denied(self):
        for context in (None,{},True,{"subject":SUBJECT}):
            with self.subTest(context=context):
                self.assertTrue(tools_call({"name":TOOL,"arguments":{}},context)["isError"])
        self.identity_provider.assert_not_called()

    def test_only_exact_tool_and_empty_arguments_allowed(self):
        cases=[
            ({"name":"shell","arguments":{}},self.context),
            ({"name":TOOL,"arguments":{"path":"/etc/passwd"}},self.context),
            ({"name":TOOL,"arguments":{"environment":"production"}},self.context),
            ({"name":TOOL,"arguments":None},self.context),
            ({"name":TOOL,"arguments":[]},self.context),
            ({"name":TOOL,"arguments":{},"command":"id"},self.context),
            ({"name":TOOL},self.context),
            ({"arguments":{}},self.context),
            ([],self.context),
            ({"name":TOOL,"arguments":{},"_meta":"spoof"},self.context),
        ]
        for params,context in cases:
            with self.subTest(params=params):
                self.assertTrue(tools_call(params,context)["isError"])
        self.identity_provider.assert_not_called()

    def test_revoked_grant_returns_uniform_mcp_error(self):
        self.grant_provider=Mock(side_effect=[self.grant,CurrentGrant(
            self.grant_id,ISSUER,RESOURCE,CLIENT,SUBJECT,"staging",SCOPES,
            NOW-20,NOW+600,False)])
        context=ServerVerifiedContext(Policy(True),self.identity_provider,
            self.grant_provider,lambda:NOW,self.store)
        result=tools_call({"name":TOOL,"arguments":{}},context)
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"],[{"type":"text","text":"Read-only status query denied."}])
        self.assertNotIn("subject",json.dumps(result))
        self.assertNotIn("grant",json.dumps(result))

    def test_disabled_policy_and_stale_snapshot_do_not_leak_data(self):
        disabled=ServerVerifiedContext(Policy(False),self.identity_provider,
            self.grant_provider,lambda:NOW,self.store)
        self.assertTrue(tools_call({"name":TOOL,"arguments":{}},disabled)["isError"])
        self.identity_provider.assert_not_called()
        self.store.write(dict(sample(),observedAt="2026-11-25T06:30:00Z"))
        stale_context=ServerVerifiedContext(Policy(True),self.identity_provider,
            self.grant_provider,lambda:NOW,self.store)
        result=tools_call({"name":TOOL,"arguments":{}},stale_context)
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["status"],"stale")
        self.assertIsNone(result["structuredContent"]["cpu"])
        self.assertIsNone(result["structuredContent"]["disk"])

    def test_no_transport_or_network_or_registration_imports(self):
        import ast
        from pathlib import Path
        tree=ast.parse((Path(__file__).parent/"mcp_adapter.py").read_text())
        forbidden={"socket","urllib","http","requests","subprocess","fastmcp","mcp"}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for alias in node.names:self.assertNotIn(alias.name.split(".")[0],forbidden)
            if isinstance(node,ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0],forbidden)
