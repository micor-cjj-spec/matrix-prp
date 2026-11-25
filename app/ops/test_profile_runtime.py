import hashlib
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import service_entry
from profile_config import (parse_profile,approved_profile,PROFILE_NAME,APPROVAL_NAME)
from auth_adapter import GrantFile, parse_grant, verify_introspection, IntrospectionClient
from admin_grant import record
from http_boundary import HttpBoundary,Budget,METADATA_PATH
from query_contract import CLIENT,SCOPE,Policy,QueryDenied,TOOL,FIXTURE_PROFILE
from snapshot_contract import SnapshotStore
from test_snapshot_contract import NOW,sample

VALUES={"version":1,"environment":"staging",
    "issuer":"https://id-ops.example.com/realms/prp-ops-staging",
    "resource":"https://ops-staging.example.com/mcp",
    "subject":"owner-fixture-42","introspectionClientId":"prp-ops-staging-resource"}
def raw(**changes):
    return json.dumps(dict(VALUES,**changes),sort_keys=True).encode()

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.dir.chmod(0o755)
        self.uid=os.geteuid()
        self.gid=os.getegid()
        self.profile=parse_profile(raw())
    def write(self,data=None):
        data=raw() if data is None else data
        for name,content in ((PROFILE_NAME,data),(APPROVAL_NAME,
            ("profile-sha256="+hashlib.sha256(data).hexdigest()+"\n").encode())):
            path=self.dir/name
            path.write_bytes(content)
            path.chmod(0o644)
    def load(self):
        return approved_profile(self.dir,owner=self.uid,gid=self.gid)
    def test_missing_marker_and_changed_profile_fail_closed(self):
        self.assertIsNone(self.load())
        self.write()
        self.assertEqual(self.load(),self.profile)
        (self.dir/PROFILE_NAME).write_bytes(raw(subject="changed"))
        self.assertIsNone(self.load())
        self.write()
        (self.dir/APPROVAL_NAME).unlink()
        self.assertIsNone(self.load())
    def test_profile_strict_shape_separate_hosts_and_no_placeholders(self):
        for changes in ({"environment":"production"},{"version":True},
            {"issuer":"http://id.example.com/realms/prp-ops-staging"},
            {"issuer":"https://id.example.com/realms/prp-mcp"},
            {"resource":"https://ops.invalid/mcp"},{"resource":"https://ops.example.com:9443/mcp"},
            {"resource":"https://ops.example.com/mcp?x=1"},{"resource":"https://id-ops.example.com/mcp"},
            {"resource":"https://127.0.0.1/mcp"},{"subject":"synthetic-staging-owner"},
            {"introspectionClientId":"other"},{"extra":"secret"}):
            with self.subTest(changes=changes),self.assertRaises((QueryDenied,ValueError)):
                parse_profile(raw(**changes))
    def test_profile_mode_symlink_and_hardlink_rejected(self):
        self.write()
        path=self.dir/PROFILE_NAME
        path.chmod(0o666)
        self.assertIsNone(self.load())
        path.chmod(0o644)
        other=self.dir/"other"
        os.link(path,other)
        self.assertIsNone(self.load())
        path.unlink()
        path.symlink_to(other)
        self.assertIsNone(self.load())
    def test_alternate_profile_grant_and_introspection_binding(self):
        p=self.profile.identity
        data=record(str(uuid.uuid4()),NOW-20,NOW+600,True,p)
        grant=parse_grant(data,p)
        with self.assertRaises(QueryDenied):
            parse_grant(data)
        claims={"active":True,"iss":p.issuer,"sub":p.subject,"aud":[p.resource],
            "client_id":CLIENT,"scope":SCOPE,"token_type":"Bearer","iat":NOW-10,"exp":NOW+300}
        self.assertEqual(verify_introspection(json.dumps(claims).encode(),grant,NOW,p).subject,p.subject)
        for field,value in (("iss",FIXTURE_PROFILE.issuer),("aud",[FIXTURE_PROFILE.resource]),
                            ("sub",FIXTURE_PROFILE.subject)):
            with self.assertRaises(QueryDenied):
                verify_introspection(json.dumps(dict(claims,**{field:value})).encode(),grant,NOW,p)
    def test_profile_http_metadata_challenge_and_full_query(self):
        p=self.profile.identity
        grant=parse_grant(record(str(uuid.uuid4()),NOW-20,NOW+600,True,p),p)
        claims={"active":True,"iss":p.issuer,"sub":p.subject,"aud":[p.resource],
            "client_id":CLIENT,"scope":SCOPE,"token_type":"Bearer","iat":NOW-10,"exp":NOW+300}
        store_dir=self.dir/"snapshot"
        store_dir.mkdir(mode=0o700)
        store=SnapshotStore(store_dir)
        store.write(sample())
        grants=GrantFile(reader_gid=self.gid,profile=p)
        boundary=HttpBoundary(server=dict(policy=Policy(True),profile=p,
            introspect=lambda _:json.dumps(claims).encode(),grants=grants,
            trusted_clock=lambda:NOW,store=store),audit_sink=lambda _:True,
            budget=Budget(lambda:100),disclosure_check=lambda:True)
        host=[("Host","ops-staging.example.com")]
        metadata=boundary.handle("GET",METADATA_PATH,host,b"")
        self.assertEqual(json.loads(metadata.body)["resource"],p.resource)
        self.assertEqual(json.loads(metadata.body)["authorization_servers"],[p.issuer])
        body=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
            "params":{"name":TOOL,"arguments":{}}}).encode()
        headers=host+[("Content-Type","application/json"),("Accept","application/json, text/event-stream"),
                     ("Content-Length",str(len(body)))]
        with patch.object(grants,"current",return_value=grant):
            denied=boundary.handle("POST","/mcp",headers,body)
            self.assertEqual(denied.status,401)
            self.assertIn("https://ops-staging.example.com"+METADATA_PATH,
                          dict(denied.headers)["WWW-Authenticate"])
            self.assertEqual(boundary.handle("POST","/mcp",
                [("Host","ops.invalid")]+headers[1:],body).status,400)
            got=boundary.handle("POST","/mcp",headers+[("Authorization","Bearer synthetic")],body)
        self.assertEqual(got.status,200)
        self.assertEqual(json.loads(got.body)["result"]["structuredContent"]["status"],"fresh")

    def test_entry_default_disabled_without_creds_or_listener(self):
        with patch("service_entry.sys.argv",["service_entry.py"]), \
             patch("service_entry.os.geteuid",return_value=1001), \
             patch("service_entry.approved_profile",return_value=None), \
             patch("service_entry.compose") as compose:
            self.assertEqual(service_entry.main(),78)
            compose.assert_not_called()
        with patch("service_entry.sys.argv",["service_entry.py"]), \
             patch("service_entry.os.geteuid",return_value=1001), \
             patch("service_entry.approved_profile",return_value=self.profile), \
             patch("service_entry.live_collection_enabled",return_value=False), \
             patch("service_entry.compose") as compose:
            self.assertEqual(service_entry.main(),78)
            compose.assert_not_called()
    def test_entry_rejects_root_and_cli_overrides(self):
        with patch("service_entry.approved_profile") as loader:
            with patch("service_entry.sys.argv",["service_entry.py"]),patch("service_entry.os.geteuid",return_value=0):
                self.assertEqual(service_entry.main(),78)
            with patch("service_entry.sys.argv",["service_entry.py","--host","0.0.0.0"]):
                self.assertEqual(service_entry.main(),78)
            loader.assert_not_called()
