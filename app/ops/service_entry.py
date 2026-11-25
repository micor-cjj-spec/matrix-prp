"""Candidate service launcher. No startup without separate root approval.

No CLI overrides, env-based profile, public listener, test identity or
default secrets. Never invoked by CI except with absent/mocked gates.
"""
import grp
import os
import pwd
import stat
import sys
import time
from pathlib import Path
from asgi_runtime import OpsASGI
from auth_adapter import GrantFile, IntrospectionClient
from audit_store import AuditStoreFixture
from collector_runtime import live_collection_enabled
from http_boundary import Budget, HttpBoundary
from profile_config import approved_profile, ApprovedProfile
from query_contract import Policy, require
from shared_snapshot import SharedSnapshotReader, SNAPSHOT_DIRECTORY, WRITER_ACCOUNT, READER_ACCOUNT, SHARED_GROUP

BIND_HOST="127.0.0.1"
BIND_PORT=18444
AUDIT_DIRECTORY=Path("/var/lib/prp-ops-audit")
CREDENTIAL_DIRECTORY=Path("/run/credentials/prp-ops-mcp.service")
SECRET_NAME="introspection-secret"
CERT_NAME="tls-cert.pem"
KEY_NAME="tls-key.pem"

def credentials_directory():
    # systemd provides a private read-only credential mount. Do not accept
    # CREDENTIALS_DIRECTORY from request or environment.
    fd=os.open(CREDENTIAL_DIRECTORY,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    info=os.fstat(fd)
    if info.st_uid not in (0,os.geteuid()) or info.st_mode&0o077:
        os.close(fd)
        raise ValueError("credential directory unavailable")
    return fd

def read_secret():
    fd=source=None
    try:
        fd=credentials_directory()
        source=os.open(SECRET_NAME,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
        info=os.fstat(source)
        require(stat.S_ISREG(info.st_mode) and info.st_uid in (0,os.geteuid())
                and stat.S_IMODE(info.st_mode)==0o400 and info.st_nlink==1
                and 0<info.st_size<=512)
        raw=os.read(source,513)
        require(len(raw)==info.st_size)
        return raw.decode("ascii")
    finally:
        if source is not None:
            os.close(source)
        if fd is not None:
            os.close(fd)

def compose(profile):
    require(type(profile) is ApprovedProfile and os.geteuid()!=0)
    account=pwd.getpwnam(READER_ACCOUNT)
    writer=pwd.getpwnam(WRITER_ACCOUNT)
    shared=grp.getgrnam(SHARED_GROUP).gr_gid
    private=grp.getgrnam(READER_ACCOUNT).gr_gid
    require(os.geteuid()==account.pw_uid and os.getegid()==private==account.pw_gid
            and account.pw_uid>0 and writer.pw_uid>0
            and account.pw_uid!=writer.pw_uid and shared>0 and private>0 and shared!=private
            and shared in os.getgroups())
    secret=read_secret()
    grants=GrantFile(reader_gid=private,profile=profile.identity)
    # Require pre-provisioned, parseable grant state; inactive is OK so
    # metadata remains discoverable. No creation or repair.
    grants.current()
    store=SharedSnapshotReader(SNAPSHOT_DIRECTORY,writer.pw_uid,shared)
    def clock():
        return int(time.time())
    def enabled():
        return live_collection_enabled() and approved_profile()==profile
    boundary=HttpBoundary(server=dict(policy=Policy(True),
        introspect=IntrospectionClient(profile.client_id,secret,profile=profile.identity),
        grants=grants,trusted_clock=clock,store=store,profile=profile.identity),
        audit_sink=AuditStoreFixture(AUDIT_DIRECTORY,owner_uid=account.pw_uid,clock=clock),
        budget=Budget(),disclosure_check=enabled)
    return OpsASGI(boundary)

def main():
    # Explicit dual approval BEFORE reading credentials, accounts or binding.
    if len(sys.argv)!=1 or os.geteuid()==0:
        return 78
    profile=approved_profile()
    if profile is None or not live_collection_enabled():
        return 78
    app=None
    try:
        app=compose(profile)
        import uvicorn
        config=uvicorn.Config(app,host=BIND_HOST,port=BIND_PORT,
            ssl_certfile=str(CREDENTIAL_DIRECTORY/CERT_NAME),
            ssl_keyfile=str(CREDENTIAL_DIRECTORY/KEY_NAME),
            loop="asyncio",http="h11",ws="none",lifespan="on",
            proxy_headers=False,access_log=False,log_config=None,log_level="critical",
            server_header=False,date_header=False,limit_concurrency=16,
            timeout_keep_alive=1,timeout_graceful_shutdown=2,
            h11_max_incomplete_event_size=16384)
        # Refuse if approval changed during composition. No public socket.
        if approved_profile()!=profile or not live_collection_enabled():
            return 78
        server=uvicorn.Server(config)
        server.run()
        return 0 if server.started else 1
    except (Exception,SystemExit):
        return 1
    finally:
        if app is not None:
            app.close()

if __name__=="__main__":
    raise SystemExit(main())
