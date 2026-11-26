"""Offline V1.1 job contract. No network, process execution or live credentials."""
import base64
import binascii
import hashlib
import hmac
import json
import re
import time
import uuid

TARGET = "prp-staging"
REPOSITORY = "micor-cjj-spec/matrix-prp"
MAX_INLINE = 8 * 1024
MAX_ARTIFACT = 512 * 1024 * 1024
MAX_FILES = 32
MAX_ENVELOPE = 32 * 1024
OPERATIONS = {"sandbox.bash", "sandbox.python", "stage.health", "artifact.inspect"}
HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")

class InvalidJob(ValueError):
    pass

def require(condition, reason):
    if not condition:
        raise InvalidJob(reason)

def exact(obj, keys):
    require(type(obj) is dict and set(obj) == set(keys.split()), "invalid fields")

def integer(value, lower, upper):
    require(type(value) is int and lower <= value <= upper, "integer out of bounds")

def matches(pattern, value):
    return type(value) is str and pattern.fullmatch(value) is not None

def relative_path(value):
    require(type(value) is str and 0 < len(value) <= 240, "invalid path")
    parts = value.split("/")
    require(len(parts) <= 12 and all(matches(PART, x) and not x.endswith(".") for x in parts), "unsafe path")
    return value

def digest(value):
    require(matches(HEX64, value), "invalid sha256")

def commit(value):
    require(matches(HEX40, value), "invalid commit")

def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("ascii")
    except (ValueError, TypeError, RecursionError) as exc:
        raise InvalidJob("invalid canonical JSON") from exc

def parse(raw):
    require(type(raw) is bytes and len(raw) <= MAX_ENVELOPE, "invalid envelope size")
    def pairs(items):
        out = {}
        for k, v in items:
            require(k not in out, "duplicate field")
            out[k] = v
        return out
    def invalid_constant(_):
        raise InvalidJob("nonfinite number")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidJob("invalid JSON") from exc

def inline_bytes(source):
    data = source["data"]
    require(type(data) is str and len(data) <= 4 * ((MAX_INLINE + 2) // 3), "inline too large")
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidJob("invalid base64") from exc
    require(base64.b64encode(raw).decode("ascii") == data and len(raw) <= MAX_INLINE,
            "noncanonical or oversized inline")
    return raw

def verify_bytes(file, raw):
    require(type(raw) is bytes and len(raw) == file["size"], "size mismatch")
    require(hmac.compare_digest(hashlib.sha256(raw).hexdigest(), file["sha256"]), "digest mismatch")

def validate_file(file):
    exact(file, "path size sha256 source")
    relative_path(file["path"])
    integer(file["size"], 0, MAX_ARTIFACT)
    digest(file["sha256"])
    src = file["source"]
    require(type(src) is dict, "invalid source")
    kind = src.get("kind")
    if kind == "inline":
        exact(src, "kind data")
        verify_bytes(file, inline_bytes(src))
        return file["size"]
    if kind == "repository":
        exact(src, "kind repository commit path")
        require(src["repository"] == REPOSITORY, "wrong repository")
        commit(src["commit"])
        relative_path(src["path"])
    elif kind == "ci_artifact":
        exact(src, "kind repository commit workflow runId artifactId name archiveSize archiveSha256 member")
        require(src["repository"] == REPOSITORY, "wrong repository")
        commit(src["commit"])
        workflow = relative_path(src["workflow"])
        require("/" not in workflow and workflow.endswith((".yml", ".yaml")), "invalid workflow filename")
        integer(src["runId"], 1, 2**63 - 1)
        integer(src["artifactId"], 1, 2**63 - 1)
        require(matches(PART, src["name"]), "invalid artifact name")
        integer(src["archiveSize"], 1, MAX_ARTIFACT)
        digest(src["archiveSha256"])
        relative_path(src["member"])
    else:
        raise InvalidJob("unsupported source")
    return 0

def validate_manifest(manifest):
    exact(manifest, "target operation files entrypoint args timeoutSeconds")
    require(manifest["target"] == TARGET, "wrong target")
    op = manifest["operation"]
    require(type(op) is str and op in OPERATIONS, "unsupported operation")
    integer(manifest["timeoutSeconds"], 1, 120)
    args = manifest["args"]
    require(type(args) is list and len(args) <= 16, "invalid args")
    require(all(type(x) is str and len(x.encode("utf-8", "surrogatepass")) <= 256
                and all(32 <= ord(c) < 127 for c in x) for x in args), "invalid arg")
    files = manifest["files"]
    require(type(files) is list and len(files) <= MAX_FILES, "too many files")
    paths = set()
    total = inline = archive_total = 0
    archives = {}
    for file in files:
        inline += validate_file(file)
        total += file["size"]
        path = file["path"].lower()
        require(not any(path == p or path.startswith(p + "/") or p.startswith(path + "/") for p in paths),
                "conflicting file path")
        paths.add(path)
        src = file["source"]
        if src["kind"] == "ci_artifact":
            identity = (src["runId"], src["artifactId"])
            metadata = {k: v for k, v in src.items() if k != "member"}
            if identity in archives:
                require(archives[identity] == metadata, "conflicting artifact identity")
            else:
                archives[identity] = metadata
                archive_total += src["archiveSize"]
    require(total <= MAX_ARTIFACT and archive_total <= MAX_ARTIFACT and inline <= MAX_INLINE, "aggregate size exceeded")
    entry = manifest["entrypoint"]
    if op.startswith("sandbox."):
        relative_path(entry)
        require(any(f["path"] == entry for f in files), "missing entrypoint")
        require(entry.endswith(".sh" if op == "sandbox.bash" else ".py"), "interpreter mismatch")
    else:
        require(entry is None and args == [], "fixed operation takes no caller arguments")
        if op == "stage.health":
            require(files == [], "health takes no files")
        elif op == "artifact.inspect":
            require(bool(files), "missing artifact")
    require(len(canonical(manifest)) <= MAX_ENVELOPE, "manifest oversized")
    return manifest

def manifest_sha256(manifest):
    return hashlib.sha256(canonical(validate_manifest(manifest))).hexdigest()

def validate_job(job, now=None):
    exact(job, "version jobId nonce issuedAt expiresAt manifest manifestSha256")
    require(type(job["version"]) is int and job["version"] == 11, "wrong version")
    try:
        require(type(job["jobId"]) is str and str(uuid.UUID(job["jobId"])) == job["jobId"]
                and uuid.UUID(job["jobId"]).version == 4, "invalid job ID")
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidJob("invalid job ID") from exc
    require(matches(re.compile(r"[0-9a-f]{32}"), job["nonce"]), "invalid nonce")
    t = int(time.time() if now is None else now)
    integer(job["issuedAt"], t - 300, t + 15)
    integer(job["expiresAt"], t + 1, job["issuedAt"] + 300)
    digest(job["manifestSha256"])
    require(hmac.compare_digest(manifest_sha256(job["manifest"]), job["manifestSha256"]), "manifest mismatch")
    require(len(canonical(job)) <= MAX_ENVELOPE, "job oversized")
    return job

# Source metadata is declarative, not evidence of successful CI or authorized
# origin. A later trusted bridge must independently resolve and verify it.
# This module has no execution, transfer, approval or authentication authority.
