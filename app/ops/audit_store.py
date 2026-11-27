"""Bounded durable local audit candidate, not a tamper-proof audit service.

Only a pre-provisioned private directory/file are accepted. No auto-creation,
rotation, repair or truncation; full, malformed-tail or uncertain write denies
the request. Runtime UID owns the file, so same-UID/root compromise is outside
the guarantee. Not a network-delivery receipt.
"""
import fcntl
import json
import os
import stat
from pathlib import Path
from admin_grant import open_fixed_directory
from query_contract import grant_id_valid, require
from snapshot_contract import utc

AUDIT_NAME="access.jsonl"
MAX_AUDIT_BYTES=1024*1024
EVENT_KEYS={"version","traceId","route","candidateStatus","outcome"}

def encode_event(event,now):
    require(type(event) is dict and set(event)==EVENT_KEYS)
    require(type(event["version"]) is int and event["version"]==1
            and grant_id_valid(event["traceId"])
            and event["route"] in ("mcp","metadata","unknown")
            and type(event["candidateStatus"]) is int
            and event["candidateStatus"] in (200,202,400,401,403,404,405,406,413,415,429,503)
            and event["outcome"] in ("handled","denied","limited","unavailable"))
    return json.dumps(dict(event,recordedAt=utc(now)),sort_keys=True,
                      separators=(",",":"),allow_nan=False).encode("ascii")+b"\n"

class AuditStoreFixture:
    def __init__(self,directory,*,owner_uid,clock):
        self.directory=Path(directory)
        self.owner_uid=owner_uid
        self.clock=clock

    def __call__(self,event):
        fd=source=None
        try:
            require(os.geteuid()==self.owner_uid)
            row=encode_event(event,self.clock())
            fd=open_fixed_directory(self.directory,self.owner_uid,0o700)
            source=os.open(AUDIT_NAME,os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW|
                           os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
            info=os.fstat(source)
            require(stat.S_ISREG(info.st_mode) and info.st_uid==self.owner_uid
                    and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1)
            fcntl.flock(source,fcntl.LOCK_EX|fcntl.LOCK_NB)
            info=os.fstat(source)
            require(info.st_nlink==1 and 0<=info.st_size<=MAX_AUDIT_BYTES-len(row))
            # Detect an incomplete append; never silently repair or truncate.
            if info.st_size:
                require(os.pread(source,1,info.st_size-1)==b"\n")
            require(os.write(source,row)==len(row))
            os.fsync(source)
            return True
        except Exception:
            return False
        finally:
            if source is not None:
                os.close(source)
            if fd is not None:
                os.close(fd)
