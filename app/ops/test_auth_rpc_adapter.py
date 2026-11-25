import base64
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

from auth_adapter import (GrantFile, GRANT_NAME, IntrospectionClient, bearer_token,
    authorize_request, parse_grant, verify_introspection)
from query_contract import (ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPE, TOOL,
    Policy, QueryDenied)
from snapshot_contract import SnapshotStore
from test_snapshot_contract import NOW, sample
from rpc_adapter import dispatch_fixture, PROTOCOL

class RequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name)/"grant"
        self.directory.mkdir()
        self.directory.chmod(0o755)
        self.path=self.directory/GRANT_NAME
        self.uid=os.geteuid()
        self.gid=os.getegid()
        self.grant={"version":1,"grantId":str(uuid.uuid4()),"issuer":ISSUER,
            "resource":RESOURCE,"client":CLIENT,"subject":SUBJECT,"environment":"staging",
            "scope":SCOPE,"issuedAt":NOW-20,"expiresAt":NOW+600,"active":True}
        self.write_grant(self.grant)
        self.claims={"active":True,"iss":ISSUER,"sub":SUBJECT,"aud":[RESOURCE],
            "client_id":CLIENT,"azp":CLIENT,"scope":SCOPE,"token_type":"Bearer",
            "iat":NOW-10,"exp":NOW+300}
        self.introspect=Mock(side_effect=lambda _:json.dumps(self.claims).encode())
        self.grants=GrantFile(self.directory,reader_gid=self.gid,owner_uid=self.uid)
        store_dir=Path(self.tmp.name)/"snapshot"
        store_dir.mkdir(mode=0o700)
        self.store=SnapshotStore(store_dir)
        self.store.write(sample())
        self.server=dict(policy=Policy(True),introspect=self.introspect,
                         grants=self.grants,trusted_clock=lambda:NOW,store=self.store)

    def write_grant(self, value):
        self.path.write_bytes(json.dumps(value).encode())
        self.path.chmod(0o640)

    def as_reader(self):
        # Patch only the grant module's effective identity check. SnapshotStore
        # uses the same os module, so restore its expected identity at read time.
        real_read=self.store.read_raw
        def read_snapshot():
            with patch("snapshot_contract.os.geteuid",return_value=self.uid):
                return real_read()
        return (patch("auth_adapter.os.geteuid",return_value=self.uid+10000),
                patch("auth_adapter.os.getgroups",return_value=[self.gid]),
                patch.object(self.store,"read_raw",side_effect=read_snapshot))

    def dispatch(self, method="tools/call", params=None, raw=None, header="Bearer synthetic-token", **changes):
        if raw is None:
            raw=json.dumps({"jsonrpc":"2.0","id":1,"method":method,
                "params":params if params is not None else {"name":TOOL,"arguments":{}}}).encode()
        a,b,c=self.as_reader()
        with a,b,c:
            return dispatch_fixture(raw,header,**dict(self.server,**changes))

    def test_end_to_end_bearer_grant_rpc_read(self):
        status,body=self.dispatch()
        self.assertEqual(status,200)
        self.assertFalse(body["result"]["isError"])
        self.assertEqual(body["result"]["structuredContent"]["status"],"fresh")
        self.introspect.assert_called_once_with("synthetic-token")

    def test_initialization_and_list_authorized(self):
        status,body=self.dispatch("initialize",{"protocolVersion":PROTOCOL,"capabilities":{},"clientInfo":{"name":"fixture","version":"1"}})
        self.assertEqual(status,200)
        self.assertEqual(body["result"]["protocolVersion"],PROTOCOL)
        status,body=self.dispatch("tools/list",{})
        self.assertEqual([v["name"] for v in body["result"]["tools"]],[TOOL])

    def test_denied_list_and_default_off_never_read_snapshot(self):
        for header in (None,"Basic synthetic","Bearer a b","Bearer a\nb","Bearer "+"x"*8193):
            self.assertEqual(self.dispatch("tools/list",{},header=header),(401,None))
        self.assertEqual(self.dispatch(policy=Policy()),(401,None))
        self.introspect.assert_not_called()

    def test_revocation_and_grant_replacement_old_token_denied(self):
        self.assertEqual(self.dispatch()[0],200)
        self.write_grant(dict(self.grant,active=False))
        self.assertEqual(self.dispatch(),(401,None))
        self.write_grant(dict(self.grant,grantId=str(uuid.uuid4()),issuedAt=NOW))
        self.assertEqual(self.dispatch(),(401,None))
        self.claims["iat"]=NOW
        self.assertEqual(self.dispatch()[0],200)

    def test_revocation_during_snapshot_read(self):
        real_read=self.store.read_raw
        def revoke():
            self.write_grant(dict(self.grant,active=False))
            with patch("snapshot_contract.os.geteuid",return_value=self.uid):
                return real_read()
        a,b,_=self.as_reader()
        with a,b,patch.object(self.store,"read_raw",side_effect=revoke):
            raw=b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"prp_ops_status_get","arguments":{}}}'
            status,body=dispatch_fixture(raw,"Bearer synthetic-token",**self.server)
        self.assertEqual(status,200)
        self.assertTrue(body["result"]["isError"])
        self.assertNotIn("structuredContent",body["result"])

    def test_wrong_or_inactive_introspection_claims(self):
        for key,value in (("active",1),("active",False),("iss","wrong"),("sub","wrong"),
            ("aud",[RESOURCE,"https://other.invalid"]),("aud",[RESOURCE,RESOURCE]),
            ("client_id","wrong"),("azp","wrong"),("scope",SCOPE+" prp.write.create"),
            ("token_type","ID"),("iat",True),("iat",NOW+1),("exp",NOW),("nbf",NOW+1),
            ("scp",[SCOPE])):
            previous=self.claims.copy()
            self.claims[key]=value
            with self.subTest(key=key,value=value):
                self.assertEqual(self.dispatch(),(401,None))
            self.claims=previous

    def test_missing_or_malformed_authority_response_denied(self):
        for response in (b"{}",b'{"active":false,"active":true}',b"x"*8193,b"\xff"):
            self.assertEqual(self.dispatch(introspect=lambda _:response),(401,None))
        self.assertEqual(self.dispatch(introspect=Mock(side_effect=RuntimeError("secret"))),(401,None))

    def test_grant_file_missing_wrong_permissions_symlink_and_fifo_denied(self):
        self.path.chmod(0o644)
        self.assertEqual(self.dispatch(),(401,None))
        self.path.unlink()
        self.assertEqual(self.dispatch(),(401,None))
        target=self.directory/"other"
        target.write_bytes(json.dumps(self.grant).encode())
        target.chmod(0o640)
        self.path.symlink_to(target)
        self.assertEqual(self.dispatch(),(401,None))
        self.path.unlink()
        os.link(target,self.path)
        self.assertEqual(self.dispatch(),(401,None))
        self.path.unlink()
        os.mkfifo(self.path,0o640)
        self.assertEqual(self.dispatch(),(401,None))

    def test_grant_schema_and_exact_time_types(self):
        for record in (dict(self.grant,active=1),dict(self.grant,issuedAt=True),
                       dict(self.grant,scope="prp.tasks.read"),dict(self.grant,extra="secret")):
            self.write_grant(record)
            self.assertEqual(self.dispatch(),(401,None))

    def test_rpc_duplicate_keys_batch_oversize_and_invalid_ids(self):
        for raw in (b'{"jsonrpc":"2.0","id":1,"id":2,"method":"tools/list"}',
                    b"[]",b"x"*4097,b'{"jsonrpc":"2.0","id":true,"method":"tools/list"}',
                    b'{"jsonrpc":"2.0","id":1,"method":"tools/list","identity":"spoof"}'):
            status,body=self.dispatch(raw=raw)
            self.assertEqual(status,400)
            self.assertIn("error",body)

    def test_rpc_unknown_method_and_argument_injection_denied(self):
        status,body=self.dispatch("shell",{})
        self.assertEqual(body["error"]["code"],-32601)
        status,body=self.dispatch(params={"name":TOOL,"arguments":{"path":"/etc/passwd"}})
        self.assertTrue(body["result"]["isError"])
        status,body=self.dispatch("tools/list",{"cursor":"other"})
        self.assertEqual(body["error"]["code"],-32602)

    def test_initialized_notification_no_response(self):
        self.assertEqual(self.dispatch(raw=b'{"jsonrpc":"2.0","method":"notifications/initialized"}'),(202,None))

class IntrospectionClientTests(unittest.TestCase):
    def response(self, status=200, content=b'{"active":false}', media="application/json", encoding="identity"):
        response=Mock()
        response.status=status
        response.getheader.side_effect=lambda name,default="": {"Content-Type":media,"Content-Encoding":encoding}.get(name,default)
        response.read.return_value=content
        return response

    def test_fixed_https_endpoint_and_credentials_not_forwarded_elsewhere(self):
        conn=Mock()
        conn.getresponse.return_value=self.response()
        with patch("auth_adapter.http.client.HTTPSConnection",return_value=conn) as factory:
            data=IntrospectionClient("fixture-client","fixture-secret")("synthetic-token")
        self.assertEqual(data,b'{"active":false}')
        self.assertEqual(factory.call_args.args,("issuer.invalid",443))
        self.assertEqual(factory.call_args.kwargs["timeout"],2)
        self.assertTrue(factory.call_args.kwargs["context"].check_hostname)
        args=conn.request.call_args
        self.assertEqual(args.args,("POST","/ops-staging/protocol/openid-connect/token/introspect"))
        self.assertEqual(parse_qs(args.kwargs["body"].decode()),{"token":["synthetic-token"],"token_type_hint":["access_token"]})
        self.assertEqual(base64.b64decode(args.kwargs["headers"]["Authorization"].split()[1]),b"fixture-client:fixture-secret")
        conn.close.assert_called_once()

    def test_bad_status_redirect_oversize_and_compression_fail_closed(self):
        for resp in (self.response(status=302),self.response(status=401),
                     self.response(content=b"x"*8193),self.response(media="text/html"),
                     self.response(encoding="gzip")):
            conn=Mock()
            conn.getresponse.return_value=resp
            with patch("auth_adapter.http.client.HTTPSConnection",return_value=conn):
                with self.assertRaisesRegex(QueryDenied,"^query denied$"):
                    IntrospectionClient("fixture-client","fixture-secret")("synthetic-token")
            self.assertEqual(conn.request.call_count,1)
            conn.close.assert_called_once()

    def test_transport_failure_does_not_leak_secret(self):
        with patch("auth_adapter.http.client.HTTPSConnection",side_effect=OSError("fixture-secret")):
            with self.assertRaisesRegex(QueryDenied,"^query denied$"):
                IntrospectionClient("fixture-client","fixture-secret")("synthetic-token")
