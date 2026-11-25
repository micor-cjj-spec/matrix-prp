import ast
import tempfile
import threading
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from snapshot_contract import SnapshotStore, unavailable
from test_snapshot_contract import NOW, sample, BEFORE, AFTER, MEM
from collector_runtime import collect_once
from shared_snapshot import SharedSnapshotWriter, SharedSnapshotReader
from query_contract import (TOOL, SCOPE, ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPES,
                            Policy, VerifiedIdentity, CurrentGrant, QueryDenied,
                            query_status_fixture)

class QueryContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = SnapshotStore(Path(self.tmp.name))
        self.store.write(sample())
        self.id = str(uuid.uuid4())
        self.identity = VerifiedIdentity(ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPES,
                                         self.id, NOW-10, NOW+300)
        self.grant = CurrentGrant(self.id, ISSUER, RESOURCE, CLIENT, SUBJECT,
                                  "staging", SCOPES, NOW-20, NOW+600, True)
        self.identity_provider = Mock(return_value=self.identity)
        self.grant_provider = Mock(return_value=self.grant)
        self.args = dict(policy=Policy(True), identity_provider=self.identity_provider,
                         grant_provider=self.grant_provider, trusted_clock=lambda: NOW,
                         store=self.store)

    def query(self, tool=TOOL, raw=b"{}", **changes):
        return query_status_fixture(tool, raw, **dict(self.args, **changes))

    def denied(self, **changes):
        with self.assertRaisesRegex(QueryDenied, "^query denied$"):
            self.query(**changes)

    def test_exact_scope_preapproved_query_reads_only_snapshot(self):
        before = (self.store.directory / "status.json").read_bytes()
        with patch.object(self.store, "write", side_effect=AssertionError("write forbidden")):
            value = self.query()
        self.assertEqual(value["status"], "fresh")
        self.assertEqual(value["memory"]["usagePercent"],50.0)
        self.assertEqual(self.identity_provider.call_count,1)
        self.assertEqual(self.grant_provider.call_count,2)
        self.assertEqual(before,(self.store.directory/"status.json").read_bytes())

    def test_default_off_no_provider_or_read(self):
        with patch.object(self.store,"read_raw") as reader:
            self.denied(policy=Policy())
            self.denied(policy=Policy(1))
            self.denied(policy={"enabled":True})
            reader.assert_not_called()
        self.identity_provider.assert_not_called()
        self.grant_provider.assert_not_called()

    def test_reject_other_tool_and_nonempty_or_malformed_arguments(self):
        with patch.object(self.store,"read_raw") as reader:
            for tool,raw in (("shell",b"{}"),(TOOL,b'{"environment":"production"}'),
                (TOOL,b'{"path":"/etc/passwd"}'),(TOOL,b'{"url":"https://invalid"}'),
                (TOOL,b'{"approved":true}'),(TOOL,b'{"subject":"synthetic-staging-owner"}'),
                (TOOL,b'{"x":1,"x":2}'),(TOOL,b"[]"),(TOOL,b"null"),
                (TOOL,b"{}"+b" "*256),(TOOL,{}),(TOOL,b"\xff")):
                with self.subTest(tool=tool,raw=raw),self.assertRaises(QueryDenied):
                    self.query(tool,raw)
            reader.assert_not_called()
        self.identity_provider.assert_not_called()

    def test_allow_whitespace_empty_object(self):
        self.assertEqual(self.query(raw=b" { } ")["status"],"fresh")

    def test_unverified_or_legacy_identity_denied_before_read(self):
        with patch.object(self.store,"read_raw") as reader:
            for identity in (None,{},True,{"subject":SUBJECT}):
                self.denied(identity_provider=lambda i=identity:i)
            reader.assert_not_called()

    def test_wrong_identity_fields_or_scope_denied(self):
        with patch.object(self.store,"read_raw") as reader:
            changes = {"issuer":"other","audience":"https://production.invalid/mcp",
                       "client":"other","subject":"other","grant_id":"not-uuid",
                       "scopes":frozenset({"prp.tasks.read"})}
            for key,value in changes.items():
                self.denied(identity_provider=lambda k=key,v=value:replace(self.identity,**{k:v}))
            for scopes in (frozenset(),frozenset({SCOPE,"prp.write.create"}),{SCOPE}):
                self.denied(identity_provider=lambda s=scopes:replace(self.identity,scopes=s))
            reader.assert_not_called()
        self.grant_provider.assert_not_called()

    def test_expired_future_and_boolean_token_timestamps(self):
        for changes in ({"expires_at":NOW},{"issued_at":NOW+1},{"issued_at":True}):
            self.denied(identity_provider=lambda c=changes:replace(self.identity,**c))

    def test_missing_revoked_or_wrong_grant_denied_before_read(self):
        with patch.object(self.store,"read_raw") as reader:
            for grant in (None,{},False,replace(self.grant,active=False),replace(self.grant,active=1),
                replace(self.grant,environment="production"),replace(self.grant,subject="other"),
                replace(self.grant,resource="other"),replace(self.grant,issuer="other"),
                replace(self.grant,client="other"),replace(self.grant,grant_id=str(uuid.uuid4())),
                replace(self.grant,scopes=frozenset({"prp.tasks.read"})),
                replace(self.grant,expires_at=NOW),replace(self.grant,issued_at=NOW)):
                self.denied(grant_provider=lambda _,g=grant:g)
            reader.assert_not_called()

    def test_revoked_during_read_denies_result(self):
        provider=Mock(side_effect=[self.grant,replace(self.grant,active=False)])
        self.denied(grant_provider=provider)
        self.assertEqual(provider.call_count,2)

    def test_changed_grant_during_read_denies_result(self):
        self.denied(grant_provider=Mock(side_effect=[self.grant,replace(self.grant,expires_at=NOW+500)]))

    def test_token_expiry_during_read_denies_result(self):
        self.denied(trusted_clock=Mock(side_effect=[NOW,NOW+1,NOW+300]))

    def test_grant_expiry_during_read_denies_result(self):
        self.denied(grant_provider=lambda _:replace(self.grant,expires_at=NOW+2),
                    trusted_clock=Mock(side_effect=[NOW,NOW+1,NOW+2]))

    def test_clock_missing_regresses_or_invalid_denied(self):
        for clock in (None,lambda:True,Mock(side_effect=[NOW,NOW-1]),
                      Mock(side_effect=[NOW,NOW+1,NOW])):
            self.denied(trusted_clock=clock)

    def test_provider_failure_no_detail_leaks(self):
        for changes in ({"identity_provider":Mock(side_effect=RuntimeError("SECRET"))},
                        {"grant_provider":Mock(side_effect=RuntimeError("SECRET"))},
                        {"grant_provider":Mock(side_effect=[self.grant,RuntimeError("SECRET")])}):
            self.denied(**changes)

    def test_freshness_recalculated_after_grant_check(self):
        value=self.query(trusted_clock=Mock(side_effect=[NOW+118,NOW+119,NOW+120]))
        self.assertEqual(value["status"],"stale")
        self.assertIsNone(value["cpu"])
        self.assertIsNone(value["disk"])

    def test_missing_or_malformed_snapshot_only_authorized_unavailable(self):
        path=self.store.directory/"status.json"
        path.unlink()
        self.assertEqual(self.query(),unavailable())
        path.write_bytes(b'{"secret":"not returned"}')
        path.chmod(0o600)
        self.assertEqual(self.query(),unavailable())
        self.denied(policy=Policy())

    def test_parallel_queries_reuse_grant_without_write_or_collection(self):
        results=[]
        failures=[]
        def run():
            try:
                results.append(self.query())
            except Exception as exc:
                failures.append(type(exc).__name__)
        threads=[threading.Thread(target=run) for _ in range(8)]
        with patch.object(self.store,"write",side_effect=AssertionError("write forbidden")):
            for t in threads:t.start()
            for t in threads:t.join()
        self.assertEqual(failures,[])
        self.assertEqual(len(results),8)
        self.assertTrue(all(v==results[0] and v["status"]=="fresh" for v in results))
        self.assertEqual(self.grant_provider.call_count,16)

    def test_no_unreviewed_store_adapter(self):
        self.denied(store=Mock())


    def test_separate_uid_shared_group_reader_is_accepted(self):
        import os
        uid=os.geteuid()
        gid=os.getegid()
        directory=Path(self.tmp.name)/"shared"
        directory.mkdir(mode=0o700)
        directory.chmod(0o2750)
        writer=SharedSnapshotWriter(directory,uid,gid)
        writer.write(sample())
        reader=SharedSnapshotReader(directory,uid,gid)
        with patch("shared_snapshot.os.geteuid",return_value=uid+10000), patch("shared_snapshot.os.getegid",return_value=gid), patch("shared_snapshot.os.getgroups",return_value=[gid]):
            value=self.query(store=reader)
        self.assertEqual(value["status"],"fresh")
        self.assertEqual(value["cpu"]["usagePercent"],30.0)


    def test_collector_to_shared_snapshot_to_authorized_query(self):
        import os
        from types import SimpleNamespace
        uid=os.geteuid()
        gid=os.getegid()
        directory=Path(self.tmp.name)/"collector-shared"
        directory.mkdir(mode=0o700)
        directory.chmod(0o2750)
        writer=SharedSnapshotWriter(directory,uid,gid)
        samples=iter([BEFORE,AFTER,MEM])
        collect_once(proc_reader=lambda name: next(samples),
            disk_reader=lambda:SimpleNamespace(f_frsize=1024,f_blocks=100,f_bfree=40,f_bavail=30),
            sleeper=lambda seconds:None,wall_clock=lambda:NOW,writer=writer)
        reader=SharedSnapshotReader(directory,uid,gid)
        with patch("shared_snapshot.os.geteuid",return_value=uid+10000), patch("shared_snapshot.os.getegid",return_value=gid), patch("shared_snapshot.os.getgroups",return_value=[gid]):
            result=self.query(store=reader)
        self.assertEqual(result["status"],"fresh")
        self.assertEqual(result["cpu"]["usagePercent"],30.0)
        self.assertEqual(result["memory"]["usagePercent"],50.0)
        self.assertEqual(result["disk"]["usagePercent"],60.0)
        self.assertEqual(result["application"],{"backend":"unknown","readiness":"unknown"})

class OfflineBoundaryTests(unittest.TestCase):
    def test_no_network_process_or_live_tool_registration_imports(self):
        allowed={"json","math","os","re","stat","datetime","pathlib","dataclasses","uuid","snapshot_contract","shared_snapshot"}
        forbidden_calls={"eval","exec","compile","__import__","os.system","os.popen","os.statvfs"}
        for name in ("snapshot_contract.py","query_contract.py"):
            tree=ast.parse((Path(__file__).parent/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    for alias in node.names:self.assertIn(alias.name,allowed)
                elif isinstance(node,ast.ImportFrom):
                    self.assertIn(node.module,allowed)
                elif isinstance(node,ast.Call):
                    target=node.func
                    key=target.id if isinstance(target,ast.Name) else (
                        target.value.id+"."+target.attr if isinstance(target,ast.Attribute)
                        and isinstance(target.value,ast.Name) else "")
                    self.assertNotIn(key,forbidden_calls)
