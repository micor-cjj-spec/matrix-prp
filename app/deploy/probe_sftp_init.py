"""Bounded SFTP INIT-only evidence; never opens a path or changes acceptance rules."""
from __future__ import annotations

import os
import re
import selectors
import struct
import subprocess
import time

INIT = struct.pack(">IBI", 5, 1, 3)  # SSH_FXP_INIT, version 3; no filesystem request.
MAX_STDOUT = 8192
MAX_STDERR = 65536


def version_packet(data):
    if len(data) < 4:
        return None
    size = struct.unpack(">I", data[:4])[0]
    if size < 5 or size > MAX_STDOUT - 4 or len(data) < size + 4 or data[4] != 2:
        return None
    # VERSION carries a uint32 version and optional pairs of length-prefixed strings.
    cursor, end = 9, size + 4
    fields = 0
    while cursor < end:
        if cursor + 4 > end:
            return None
        length = struct.unpack(">I", data[cursor:cursor+4])[0]
        cursor += 4 + length
        if cursor > end:
            return None
        fields += 1
    if fields % 2:
        return None
    return struct.unpack(">I", data[5:9])[0]


def exchange(args, timeout=20):
    """Keep stdin OPEN after INIT until response, child exit, limit or timeout.

    Linux runner: selectors bound memory while draining both pipes. A successful
    VERSION ends the SSH connection immediately; no file or directory operation
    is ever constructed. Debug bytes live only in bounded process memory.
    """
    out, err = bytearray(), bytearray()
    timed_out = limited = stdout_eof = stopped_after_version = False
    sent = False
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env={**os.environ, "LC_ALL": "C"})
    deadline = time.monotonic() + timeout
    try:
        try:
            proc.stdin.write(INIT)
            proc.stdin.flush()
            sent = True
        except BrokenPipeError:
            pass
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ, (out, MAX_STDOUT))
            selector.register(proc.stderr, selectors.EVENT_READ, (err, MAX_STDERR))
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    buf, limit = key.data
                    chunk = os.read(key.fd, min(4096, limit + 1 - len(buf)))
                    if not chunk:
                        if key.fileobj is proc.stdout:
                            stdout_eof = True
                        selector.unregister(key.fileobj)
                        continue
                    buf.extend(chunk)
                    if len(buf) > limit:
                        del buf[limit:]
                        limited = True
                        break
                if limited:
                    break
                if version_packet(out) is not None:
                    stopped_after_version = True
                    break
            if not stopped_after_version and not timed_out and not limited:
                try:
                    proc.wait(timeout=max(0.001, deadline-time.monotonic()))
                except subprocess.TimeoutExpired:
                    timed_out = True
        code = proc.poll()
    finally:
        # Kill before closing stdin, so the test cannot cause an EOF-based exit.
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except BrokenPipeError:
                pass
    return classify(bytes(out), bytes(err), code, timed_out=timed_out,
                    limited=limited, stdout_eof=stdout_eof, init_sent=sent,
                    stopped_after_version=stopped_after_version)


def classify(out, err, code, *, timed_out=False, limited=False, stdout_eof=False,
             init_sent=True, stopped_after_version=False):
    lower = err.lower()
    gateway = b"Allowed: deploy, status, check, rollback RELEASE_ID" in err
    rejected = bool(re.search(rb"subsystem request failed on channel [0-9]+(?:\r?\n|$)", lower))
    accepted = bool(re.search(rb"subsystem request accepted on channel [0-9]+", lower))
    version = version_packet(out)
    known = {
        "AUTHENTICATION_ERROR": [b"permission denied (", b"authentication failed", b"no supported authentication methods"],
        "HOST_KEY_ERROR": [b"host key verification failed", b"remote host identification has changed"],
        "NETWORK_ERROR": [b"connection refused", b"connection timed out", b"could not resolve hostname",
                          b"no route to host", b"connection reset by peer", b"connection closed by", b"kex_exchange_identification"],
    }
    transport = next((name for name, markers in known.items() if any(m in lower for m in markers)), None)
    startup = any(m in lower for m in [b"subsystem not found", b"could not exec", b"exec request failed on channel"])
    if version is not None:
        category = "SFTP_ACCESSIBLE"
    elif limited:
        category = "OUTPUT_LIMIT"
    elif timed_out:
        category = "TIMEOUT"
    elif transport:
        category = transport
    elif code == 255 and not out and rejected and not accepted:
        category = "SSH_PROTOCOL_REJECTED"
    elif code == 2 and not out and gateway:
        category = "GATEWAY_REJECTED"
    elif startup:
        category = "SUBSYSTEM_STARTUP_FAILED"
    elif accepted and code is not None:
        category = "SUBSYSTEM_EXITED_WITHOUT_VERSION"
    elif stdout_eof:
        category = "EOF_WITHOUT_VERSION"
    else:
        category = "UNKNOWN_ERROR"
    return {"category": category, "exit_code": code, "stdout_bytes": len(out),
            "stdout_empty": not out, "stderr_bytes": len(err), "stderr_empty": not err,
            "gateway_denial": gateway, "subsystem_request_failed": rejected,
            "subsystem_request_accepted": accepted, "version_response": version is not None,
            "sftp_version": version, "authentication_error": transport == "AUTHENTICATION_ERROR",
            "host_key_error": transport == "HOST_KEY_ERROR", "network_error": transport == "NETWORK_ERROR",
            "timed_out": timed_out, "output_limited": limited, "stdout_eof": stdout_eof,
            "init_sent": init_sent, "stdin_held_open": True,
            "stopped_after_version": stopped_after_version,
            # Evidence only; neither this field nor a process exit grants deployment.
            "sftp_accessible": version is not None}


def probe(base, destination):
    try:
        # -vv debug output is parsed in memory and NEVER printed or written to disk.
        return exchange(base + ["-vv", "-s", destination, "sftp"])
    except Exception:
        return {"category": "PROBE_CLIENT_ERROR", "sftp_accessible": False,
                "version_response": False, "exit_code": None}
