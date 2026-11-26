"""P3 transport candidate. No live entrypoint or configured credentials.

A trusted default-branch workflow will supply authenticated metadata and streams
using fixed GitHub API routes. A manifest is not proof of artifact provenance.
"""
from contextlib import contextmanager
import base64
import binascii
import hashlib
import hmac
import http.client
import ssl
import time
from urllib.parse import quote, urlsplit
import re
import stat
import struct
import tempfile
import uuid
import zipfile

from protocol import (REPOSITORY, MAX_ARTIFACT, MAX_FILES, InvalidJob,
                      require, relative_path, validate_job, inline_bytes, canonical, parse,
                      exact, integer, digest, uuid4_text, open_request, MAX_CMS_DER, commit)
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

def file_frame_chunks(stream, job_id, manifest_digest, item):
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
