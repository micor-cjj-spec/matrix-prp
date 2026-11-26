"""P3 offline transport adapter. No network requests, SSH, secrets or entrypoint.

A trusted default-branch workflow will supply authenticated metadata and streams
using fixed GitHub API routes. A manifest is not proof of artifact provenance.
"""
from contextlib import contextmanager
import base64
import binascii
import hashlib
import hmac
import re
import stat
import struct
import tempfile
import uuid
import zipfile

from protocol import (REPOSITORY, MAX_ARTIFACT, MAX_FILES, InvalidJob,
                      require, relative_path, validate_job, inline_bytes, canonical, parse,
                      exact, integer, digest, uuid4_text, open_request, MAX_CMS_DER)
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
