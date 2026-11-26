"""P3 transport candidate. No live entrypoint or configured credentials.

A trusted default-branch workflow will supply authenticated metadata and streams
using fixed GitHub API routes. A manifest is not proof of artifact provenance.
"""
from contextlib import contextmanager
import base64
import binascii
import hashlib
import hmac
import os
import select
import signal
import subprocess
from pathlib import Path
import http.client
import ssl
import time
from urllib.parse import quote, urlsplit
import re
import stat
import struct
import sys
import tempfile
import uuid
import zipfile

from protocol import (REPOSITORY, MAX_ARTIFACT, MAX_FILES, InvalidJob,
                      require, relative_path, validate_job, inline_bytes, canonical, parse,
                      exact, integer, digest, uuid4_text, open_request, MAX_CMS_DER, commit, seal_receipt, validate_file, MAX_INLINE)
from executor import CHUNK

OWNER = "micor-cjj-spec"
MAX_COMMENT = 62000
MAX_ARCHIVE_ENTRIES = 128
COMMAND = re.compile(r"/prp-remote-v11 ([0-9a-f-]{36}) ([A-Za-z0-9_-]{8,60000})\n?")

def verify_event(event, repository, ref, issue):
    """GitHub-event checks, not independent proof of chat approval."""
    require(repository == REPOSITORY and ref == "refs/heads/main", "wrong event context")
    require(type(issue) is int and issue > 0 and type(event) is dict,
            "invalid event configuration")
    require(event.get("action") == "created"
            and event.get("repository", {}).get("full_name") == REPOSITORY,
            "wrong event")
    comment = event.get("comment", {})
    for actor in (event.get("sender", {}), comment.get("user", {})):
        require(actor.get("login") == OWNER and actor.get("type") == "User", "untrusted actor")
    item = event.get("issue", {})
    require(item.get("number") == issue and item.get("state") == "open"
            and item.get("pull_request") is None, "wrong issue")
    require(type(comment.get("id")) is int and comment["id"] > 0, "invalid comment")
    body = comment.get("body")
    require(type(body) is str and len(body) <= MAX_COMMENT, "invalid comment body")
    match = COMMAND.fullmatch(body)
    require(match is not None, "wrong protocol")
    job_id, ciphertext = match.groups()
    try:
        require(str(uuid.UUID(job_id)) == job_id and uuid.UUID(job_id).version == 4,
                "invalid job id")
    except ValueError as exc:
        raise InvalidJob("invalid job id") from exc
    return job_id, ciphertext

def verify_producer(source, run, artifact, approved_producers):
    """Exact allowlist of (workflow filename, source SHA) from trusted config.

    Metadata is obtained independently via the authenticated GitHub API, never
    from the request itself. No default producer authorization. PR artifacts
    are acceptable only for an explicitly reviewed exact source commit.
    """
    require((source["workflow"], source["commit"]) in approved_producers,
            "unapproved producer")
    require(run.get("id") == source["runId"]
            and run.get("repository", {}).get("full_name") == REPOSITORY
            and run.get("head_repository", {}).get("full_name") == REPOSITORY
            and run.get("head_sha") == source["commit"]
            and run.get("path") == ".github/workflows/" + source["workflow"]
            and run.get("status") == "completed" and run.get("conclusion") == "success",
            "run provenance mismatch")
    require(artifact.get("id") == source["artifactId"]
            and artifact.get("name") == source["name"]
            and artifact.get("expired") is False
            and artifact.get("size_in_bytes") == source["archiveSize"]
            and artifact.get("workflow_run", {}).get("id") == source["runId"]
            and artifact.get("workflow_run", {}).get("head_sha") == source["commit"]
            and artifact.get("digest") == "sha256:" + source["archiveSha256"],
            "artifact provenance mismatch")

def chunks(stream):
    while True:
        block = stream.read(CHUNK)
        if not block:
            require(block == b"", "invalid stream EOF")
            return
        require(type(block) is bytes and len(block) <= CHUNK, "invalid stream chunk")
        yield block

@contextmanager
def verified_archive(source, stream, scratch):
    """Bounded archive spool, verify outer bytes before inspecting any member."""
    count = 0
    sha = hashlib.sha256()
    with tempfile.TemporaryFile(dir=scratch) as archive:
        for block in chunks(stream):
            count += len(block)
            require(count <= source["archiveSize"] <= MAX_ARTIFACT, "archive oversized")
            sha.update(block)
            archive.write(block)
        require(count == source["archiveSize"]
                and hmac.compare_digest(sha.hexdigest(), source["archiveSha256"]),
                "archive digest mismatch")
        archive.seek(0)
        try:
            with zipfile.ZipFile(archive) as z:
                entries = z.infolist()
                require(len(entries) <= MAX_ARCHIVE_ENTRIES, "too many archive entries")
                names = set()
                total = 0
                for entry in entries:
                    name = entry.filename.rstrip("/") if entry.is_dir() else entry.filename
                    relative_path(name)
                    key = name.lower()
                    require(key not in names, "duplicate archive path")
                    names.add(key)
                    kind = stat.S_IFMT(entry.external_attr >> 16)
                    require(kind in (0, stat.S_IFDIR if entry.is_dir() else stat.S_IFREG),
                            "unsafe archive entry")
                    require(not (entry.flag_bits & 1)
                            and entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                            "unsupported archive entry")
                    total += entry.file_size
                    require(total <= MAX_ARTIFACT, "expanded archive too large")
                yield z
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
            raise InvalidJob("invalid archive") from exc

def transfer_job(job, ledger, provider, approved_producers=frozenset(), now=None):
    """Receive only; never execute.

    provider is a trusted internal adapter providing:
      repository_file(commit, path) -> context-managed binary stream
      run_metadata(run_id) / artifact_metadata(artifact_id) -> API metadata
      artifact_zip(artifact_id) -> context-managed binary stream
    No arbitrary URL or endpoint is accepted from a manifest. The provider
    must enforce timeouts, authenticated endpoints and safe redirect handling.
    The local Ledger is a stand-in for a future framed SSH receiver.
    """
    validate_job(job, now)
    jid, digest = job["jobId"], job["manifestSha256"]
    # A repeated submit is rejected by the durable ledger. Transfer retry
    # after interruption is separate and must retain exact identity.
    ledger.accept(job, now)
    groups = {}
    for item in job["manifest"]["files"]:
        src = item["source"]
        kind = src["kind"]
        if kind == "inline":
            data = inline_bytes(src)
            ledger.receive_file(jid, digest, item["path"], [data] if data else [], now)
        elif kind == "repository":
            with provider.repository_file(src["commit"], src["path"]) as stream:
                ledger.receive_file(jid, digest, item["path"], chunks(stream), now)
        elif kind == "ci_artifact":
            groups.setdefault((src["runId"], src["artifactId"]), []).append(item)
        else:
            raise InvalidJob("unsupported source")
    for items in groups.values():
        src = items[0]["source"]
        verify_producer(src, provider.run_metadata(src["runId"]),
                        provider.artifact_metadata(src["artifactId"]), approved_producers)
        with provider.artifact_zip(src["artifactId"]) as stream:
            with verified_archive(src, stream, ledger.root) as archive:
                for item in items:
                    try:
                        member = archive.getinfo(item["source"]["member"])
                    except KeyError as exc:
                        raise InvalidJob("missing archive member") from exc
                    require(not member.is_dir() and member.file_size == item["size"],
                            "member size mismatch")
                    with archive.open(member, "r") as data:
                        ledger.receive_file(jid, digest, item["path"], chunks(data), now)
    ledger.verify(jid, digest, now)
    return ledger.status(jid, digest)


def decode_comment_request(event, repository, ref, issue, cert, key, now=None):
    """Call only on an authentic GitHub event from the trusted workflow."""
    public_job_id, encoded = verify_event(event, repository, ref, issue)
    try:
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidJob("invalid ciphertext") from exc
    require(len(raw) <= MAX_CMS_DER
            and base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") == encoded,
            "noncanonical ciphertext")
    request = open_request(raw, cert, key, now)
    require(public_job_id == request["jobId"], "comment job mismatch")
    return request

# Candidate binary framing for a single file over a future authenticated
# staging-only SSH stream. No SSH invocation or remote receiver entrypoint.
# The authenticated control request binds the job and manifest; chunk hashes
# detect corruption, not sender identity. Ledger verifies the whole file.
FRAME_MAGIC = b"PRP11F\x00"
MAX_FRAME_HEADER = 2048

def _read_exact(stream, n):
    result = bytearray()
    while len(result) < n:
        block = stream.read(n - len(result))
        require(type(block) is bytes and 0 < len(block) <= n - len(result), "truncated frame")
        result.extend(block)
    return bytes(result)

def _validate_frame(header, data):
    exact(header, "version jobId manifestSha256 path offset size sha256 final")
    require(type(header["version"]) is int and header["version"] == 11, "wrong frame version")
    uuid4_text(header["jobId"])
    digest(header["manifestSha256"])
    relative_path(header["path"])
    integer(header["offset"], 0, MAX_ARTIFACT)
    integer(header["size"], 0, CHUNK)
    digest(header["sha256"])
    require(type(header["final"]) is bool, "invalid frame final flag")
    require(type(data) is bytes and len(data) == header["size"]
            and (len(data) > 0 or header["final"])
            and header["offset"] + len(data) <= MAX_ARTIFACT, "invalid frame length")
    require(hmac.compare_digest(hashlib.sha256(data).hexdigest(), header["sha256"]),
            "frame digest mismatch")

def pack_frame(job_id, manifest_digest, path, offset, data, final):
    require(type(data) is bytes and len(data) <= CHUNK, "invalid frame data")
    header = {"version":11, "jobId":job_id, "manifestSha256":manifest_digest,
              "path":path, "offset":offset, "size":len(data),
              "sha256":hashlib.sha256(data).hexdigest(), "final":final}
    _validate_frame(header, data)
    raw = canonical(header)
    require(len(raw) <= MAX_FRAME_HEADER, "frame header too large")
    return FRAME_MAGIC + struct.pack(">I", len(raw)) + raw + data

def read_frame(stream):
    require(_read_exact(stream, len(FRAME_MAGIC)) == FRAME_MAGIC, "wrong frame magic")
    size, = struct.unpack(">I", _read_exact(stream, 4))
    require(0 < size <= MAX_FRAME_HEADER, "invalid frame header length")
    raw = _read_exact(stream, size)
    header = parse(raw, limit=MAX_FRAME_HEADER)
    require(type(header) is dict and "size" in header, "invalid header")
    require(raw == canonical(header), "noncanonical header")
    integer(header["size"], 0, CHUNK)
    data = _read_exact(stream, header["size"])
    _validate_frame(header, data)
    return header, data

def file_frame_chunks(stream, job_id, manifest_digest, item, *, require_eof=True):
    """Sequential, exact file framing; one complete file per bounded stream.

    Future transport must independently authenticate, impose IO deadlines,
    and provide a private spool. No automatic resume or execution.
    """
    offset = 0
    while True:
        header, data = read_frame(stream)
        require(header["jobId"] == job_id and header["manifestSha256"] == manifest_digest
                and header["path"] == item["path"] and header["offset"] == offset,
                "frame identity or sequence mismatch")
        offset += len(data)
        require(offset <= item["size"] and header["final"] == (offset == item["size"]),
                "incorrect frame completion")
        if data:
            yield data
        if header["final"]:
            if require_eof:
                require(stream.read(1) == b"", "trailing frame data")
            return


# The provider is constructed only by trusted orchestration, never by a job.
# Use fixed GitHub API routes and TLS; do not inherit proxy configuration.
# Archive redirects are accepted exactly once to an administrator-pinned
# storage hostname, without forwarding the GitHub Authorization header.
API_HOST = "api.github.com"
API_PREFIX = "/repos/" + REPOSITORY
MAX_METADATA = 256 * 1024
MAX_IO_SECONDS = 300
SOCKET_TIMEOUT = 15
HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")

class _DeadlineStream:
    def __init__(self, response, deadline, limit):
        self.response = response
        self.deadline = deadline
        self.remaining = limit

    def read(self, n):
        integer(n, 1, CHUNK)
        require(time.monotonic() < self.deadline, "transfer deadline exceeded")
        # Read an extra byte at the limit so oversize data cannot be mistaken
        # for EOF; never hand out an over-limit chunk.
        data = self.response.read(min(n, self.remaining + 1))
        require(type(data) is bytes and len(data) <= self.remaining, "response oversized")
        require(time.monotonic() < self.deadline, "transfer deadline exceeded")
        self.remaining -= len(data)
        return data

def _redirect_target(location, allowed_hosts):
    require(type(location) is str and 0 < len(location) <= 8192
            and all(33 <= ord(c) < 127 for c in location)
            and "\\" not in location, "invalid archive redirect")
    try:
        url = urlsplit(location)
        require(url.scheme == "https" and url.hostname in allowed_hosts
                and url.netloc == url.hostname and not url.fragment
                and url.path.startswith("/") and not url.path.startswith("//"),
                "archive redirect not allowed")
    except ValueError as exc:
        raise InvalidJob("invalid archive redirect") from exc
    return url.hostname, url.path + ("?" + url.query if url.query else "")

class GitHubProvider:
    """Fixed read-only API provider. Live use requires separate authorization.

    Exact redirect hosts are operator-supplied trusted config (not a wildcard
    or manifest field). Without them artifact download fails closed.
    """
    def __init__(self, token, redirect_hosts=()):
        require(type(token) is str and 16 <= len(token) <= 4096
                and re.fullmatch(r"[A-Za-z0-9_.-]+", token) is not None, "invalid token")
        hosts = frozenset(redirect_hosts)
        require(len(hosts) <= 16 and all(type(h) is str and HOST.fullmatch(h)
                and h != API_HOST and "." in h and not h.endswith(".")
                and not all(c.isdigit() or c == "." for c in h) for h in hosts),
                "invalid trusted storage hosts")
        self._token = token
        self._hosts = hosts

    @contextmanager
    def _response(self, host, path, accept, *, auth):
        require(path.startswith("/") and not path.startswith("//")
                and all(33 <= ord(c) < 127 for c in path), "invalid request target")
        require((auth and host == API_HOST) or (not auth and host in self._hosts),
                "unexpected request destination")
        headers = {"Accept":accept, "User-Agent":"prp-remote-executor-v11",
                   "Accept-Encoding":"identity"}
        if auth:
            headers.update({"Authorization":"Bearer "+self._token,
                            "X-GitHub-Api-Version":"2022-11-28"})
        connection = http.client.HTTPSConnection(host, timeout=SOCKET_TIMEOUT,
                                                 context=ssl.create_default_context())
        response = None
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            yield response
        except (OSError, http.client.HTTPException, ValueError) as exc:
            # Do not propagate URLs, headers, signed redirect or raw errors.
            raise InvalidJob("GitHub response unavailable") from None
        finally:
            if response is not None:
                response.close()
            connection.close()

    @staticmethod
    def _stream(response, limit, deadline):
        require(response.status == 200, "unexpected response status")
        require(response.getheader("Content-Encoding") in (None, "identity"),
                "unsupported content encoding")
        size = response.getheader("Content-Length")
        if size is not None:
            require(size.isascii() and size.isdecimal() and len(size) <= 12
                    and int(size) <= limit, "response oversized")
        return _DeadlineStream(response, deadline, limit)

    def _metadata(self, suffix):
        deadline = time.monotonic() + MAX_IO_SECONDS
        with self._response(API_HOST, API_PREFIX+suffix, "application/vnd.github+json", auth=True) as response:
            stream = self._stream(response, MAX_METADATA, deadline)
            data = bytearray()
            for block in chunks(stream):
                data.extend(block)
            value = parse(bytes(data), limit=MAX_METADATA)
            require(type(value) is dict, "invalid API metadata")
            return value

    def run_metadata(self, run_id):
        integer(run_id, 1, 2**63-1)
        return self._metadata("/actions/runs/"+str(run_id))

    def artifact_metadata(self, artifact_id):
        integer(artifact_id, 1, 2**63-1)
        return self._metadata("/actions/artifacts/"+str(artifact_id))

    @contextmanager
    def repository_file(self, sha, path):
        commit(sha)
        relative_path(path)
        deadline = time.monotonic() + MAX_IO_SECONDS
        route = API_PREFIX+"/contents/"+quote(path,safe="/")+"?ref="+sha
        with self._response(API_HOST, route, "application/vnd.github.raw+json", auth=True) as response:
            yield self._stream(response, MAX_ARTIFACT, deadline)

    @contextmanager
    def artifact_zip(self, artifact_id):
        integer(artifact_id, 1, 2**63-1)
        deadline = time.monotonic() + MAX_IO_SECONDS
        route = API_PREFIX+"/actions/artifacts/"+str(artifact_id)+"/zip"
        with self._response(API_HOST, route, "application/octet-stream", auth=True) as response:
            require(response.status == 302, "expected artifact redirect")
            host, path = _redirect_target(response.getheader("Location"), self._hosts)
        with self._response(host, path, "application/octet-stream", auth=False) as response:
            yield self._stream(response, MAX_ARTIFACT, deadline)

def encode_file_stream(stream, job_id, manifest_digest, item):
    """Generate bounded frames from verified source; retain only one block.

    A receiver must still verify the full file against its immutable manifest.
    No automatic retry; caller handles uncertain transfer outcome.
    """
    offset = 0
    hasher = hashlib.sha256()
    for block in chunks(stream):
        end = offset + len(block)
        require(end <= item["size"], "source oversized")
        hasher.update(block)
        if end == item["size"]:
            require(stream.read(1) == b"" and
                    hmac.compare_digest(hasher.hexdigest(), item["sha256"]),
                    "source digest mismatch")
            yield pack_frame(job_id, manifest_digest, item["path"], offset, block, True)
            return
        yield pack_frame(job_id, manifest_digest, item["path"], offset, block, False)
        offset = end
    require(item["size"] == 0 and hmac.compare_digest(hasher.hexdigest(), item["sha256"]),
            "source incomplete")
    yield pack_frame(job_id, manifest_digest, item["path"], 0, b"", True)

def ssh_receive_argv(host, key_file, known_hosts_file):
    """Pure argv builder, no process launch. Host and files from trusted config.

    A future fixed forced-command gateway authenticates and binds the control
    request before accepting frames. No remote command string from jobs.
    """
    from pathlib import Path
    require(type(host) is str and HOST.fullmatch(host) is not None
            and "." in host and not host.endswith("."), "invalid staging host")
    for path in (key_file, known_hosts_file):
        require(type(path) is str and Path(path).is_absolute()
                and all(33 <= ord(c) < 127 for c in path)
                and "%" not in path, "invalid credential path")
    return ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-p", "22",
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "PasswordAuthentication=no", "-o", "KbdInteractiveAuthentication=no",
            "-o", "StrictHostKeyChecking=yes", "-o", "GlobalKnownHostsFile=/dev/null",
            "-o", "UserKnownHostsFile="+known_hosts_file,
            "-o", "ClearAllForwardings=yes", "-o", "ForwardAgent=no",
            "-o", "ConnectTimeout=15", "-o", "ConnectionAttempts=1",
            "-i", key_file, "prp-remote-v11@"+host, "receive-v11"]


def dispatch_event(event, repository, ref, issue, ledger, provider,
                   recipient_cert, recipient_key, signer_cert, signer_key,
                   approved_producers=frozenset(), now=None):
    """Internal integration adapter, NOT a network service or live entrypoint.

    Only a trusted event source may call this function. Caller must establish
    actual event provenance and independent approval; JSON fields alone are
    not an authentication mechanism. No script launch or stage mutation here.
    """
    t = int(time.time() if now is None else now)
    require(type(issue) is int and issue > 0 and issue != 277,
            "dedicated V1.1 issue required")
    req = decode_comment_request(event, repository, ref, issue,
                                 recipient_cert, recipient_key, t)
    # Claim before any file transfer, query result access or response signing.
    ledger.claim_request(req, event["comment"]["id"], t)
    jid, md = req["jobId"], req["manifestSha256"]
    if req["action"] == "submit":
        transfer_job(req["job"], ledger, provider, approved_producers, t)
    snapshot = ledger.snapshot(jid, md, include_result=req["action"] == "result")
    receipt = {k: req[k] for k in ("version", "target", "action", "requestId",
                                   "jobId", "manifestSha256", "nonce")}
    receipt.update(snapshot)
    receipt["issuedAt"] = int(time.time() if now is None else now)
    encrypted = seal_receipt(receipt, req, signer_cert, signer_key, receipt["issuedAt"])
    encoded = base64.urlsafe_b64encode(encrypted).decode("ascii").rstrip("=")
    require(len(encoded) <= 60000, "encrypted response too large")
    return "/prp-remote-result-v11 " + req["requestId"] + " " + encoded


# Duplex relay: the GitHub-hosted runner has only the dedicated SSH credential
# and read-only artifact access. CMS private keys stay on the staging receiver.
# Only the authenticated SSH channel carries a plaintext external file plan.
CONTROL_MAGIC = b"PRP11C\x00"
MAX_CONTROL = 128 * 1024

def _write_all(stream, data):
    while data:
        count = stream.write(data)
        require(type(count) is int and 0 < count <= len(data), "short relay write")
        data = data[count:]

def write_control(stream, value):
    raw = canonical(value)
    require(0 < len(raw) <= MAX_CONTROL, "oversized relay control")
    _write_all(stream, CONTROL_MAGIC + struct.pack(">I", len(raw)) + raw)
    stream.flush()

def read_control(stream):
    require(_read_exact(stream, len(CONTROL_MAGIC)) == CONTROL_MAGIC, "wrong relay magic")
    size, = struct.unpack(">I", _read_exact(stream, 4))
    require(0 < size <= MAX_CONTROL, "oversized relay control")
    raw = _read_exact(stream, size)
    value = parse(raw, limit=MAX_CONTROL)
    require(type(value) is dict and canonical(value) == raw, "invalid relay control")
    return value

def external_files(manifest):
    # Group artifact members so the runner downloads each archive only once.
    files = []
    groups = {}
    for item in manifest["files"]:
        src = item["source"]
        if src["kind"] == "repository":
            files.append(item)
        elif src["kind"] == "ci_artifact":
            groups.setdefault((src["runId"], src["artifactId"]), []).append(item)
    for members in groups.values():
        files.extend(members)
    return files

def _validate_plan(plan, public_job):
    exact(plan, "version jobId manifestSha256 files")
    require(type(plan["version"]) is int and plan["version"] == 11
            and plan["jobId"] == public_job, "relay plan job mismatch")
    uuid4_text(plan["jobId"])
    digest(plan["manifestSha256"])
    files = plan["files"]
    require(type(files) is list and len(files) <= MAX_FILES, "invalid relay files")
    total = archive_total = 0
    seen = set()
    groups = {}
    for item in files:
        validate_file(item)
        src = item["source"]
        require(src["kind"] in ("repository", "ci_artifact"), "unexpected inline relay")
        key = item["path"].lower()
        require(not any(key == p or key.startswith(p+"/") or p.startswith(key+"/") for p in seen),
                "conflicting relay path")
        seen.add(key)
        total += item["size"]
        if src["kind"] == "ci_artifact":
            identity = (src["runId"], src["artifactId"])
            metadata = {k:v for k,v in src.items() if k != "member"}
            if identity in groups:
                require(groups[identity] == metadata, "conflicting relay artifact")
            else:
                groups[identity] = metadata
                archive_total += src["archiveSize"]
    require(total <= MAX_ARTIFACT and archive_total <= MAX_ARTIFACT, "relay quota exceeded")
    return files

def _send_external(plan, provider, approved_producers, scratch, output):
    jid, md = plan["jobId"], plan["manifestSha256"]
    files = _validate_plan(plan, jid)
    i = 0
    while i < len(files):
        item = files[i]
        src = item["source"]
        if src["kind"] == "repository":
            with provider.repository_file(src["commit"], src["path"]) as stream:
                for frame in encode_file_stream(stream, jid, md, item):
                    _write_all(output, frame)
            i += 1
            continue
        identity = (src["runId"], src["artifactId"])
        verify_producer(src, provider.run_metadata(src["runId"]),
                        provider.artifact_metadata(src["artifactId"]), approved_producers)
        with provider.artifact_zip(src["artifactId"]) as stream:
            with verified_archive(src, stream, scratch) as archive:
                while i < len(files):
                    member_item = files[i]
                    member_src = member_item["source"]
                    if member_src["kind"] != "ci_artifact" or (member_src["runId"], member_src["artifactId"]) != identity:
                        break
                    try:
                        member = archive.getinfo(member_src["member"])
                    except KeyError as exc:
                        raise InvalidJob("missing archive member") from exc
                    require(not member.is_dir() and member.file_size == member_item["size"],
                            "member size mismatch")
                    with archive.open(member, "r") as data:
                        for frame in encode_file_stream(data, jid, md, member_item):
                            _write_all(output, frame)
                    i += 1
    write_control(output, {"done":True, "jobId":jid, "manifestSha256":md})

def relay_receiver(incoming, outgoing, *, issue, ledger, recipient_cert,
                   recipient_key, signer_cert, signer_key, now=None):
    """Server-side session core. Must be invoked ONLY by a trusted restricted
    SSH service after host-local gate and identity checks. Does not launch jobs.
    No GitHub token or artifact downloader is needed on the server.
    """
    t = int(time.time() if now is None else now)
    require(type(issue) is int and issue > 0 and issue != 277, "dedicated issue required")
    control = read_control(incoming)
    exact(control, "event")
    event = control["event"]
    req = decode_comment_request(event, REPOSITORY, "refs/heads/main", issue,
                                 recipient_cert, recipient_key, t)
    ledger.claim_request(req, event["comment"]["id"], t)
    jid, md = req["jobId"], req["manifestSha256"]
    if req["action"] == "submit":
        j = req["job"]
        ledger.accept(j,t)
        for item in j["manifest"]["files"]:
            if item["source"]["kind"] == "inline":
                data = inline_bytes(item["source"])
                ledger.receive_file(jid,md,item["path"],[data] if data else [],t)
        plan = {"version":11,"jobId":jid,"manifestSha256":md,
                "files":external_files(j["manifest"])}
        write_control(outgoing,{"plan":plan})
        for item in plan["files"]:
            ledger.receive_file(jid,md,item["path"],
                                file_frame_chunks(incoming,jid,md,item,require_eof=False),
                                int(time.time() if now is None else now))
        require(read_control(incoming) == {"done":True,"jobId":jid,"manifestSha256":md},
                "relay completion mismatch")
        require(incoming.read(1) == b"", "trailing relay input")
        ledger.verify(jid,md,int(time.time() if now is None else now))
    else:
        # Query sends an empty plan so the runner can terminate input cleanly.
        write_control(outgoing,{"plan":{"version":11,"jobId":jid,
                      "manifestSha256":md,"files":[]}})
        require(read_control(incoming) == {"done":True,"jobId":jid,"manifestSha256":md},
                "relay completion mismatch")
        require(incoming.read(1) == b"", "trailing relay input")
    snapshot = ledger.snapshot(jid,md,include_result=req["action"]=="result")
    receipt = {k:req[k] for k in ("version","target","action","requestId",
                                 "jobId","manifestSha256","nonce")}
    receipt.update(snapshot)
    receipt["issuedAt"] = int(time.time() if now is None else now)
    ciphertext = seal_receipt(receipt,req,signer_cert,signer_key,receipt["issuedAt"])
    encoded = base64.urlsafe_b64encode(ciphertext).decode("ascii").rstrip("=")
    require(len(encoded) <= 60000, "oversized response")
    write_control(outgoing,{"result":"/prp-remote-result-v11 "+req["requestId"]+" "+encoded})

def relay_sender(event, repository, ref, issue, incoming, outgoing, *,
                 close_input, provider, approved_producers, scratch):
    """Runner session core on an authenticated, pinned SSH channel.

    close_input must half-close the transport write side, not close output.
    No automatic retries or plaintext public comments.
    """
    public_job,_ = verify_event(event,repository,ref,issue)
    require(issue != 277, "dedicated issue required")
    write_control(outgoing,{"event":event})
    plan_message = read_control(incoming)
    exact(plan_message,"plan")
    plan = plan_message["plan"]
    _validate_plan(plan,public_job)
    _send_external(plan,provider,approved_producers,scratch,outgoing)
    close_input()
    reply = read_control(incoming)
    exact(reply,"result")
    result = reply["result"]
    require(type(result) is str and len(result) <= MAX_COMMENT, "invalid relay result")
    match = re.fullmatch(r"/prp-remote-result-v11 ([0-9a-f-]{36}) ([A-Za-z0-9_-]{8,60000})",result)
    require(match is not None, "invalid relay result")
    uuid4_text(match.group(1))
    require(incoming.read(1)==b"", "trailing relay response")
    return result


# Candidate SSH process adapter; never activated from the draft workflow.
# The trusted caller must supply staging-only credentials and authorize the
# transport. A separate supervised workflow deadline bounds artifact fetching.
class _Pipe:
    def __init__(self, file, deadline):
        self.file = file
        self.fd = file.fileno()
        self.deadline = deadline
        os.set_blocking(self.fd, False)

    def _remaining(self):
        value = self.deadline - time.monotonic()
        require(value > 0, "SSH deadline exceeded")
        return value

    def read(self, n):
        while True:
            ready, _, _ = select.select([self.fd], [], [], self._remaining())
            require(bool(ready), "SSH read deadline exceeded")
            try:
                return os.read(self.fd, n)
            except BlockingIOError:
                continue

    def write(self, data):
        while True:
            _, ready, _ = select.select([], [self.fd], [], self._remaining())
            require(bool(ready), "SSH write deadline exceeded")
            try:
                return os.write(self.fd, data)
            except BlockingIOError:
                continue

    def flush(self):
        # os.write bypasses Python buffered file objects.
        pass

def _credential(path, value):
    require(type(value) is str and 0 < len(value.encode("utf-8")) <= 16384
            and "\x00" not in value and bool(value.strip()), "missing SSH identity")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write((value if value.endswith("\n") else value+"\n").encode("utf-8"))

def relay_over_ssh(event, repository, ref, issue, *, enabled=False, host=None,
                   private_key=None, known_hosts=None, provider=None,
                   approved_producers=frozenset(), scratch=None, timeout=240):
    """Trusted runner only. No live configuration or general SSH access.

    Pipe IO and SSH wait share one monotonic deadline. Provider network
    operations have their own limits; the outer workflow must independently
    enforce a hard overall deadline. No automatic replay after any failure.
    """
    require(enabled is True, "SSH relay disabled")
    verify_event(event,repository,ref,issue)
    require(issue != 277, "dedicated issue required")
    integer(timeout,1,300)
    deadline = time.monotonic()+timeout
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        key = Path(directory)/"key"
        hosts = Path(directory)/"known_hosts"
        _credential(key,private_key)
        _credential(hosts,known_hosts)
        argv = ssh_receive_argv(host,str(key),str(hosts))
        proc = None
        try:
            proc = subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,bufsize=0,close_fds=True,start_new_session=True,
                cwd="/",env={"PATH":"/usr/bin:/bin","LANG":"C.UTF-8"})
            incoming = _Pipe(proc.stdout,deadline)
            outgoing = _Pipe(proc.stdin,deadline)
            reply = relay_sender(event,repository,ref,issue,incoming,outgoing,
                                  close_input=proc.stdin.close,provider=provider,
                                  approved_producers=approved_producers,scratch=directory)
            require(proc.wait(timeout=incoming._remaining()) == 0, "SSH result uncertain")
            return reply
        except (OSError, subprocess.TimeoutExpired, InvalidJob) as exc:
            raise InvalidJob("SSH relay failed or uncertain") from None
        finally:
            if proc is not None:
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid,signal.SIGKILL)
                        proc.wait(timeout=5)
                    except (OSError,subprocess.TimeoutExpired):
                        pass
                for f in (proc.stdin,proc.stdout):
                    if f is not None:
                        f.close()


def _fixed_config(path, group, max_size, *, secret=False):
    """Read only fixed, administrator-owned files. Never log their contents."""
    from executor import _trusted_path
    try:
        _trusted_path(path, False)
        st = path.stat()
        expected_mode = 0o440 if secret else 0o444
        require(st.st_gid == group and stat.S_IMODE(st.st_mode) == expected_mode
                and 0 < st.st_size <= max_size, "invalid receiver config")
        with path.open("rb") as f:
            data = f.read(max_size+1)
        require(len(data) == st.st_size, "invalid receiver config size")
        return data
    except OSError as exc:
        raise InvalidJob("receiver configuration unavailable") from exc

def receiver_main():
    """Candidate forced-command receiver. Default denied on unconfigured hosts.

    Root must install reviewed code and fixed authorized_keys command with
    restrict/no PTY/no forwarding/no user rc/environment injection. SSH key
    possession is the trusted transport boundary, not independent approval.
    The worker is a separate one-shot process under the dedicated cgroup.
    """
    from executor import (CONFIG_ROOT, LEDGER_ROOT, RECEIVER_GATE, Ledger,
                          host_gate, service_identity)
    require(sys.argv[1:] == ["receive-v11"]
            and os.environ.get("SSH_ORIGINAL_COMMAND") == "receive-v11",
            "unexpected receiver command")
    account = service_identity()
    host_gate(RECEIVER_GATE, b"PRP_STAGING_RECEIVER_V11\n")
    issue_bytes = _fixed_config(CONFIG_ROOT/"issue", account.pw_gid, 20)
    require(re.fullmatch(rb"[1-9][0-9]{0,17}\n?", issue_bytes) is not None,
            "invalid dedicated issue")
    issue = int(issue_bytes)
    require(issue != 277, "production V1 issue prohibited")
    recipient_cert = _fixed_config(CONFIG_ROOT/"recipient.crt", account.pw_gid, 5000)
    recipient_key = _fixed_config(CONFIG_ROOT/"recipient.key", account.pw_gid, 16384, secret=True)
    signer_cert = _fixed_config(CONFIG_ROOT/"signer.crt", account.pw_gid, 5000)
    signer_key = _fixed_config(CONFIG_ROOT/"signer.key", account.pw_gid, 16384, secret=True)
    require(recipient_cert != signer_cert and recipient_key != signer_key,
            "separate recipient and signer identities required")
    deadline = time.monotonic()+240
    relay_receiver(_Pipe(sys.stdin.buffer, deadline), _Pipe(sys.stdout.buffer, deadline),
                   issue=issue, ledger=Ledger(LEDGER_ROOT),
                   recipient_cert=recipient_cert, recipient_key=recipient_key,
                   signer_cert=signer_cert, signer_key=signer_key)

if __name__ == "__main__":
    try:
        receiver_main()
    except Exception:
        print("REMOTE_EXECUTOR_RECEIVER_BLOCKED_OR_UNCERTAIN", file=sys.stderr)
        sys.exit(2)
