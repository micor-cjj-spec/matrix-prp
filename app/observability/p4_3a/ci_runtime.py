"""Disposable hosted test orchestrator. Actual nonroot UIDs, TLS socket, files.

The exact P4.2 fixture starts the upstream official containers. A temporary
instrumented copy calls this test once after the original readiness check.
All original P4.2 assertions still run, unchanged. No host or real issuer.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path("/run/prp-p43a")
READER = "prp-p43a-reader"
OTHER = "prp-p43a-other"


def check(ok, label):
    if not ok:
        raise AssertionError(label)
    print("OBS_P43A_CASE=" + label + ":PASS", flush=True)


def run(*cmd, **kwargs):
    kwargs.setdefault("timeout", 30)
    return subprocess.run(cmd, check=True, **kwargs)


def exercise(upstream, caller, viewer, work, p41, gateway):
    # Secrets stay on stdin; never argv, logs or repository. They are generated
    # by the disposable exact P4.2 fixture and expire after the test.
    run("sudo", "-n", "env", "GITHUB_ACTIONS=true", "RUNNER_ENVIRONMENT=github-hosted",
        str(Path(sys.executable)), str(Path(__file__).resolve()), "--root-fixture",
        input=json.dumps(dict(upstream=upstream, caller=caller, viewer=viewer,
            work=str(work), p41=str(p41), gateway=str(gateway))), text=True,
        timeout=180)


def root_fixture():
    if os.geteuid() != 0 or os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("disposable hosted CI only")
    data = json.load(sys.stdin)
    work = Path(data["work"])
    # A root-owned copy of the exact source prevents the runtime UID altering it.
    if ROOT.exists():
        raise SystemExit("unexpected fixture directory; do not overwrite")
    ROOT.mkdir(mode=0o755)
    created = []
    proc = None
    try:
        for name in (READER, OTHER):
            run("useradd", "--system", "--no-create-home", "--user-group", "--shell", "/usr/sbin/nologin", name)
            created.append(name)
        reader, other = pwd.getpwnam(READER), pwd.getpwnam(OTHER)
        check(reader.pw_uid > 0 and other.pw_uid > 0 and reader.pw_uid != other.pw_uid
              and reader.pw_gid != other.pw_gid, "distinct-real-linux-identities")
        code = ROOT / "code"
        code.mkdir(mode=0o755)
        for source in (work / "app" / "ops").glob("*.py"):
            shutil.copyfile(source, code / source.name)
        shutil.copyfile(data["p41"], code / "p4_1_ci.py")
        shutil.copyfile(data["gateway"], code / "owner_gateway.py")
        shutil.copyfile(Path(__file__).with_name("runtime.py"), code / "runtime.py")
        for path in code.iterdir():
            path.chmod(0o644)
        sys.path.insert(0, str(code))
        from admin_grant import GrantAdminFixture, digest, record, LOCK_NAME
        from auth_adapter import GRANT_NAME
        from audit_store import AUDIT_NAME, MAX_AUDIT_BYTES
        from runtime import PORT, MARKER, CONFIG
        import httpx

        def put(path, content, mode, uid=0, gid=0):
            path.write_bytes(content)
            os.chown(path, uid, gid)
            path.chmod(mode)

        grant_dir = ROOT / "grant"
        grant_dir.mkdir(mode=0o755)
        audit_dir = ROOT / "audit"
        audit_dir.mkdir(mode=0o700)
        os.chown(audit_dir, reader.pw_uid, reader.pw_gid)
        snapshot_dir = ROOT / "snapshot"
        snapshot_dir.mkdir(mode=0o700)
        os.chown(snapshot_dir, other.pw_uid, other.pw_gid)
        audit_file = audit_dir / AUDIT_NAME
        put(audit_file, b"", 0o600, reader.pw_uid, reader.pw_gid)
        grant_file = grant_dir / GRANT_NAME
        now = int(time.time())
        # Start inactive, activate by the exact #424 administrator CAS API.
        put(grant_file, record(str(uuid.uuid4()), now-30, now+600, False), 0o640, 0, reader.pw_gid)
        put(grant_dir / LOCK_NAME, b"", 0o600)
        admin = GrantAdminFixture(grant_dir, owner_uid=0, reader_gid=reader.pw_gid)
        revision = admin.change("issue", digest(grant_file.read_bytes()), now=now-10,
                                expires=now+500, approved=True)
        owner = secrets.token_urlsafe(32)
        cfg = json.dumps(dict(upstream=data["upstream"], caller=data["caller"], viewer=data["viewer"],
                              owner=owner, issued=now-5, expires=now+300)).encode()
        put(ROOT / CONFIG, cfg, 0o640, 0, reader.pw_gid)
        marker = ("profile-sha256=" + hashlib.sha256(cfg).hexdigest() + "\n").encode()
        cert = ROOT / "tls.crt"
        key = ROOT / "tls.key"
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=ops.invalid", "-addext", "subjectAltName=IP:127.0.0.1",
            "-keyout", str(key), "-out", str(cert), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cert.chmod(0o644)
        os.chown(key, 0, reader.pw_gid)
        key.chmod(0o640)

        def as_user(user, *args):
            return ["setpriv", "--reuid", str(user.pw_uid), "--regid", str(user.pw_gid),
                    "--clear-groups", "--no-new-privs", "--", *args]
        python = str(Path(sys.executable))
        entry = str(code / "runtime.py")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        def exit_code(user, *args):
            return subprocess.run(as_user(user, *args), env=env, timeout=20,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        # Real OS denies writes, directory replacement and cross-account reads.
        check(exit_code(reader, "test", "-r", str(grant_file)) == 0, "reader-grant-readable")
        check(exit_code(reader, "test", "-w", str(grant_file)) != 0
              and exit_code(reader, "test", "-w", str(grant_dir)) != 0
              and exit_code(reader, "test", "-w", str(code)) != 0
              and exit_code(reader, "test", "-w", str(ROOT / CONFIG)) != 0,
              "reader-cannot-write-grant-code-config")
        check(exit_code(other, "test", "-r", str(grant_file)) != 0
              and exit_code(other, "test", "-r", str(ROOT / CONFIG)) != 0
              and exit_code(other, "test", "-r", str(audit_file)) != 0
              and exit_code(other, "test", "-w", str(audit_dir)) != 0,
              "other-account-cannot-read-grant-config-audit")
        check(exit_code(reader, "test", "-w", str(snapshot_dir)) != 0,
              "reader-cannot-write-other-account-data")
        check(subprocess.run([python, entry], timeout=10, env=env).returncode == 78,
              "root-launch-rejected")
        check(exit_code(reader, python, entry) == 78, "missing-marker-startup-denied")
        put(ROOT / MARKER, marker, 0o644)
        check(exit_code(other, python, entry) == 78, "wrong-uid-startup-denied")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", PORT))
        proc = subprocess.Popen(as_user(reader, python, entry), env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = "https://127.0.0.1:" + str(PORT)
        import ssl
        tls = ssl.create_default_context(cafile=str(cert))
        headers = {"Host":"ops.invalid", "Accept":"application/json, text/event-stream",
                   "Content-Type":"application/json", "MCP-Protocol-Version":"2025-06-18",
                   "Authorization":"Bearer " + owner}
        with httpx.Client(base_url=base, verify=tls, timeout=12, trust_env=False) as client:
            for _ in range(80):
                if proc.poll() is not None:
                    raise AssertionError("runtime exited before readiness")
                try:
                    metadata = client.get("/.well-known/oauth-protected-resource/mcp",
                                          headers={"Host":"ops.invalid"})
                    if metadata.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.2)
            else:
                raise AssertionError("TLS metadata not ready")
            check(metadata.json()["resource"] == "https://ops.invalid/mcp", "verified-loopback-tls-metadata")
            # Actual process identity and bound socket, not mocked UID.
            status = Path("/proc") / str(proc.pid) / "status"
            fields = dict(line.split(":",1) for line in status.read_text().splitlines() if ":" in line)
            check(all(int(x) == reader.pw_uid for x in fields["Uid"].split())
                  and all(int(x) == reader.pw_gid for x in fields["Gid"].split())
                  and fields["NoNewPrivs"].strip() == "1", "actual-runtime-nonroot-no-new-privileges")
            listens = subprocess.check_output(["ss","-H","-ltn","sport","=",":"+str(PORT)], text=True)
            check("127.0.0.1:"+str(PORT) in listens and len(listens.splitlines()) == 1,
                  "loopback-only-listener")

            seq = 0
            def call(method, params=None, h=None, path="/mcp", notify=False):
                nonlocal seq
                seq += 1
                payload = {"jsonrpc":"2.0","method":method}
                if not notify:
                    payload["id"] = seq
                if params is not None:
                    payload["params"] = params
                return client.post(path, json=payload, headers=headers if h is None else h)
            initialized = call("initialize", {"protocolVersion":"2025-06-18","capabilities":{},
                                                "clientInfo":{"name":"p43a","version":"1"}})
            check(initialized.status_code == 200 and initialized.json()["result"]["protocolVersion"]=="2025-06-18",
                  "real-sdk-initialize")
            check(call("notifications/initialized", notify=True).status_code in (200,202), "real-sdk-notification")
            listed = call("tools/list", {})
            check([x["name"] for x in listed.json()["result"]["tools"]] == ["prp_observability_query"], "single-tool")
            args = {"name":"prp_observability_query","arguments":{"metric":"memory_available_bytes","window":"5m"}}
            valid = call("tools/call", args)
            payload = valid.json()["result"]["structuredContent"]
            check(valid.status_code == 200 and payload["status"] == "available" and 0 < len(payload["samples"]) <= 61,
                  "real-tls-to-official-grafana-query")
            check(any(x["outcome"]=="handled" and x["candidateStatus"]==200
                      for x in map(json.loads,audit_file.read_text().splitlines())), "real-durable-audit")
            check(call("tools/call",args,h={**headers,"Authorization":"Bearer invalid-token"}).status_code == 401,
                  "invalid-owner-denied")
            duplicate = list(headers.items())+[("Authorization","Bearer duplicate")]
            check(call("tools/call",args,h=duplicate).status_code == 400, "raw-duplicate-auth-denied")
            check(call("tools/call",args,path="/mcp?x=1").status_code == 400, "raw-query-target-denied")
            check(client.post("/mcp",content=b"x"*4097,headers=headers).status_code == 413, "oversize-body-denied")
            check(call("tools/call",args,h={**headers,"Origin":"https://foreign.invalid"}).status_code == 400,
                  "foreign-origin-denied")
            # Prove the audit sink is a real file, failure denies successful data.
            old = audit_file.read_bytes()
            with open(audit_file,"ab") as stream:
                stream.truncate(MAX_AUDIT_BYTES)
            failed = call("tools/call", args)
            check(failed.status_code == 200 and failed.json()["result"]["isError"] is True
                  and "samples" not in failed.text, "audit-cap-denies-disclosure")
            # Restore only the disposable fixture (never production rotation).
            put(audit_file, old, 0o600, reader.pw_uid, reader.pw_gid)
            positive = call("tools/call",args)
            check(positive.status_code == 200 and positive.json()["result"]["isError"] is False,
                  "positive-control-before-actual-revocation")
            admin.change("revoke", revision, now=int(time.time()), approved=True)
            revoked = call("tools/call",args)
            check(revoked.status_code == 401 and "samples" not in revoked.text, "real-admin-cas-revoke-denies")
            (ROOT / MARKER).unlink()
            check(call("tools/call",args).status_code == 503, "marker-removal-fail-closed")
        check(owner not in audit_file.read_text() and data["viewer"] not in audit_file.read_text()
              and "memory_available_bytes" not in audit_file.read_text(), "audit-no-secret-or-metric")
        print("OBS_P43A_RUNTIME=PASS; LIVE_OAUTH_TUNNEL=NOT_ENABLED",flush=True)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        shutil.rmtree(ROOT)
        for user in reversed(created):
            run("userdel", user)


if __name__ == "__main__":
    if sys.argv[1:] != ["--root-fixture"]:
        raise SystemExit("fixture only")
    root_fixture()
