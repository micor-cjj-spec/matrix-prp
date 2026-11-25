"""Offline administrator lifecycle candidate; never an MCP tool or live CLI.

Only a separately approved administrator may call this fixed-schema publisher.
The explicit fixture directory and UID/GID are trusted configuration, not
request values. No account, authorization server, credential or real grant is
created by importing this module.
"""
import fcntl
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path
from auth_adapter import GRANT_NAME, GRANT_LIMIT, parse_grant
from query_contract import ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPE, require
from snapshot_contract import ENV, strict_json, utc

LOCK_NAME = "grant-admin.lock"
MAX_GRANT_SECONDS = 7 * 86400  # candidate, not a production authorization
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

def open_fixed_directory(path, owner, mode):
    path=Path(path)
    require(path.is_absolute() and type(owner) is int and owner>=0)
    fd=os.open("/",FLAGS)
    try:
        for part in path.parts[1:]:
            require(part not in ("", ".", ".."))
            child=os.open(part,FLAGS,dir_fd=fd)
            os.close(fd)
            fd=child
        info=os.fstat(fd)
        require(info.st_uid==owner and stat.S_IMODE(info.st_mode)==mode)
        return fd
    except BaseException:
        os.close(fd)
        raise

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def record(grant_id, now, expires, active):
    result={"version":1,"grantId":grant_id,"issuer":ISSUER,"resource":RESOURCE,
            "client":CLIENT,"subject":SUBJECT,"environment":ENV,"scope":SCOPE,
            "issuedAt":now,"expiresAt":expires,"active":active}
    return encode_grant(result)

def encode_grant(value):
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")
    parse_grant(raw)
    return raw

def plan(current, action, *, now, expires=None, approved=False):
    """Pure lifecycle: rotate on issue/renew, preserve tombstone on revoke."""
    require(approved is True)
    utc(now)
    old=parse_grant(current)
    if action=="revoke":
        # Revocation must not wait until the next clock tick. Keep the ID,
        # advance the inactive tombstone's time barrier and require any
        # subsequent issue to be strictly later than that barrier.
        require(old.active is True and expires is None and now>=old.issued_at)
        return record(old.grant_id,now,max(old.expires_at,now+1),False)
    require(now>old.issued_at)
    require(action=="issue" or action=="renew")
    if action=="renew":
        require(old.active is True and now<old.expires_at)
    else:
        require(old.active is False or now>=old.expires_at)
    utc(expires)
    require(now<expires<=now+MAX_GRANT_SECONDS)
    return record(str(uuid.uuid4()),now,expires,True)

class GrantAdminFixture:
    """CAS under a pre-existing private lock. No initialization on missing state.

    Explicit inactive seed provisioning is separate (test fixture only here).
    Never restore or retry an uncertain commit automatically. Real rollback
    resistance and independent administrator approval are not implemented.
    """
    def __init__(self,directory,*,owner_uid,reader_gid):
        self.directory=Path(directory)
        self.owner_uid=owner_uid
        self.reader_gid=reader_gid

    def change(self,action,expected_digest,*,now,expires=None,approved=False):
        require(approved is True and os.geteuid()==self.owner_uid
                and type(self.reader_gid) is int and self.reader_gid>=0)
        fd=lock=source=out=None
        tmp=None
        try:
            fd=open_fixed_directory(self.directory,self.owner_uid,0o755)
            lock=os.open(LOCK_NAME,os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
            info=os.fstat(lock)
            require(stat.S_ISREG(info.st_mode) and info.st_uid==self.owner_uid
                    and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            source=os.open(GRANT_NAME,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
            info=os.fstat(source)
            require(stat.S_ISREG(info.st_mode) and info.st_uid==self.owner_uid
                    and info.st_gid==self.reader_gid and stat.S_IMODE(info.st_mode)==0o640
                    and info.st_nlink==1 and 0<info.st_size<=GRANT_LIMIT)
            with os.fdopen(source,"rb") as stream:
                source=None
                raw=stream.read(GRANT_LIMIT+1)
            require(type(expected_digest) is str and expected_digest==digest(raw))
            new=plan(raw,action,now=now,expires=expires,approved=approved)
            candidate=".grant-"+os.urandom(16).hex()
            out=os.open(candidate,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=fd)
            tmp=candidate
            os.fchown(out,-1,self.reader_gid)
            os.fchmod(out,0o640)
            info=os.fstat(out)
            require(info.st_uid==self.owner_uid and info.st_gid==self.reader_gid
                    and stat.S_IMODE(info.st_mode)==0o640 and info.st_nlink==1)
            with os.fdopen(out,"wb") as stream:
                out=None
                stream.write(new)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp,GRANT_NAME,src_dir_fd=fd,dst_dir_fd=fd)
            tmp=None
            os.fsync(fd)
            return digest(new)
        finally:
            if out is not None:
                os.close(out)
            if source is not None:
                os.close(source)
            if tmp is not None:
                try:
                    os.unlink(tmp,dir_fd=fd)
                except FileNotFoundError:
                    pass
            if lock is not None:
                os.close(lock)
            if fd is not None:
                os.close(fd)
