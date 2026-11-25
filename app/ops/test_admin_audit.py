import fcntl
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from admin_grant import (GrantAdminFixture, LOCK_NAME, MAX_GRANT_SECONDS,
                         record, plan, digest)
from auth_adapter import GRANT_NAME, parse_grant, verify_introspection
from audit_store import AuditStoreFixture, AUDIT_NAME, MAX_AUDIT_BYTES
from query_contract import QueryDenied, ISSUER, RESOURCE, SUBJECT, CLIENT, SCOPE
from test_snapshot_contract import NOW

class GrantAdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.dir.chmod(0o755)
        self.path=self.dir/GRANT_NAME
        self.seed=record(str(uuid.uuid4()),NOW-10,NOW+600,False)
        self.path.write_bytes(self.seed)
        self.path.chmod(0o640)
        (self.dir/LOCK_NAME).touch(mode=0o600)
        self.admin=GrantAdminFixture(self.dir,owner_uid=os.geteuid(),reader_gid=os.getegid())

    def issue(self,**kw):
        return self.admin.change("issue",digest(self.seed),**dict(now=NOW,expires=NOW+600,approved=True,**kw))

    def test_explicit_issue_renew_revoke(self):
        first=self.issue()
        initial=parse_grant(self.path.read_bytes())
        self.assertTrue(initial.active)
        self.assertEqual(first,digest(self.path.read_bytes()))
        renewed=self.admin.change("renew",first,now=NOW+10,expires=NOW+700,approved=True)
        current=parse_grant(self.path.read_bytes())
        self.assertNotEqual(current.grant_id,initial.grant_id)
        self.assertEqual(current.issued_at,NOW+10)
        self.admin.change("revoke",renewed,now=NOW+20,approved=True)
        revoked=parse_grant(self.path.read_bytes())
        self.assertEqual(revoked.grant_id,current.grant_id)
        self.assertFalse(revoked.active)
        self.assertEqual(self.path.stat().st_mode&0o777,0o640)

    def test_old_token_cannot_use_renewed_grant(self):
        first=self.issue()
        self.admin.change("renew",first,now=NOW+10,expires=NOW+700,approved=True)
        current=parse_grant(self.path.read_bytes())
        claims={"active":True,"iss":ISSUER,"sub":SUBJECT,"aud":[RESOURCE],
                "client_id":CLIENT,"scope":SCOPE,"token_type":"Bearer","iat":NOW+1,"exp":NOW+300}
        with self.assertRaises(QueryDenied):
            verify_introspection(json.dumps(claims).encode(),current,NOW+11)
        claims["iat"]=NOW+11
        self.assertEqual(verify_introspection(json.dumps(claims).encode(),current,NOW+11).grant_id,current.grant_id)

    def test_stale_cas_and_missing_state_no_recreate(self):
        first=self.issue()
        raw=self.path.read_bytes()
        with self.assertRaises(QueryDenied):
            self.admin.change("renew",digest(self.seed),now=NOW+10,expires=NOW+700,approved=True)
        self.assertEqual(self.path.read_bytes(),raw)
        self.path.unlink()
        with self.assertRaises(OSError):
            self.admin.change("revoke",first,now=NOW+20,approved=True)
        self.assertFalse(self.path.exists())

    def test_approval_ttl_and_wrong_transitions(self):
        for action,now,expires,approved in (("issue",NOW,NOW+600,False),
            ("issue",NOW,NOW+600,1),("issue",NOW,NOW+MAX_GRANT_SECONDS+1,True),
            ("renew",NOW,NOW+600,True),("revoke",NOW,None,True),
            ("issue",NOW-10,NOW+600,True),("shell",NOW,NOW+600,True)):
            with self.subTest(action=action,approved=approved),self.assertRaises((QueryDenied,ValueError)):
                plan(self.seed,action,now=now,expires=expires,approved=approved)
        self.assertEqual(self.path.read_bytes(),self.seed)

    def test_wrong_uid_symlink_and_locked_admin_deny(self):
        with patch("admin_grant.os.geteuid",return_value=os.geteuid()+1):
            with self.assertRaises(QueryDenied):
                self.issue()
        with open(self.dir/LOCK_NAME,"rb+") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.issue()
        self.path.unlink()
        self.path.symlink_to(self.dir/LOCK_NAME)
        with self.assertRaises(OSError):
            self.issue()

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.path=self.dir/AUDIT_NAME
        self.path.touch(mode=0o600)
        self.store=AuditStoreFixture(self.dir,owner_uid=os.geteuid(),clock=lambda:NOW)
        self.event={"version":1,"traceId":str(uuid.uuid4()),"route":"mcp","candidateStatus":200,"outcome":"handled"}

    def test_append_and_reopen(self):
        self.assertTrue(self.store(self.event))
        self.assertTrue(AuditStoreFixture(self.dir,owner_uid=os.geteuid(),clock=lambda:NOW+1)(
            dict(self.event,traceId=str(uuid.uuid4()))))
        rows=[json.loads(line) for line in self.path.read_bytes().splitlines()]
        self.assertEqual(len(rows),2)
        self.assertEqual(set(rows[0]),set(self.event)|{"recordedAt"})
        self.assertEqual(rows[0]["candidateStatus"],200)

    def test_unknown_fields_and_invalid_time_denied(self):
        self.assertFalse(self.store(dict(self.event,token="secret")))
        self.assertFalse(self.store(dict(self.event,candidateStatus=True)))
        self.assertFalse(AuditStoreFixture(self.dir,owner_uid=os.geteuid(),clock=lambda:True)(self.event))
        self.assertEqual(self.path.read_bytes(),b"")

    def test_capacity_and_incomplete_tail_no_repair(self):
        self.path.write_bytes(b"x"*(MAX_AUDIT_BYTES-1)+b"\n")
        self.assertFalse(self.store(self.event))
        self.assertEqual(self.path.stat().st_size,MAX_AUDIT_BYTES)
        self.path.write_bytes(b"incomplete")
        self.assertFalse(self.store(self.event))
        self.assertEqual(self.path.read_bytes(),b"incomplete")

    def test_missing_link_fifo_and_wrong_mode(self):
        self.path.chmod(0o644)
        self.assertFalse(self.store(self.event))
        self.path.unlink()
        self.assertFalse(self.store(self.event))
        target=self.dir/"other"
        target.touch(mode=0o600)
        self.path.symlink_to(target)
        self.assertFalse(self.store(self.event))
        self.path.unlink()
        os.link(target,self.path)
        self.assertFalse(self.store(self.event))
        self.path.unlink()
        os.mkfifo(self.path,0o600)
        self.assertFalse(self.store(self.event))

    def test_lock_and_fsync_failure_denied(self):
        with open(self.path,"rb+") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertFalse(self.store(self.event))
        with patch("audit_store.os.fsync",side_effect=OSError("failure")):
            self.assertFalse(self.store(self.event))
        # Failed fsync is uncertain; an append may remain. No rollback or repair.
        self.assertTrue(self.path.read_bytes().endswith(b"\n"))
