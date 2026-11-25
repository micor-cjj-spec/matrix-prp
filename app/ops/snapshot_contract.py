"""Offline-only snapshot contract. No live polling, transport, or tool registration."""
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 8192
MAX_INT = (1 << 63) - 1
TTL_SECONDS = 120
FUTURE_TOLERANCE = 5
ENV = "staging"  # Synthetic isolated-instance fixture; never a live target.
KEYS = {"schemaVersion", "environment", "observedAt", "cpu", "memory", "disk", "application"}
UNKNOWN_APP = {"backend": "unknown", "readiness": "unknown"}

class InvalidSnapshot(ValueError):
    pass

def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidSnapshot("duplicate field")
        result[key] = value
    return result

def reject_constant(value):
    raise InvalidSnapshot("invalid number")

def strict_json(raw, limit=MAX_BYTES):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise InvalidSnapshot("invalid size")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=reject_constant)
    except (UnicodeError, ValueError, RecursionError, TypeError):
        raise InvalidSnapshot("invalid JSON") from None

def integer(v):
    return type(v) is int and 0 <= v <= MAX_INT

def percent(v):
    return type(v) in (int, float) and 0 <= v <= 100 and math.isfinite(v)

def utc(epoch):
    if type(epoch) is not int or not 0 <= epoch <= 253402300799:
        raise InvalidSnapshot("invalid time")
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def timestamp(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        raise InvalidSnapshot("invalid time")
    try:
        epoch = int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
        if utc(epoch) != value:
            raise InvalidSnapshot("invalid time")
        return epoch
    except (ValueError, OverflowError, OSError):
        raise InvalidSnapshot("invalid time") from None

def cpu_counters(raw):
    """Only aggregate CPU; guest counters already included in user/nice."""
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise InvalidSnapshot("invalid CPU")
    line = raw.split(b"\n", 1)[0].split()
    if not 9 <= len(line) <= 11 or line[0] != b"cpu":
        raise InvalidSnapshot("invalid CPU")
    fields = line[1:9]
    if any(not re.fullmatch(rb"[0-9]{1,19}", f) for f in fields):
        raise InvalidSnapshot("invalid CPU")
    vals = tuple(map(int, fields))
    if not all(map(integer, vals)):
        raise InvalidSnapshot("invalid CPU")
    return vals

def cpu_usage(before, after):
    try:
        a, b = cpu_counters(before), cpu_counters(after)
        delta = tuple(y-x for x,y in zip(a,b))
        total = sum(delta)
        if min(delta) < 0 or total <= 0:
            return None
        idle = delta[3] + delta[4]
        return {"usagePercent": round(100 * (total-idle)/total, 2)}
    except InvalidSnapshot:
        return None

def memory_usage(raw):
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= 65536:
            return None
        values = {}
        for line in raw.splitlines():
            key = line.partition(b":")[0]
            if key not in (b"MemTotal", b"MemAvailable"):
                continue
            match = re.fullmatch(rb"(MemTotal|MemAvailable):[ \t]+([0-9]{1,19})[ \t]+kB", line)
            if not match or key in values:
                return None
            values[key] = int(match.group(2))*1024
        total, available = values[b"MemTotal"], values[b"MemAvailable"]
        if not integer(total) or not integer(available) or not 0 <= available <= total or total == 0:
            return None
        return {"totalBytes": total, "availableBytes": available,
                "usagePercent": round(100*(total-available)/total, 2)}
    except (KeyError, ValueError):
        return None

def disk_usage(stats):
    """Projection of fixed-root statvfs fixture; no path argument."""
    try:
        size, blocks, free, avail = stats.f_frsize, stats.f_blocks, stats.f_bfree, stats.f_bavail
        if not all(map(integer, (size, blocks, free, avail))) or not size or not blocks or not 0 <= avail <= free <= blocks:
            return None
        total, used, available = size*blocks, size*(blocks-free), size*avail
        if not integer(total):
            return None
        return {"totalBytes": total, "usedBytes": used, "freeBytes": available,
                "usagePercent": round(100*used/total, 2)}
    except (AttributeError, TypeError):
        return None

def application_health(status, body):
    """Only project fixed-source response; does not make HTTP requests."""
    result = dict(UNKNOWN_APP)
    if type(status) is not int:
        return result
    if 500 <= status <= 599:
        result["backend"] = "probe_error"
    if status != 200:
        return result
    try:
        p = strict_json(body, 2048)
        if (type(p) is dict and p.get("code") == "SUCCESS"
                and type(p.get("data")) is dict and p["data"].get("status") == "UP"
                and p["data"].get("service") == "matrix-prp-backend"):
            result["backend"] = "reachable"
    except InvalidSnapshot:
        pass
    return result

def check_metric(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise InvalidSnapshot("invalid metric")
    if not percent(value["usagePercent"]):
        raise InvalidSnapshot("invalid metric")
    for k in keys:
        if k != "usagePercent" and not integer(value[k]):
            raise InvalidSnapshot("invalid metric")

def validate(value):
    if type(value) is not dict or set(value) != KEYS or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1 or value["environment"] != ENV:
        raise InvalidSnapshot("invalid schema")
    timestamp(value["observedAt"])
    cpu, memory, disk, app = (value[k] for k in ("cpu","memory","disk","application"))
    if cpu is not None:
        check_metric(cpu, ("usagePercent",))
    if memory is not None:
        check_metric(memory, ("totalBytes","availableBytes","usagePercent"))
        total, available = memory["totalBytes"], memory["availableBytes"]
        if not total or available > total or memory["usagePercent"] != round(100*(total-available)/total,2):
            raise InvalidSnapshot("invalid memory")
    if disk is not None:
        check_metric(disk, ("totalBytes","usedBytes","freeBytes","usagePercent"))
        total, used, free = disk["totalBytes"], disk["usedBytes"], disk["freeBytes"]
        if not total or used+free > total or disk["usagePercent"] != round(100*used/total,2):
            raise InvalidSnapshot("invalid disk")
    if (type(app) is not dict or set(app) != {"backend","readiness"} or
            app["backend"] not in ("reachable","unknown","probe_error") or app["readiness"] != "unknown"):
        raise InvalidSnapshot("invalid app")
    return value

def encode(value):
    validate(value)
    raw = json.dumps(value, sort_keys=True, separators=(",",":"), allow_nan=False).encode("ascii")
    if len(raw) > MAX_BYTES:
        raise InvalidSnapshot("invalid size")
    return raw

def build_snapshot(*, observed_at, cpu_before, cpu_after, meminfo, statvfs_fixture, http_status, http_body):
    return validate({"schemaVersion": 1, "environment": ENV, "observedAt": utc(observed_at),
                     "cpu": cpu_usage(cpu_before, cpu_after), "memory": memory_usage(meminfo),
                     "disk": disk_usage(statvfs_fixture), "application": application_health(http_status, http_body)})

def unavailable():
    return {"schemaVersion": 1, "environment": ENV, "status": "unavailable",
            "observedAt": None, "ageSeconds": None, "cpu": None, "memory": None, "disk": None,
            "application": dict(UNKNOWN_APP)}

def query_snapshot(raw, now):
    """Pure read projection. Stale data never returned as current metrics."""
    try:
        utc(now)
        data = validate(strict_json(raw))
        age = now - timestamp(data["observedAt"])
        if age < -FUTURE_TOLERANCE:
            return unavailable()
        age = max(0, age)
        if age >= TTL_SECONDS:
            return dict(unavailable(), status="stale", observedAt=data["observedAt"], ageSeconds=age)
        return dict(data, status="fresh", ageSeconds=age)
    except (InvalidSnapshot, ValueError, TypeError, OverflowError, OSError):
        return unavailable()

class SnapshotStore:
    """Synthetic POSIX file boundary; caller supplies trusted fixture directory.

    Same-UID 0700/0600 for offline tests only. Production writer/reader
    accounts and read-only mount require separate approval and validation.
    No automatic directory creation, arbitrary user path, or live scheduling.
    """
    NAME = "status.json"
    def __init__(self, directory):
        self.directory = Path(directory)
        if not self.directory.is_absolute():
            raise InvalidSnapshot("invalid directory")

    def _directory_fd(self):
        # Traverse each ancestor via directory FD without following symlinks.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open("/", flags)
        try:
            for part in self.directory.parts[1:]:
                if part in (".", ".."):
                    raise InvalidSnapshot("invalid directory")
                next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise InvalidSnapshot("invalid directory")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def write(self, value):
        raw = encode(value)
        fd = self._directory_fd()
        tmp = None
        try:
            # Exclusive same-directory temp; no predictable file replacement.
            candidate = ".status-" + os.urandom(16).hex()
            out = os.open(candidate, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600, dir_fd=fd)
            tmp = candidate  # Only unlink a file created by this invocation.
            with os.fdopen(out, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.NAME, src_dir_fd=fd, dst_dir_fd=fd)
            tmp = None
            os.fsync(fd)
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp, dir_fd=fd)
                except FileNotFoundError:
                    pass
            os.close(fd)

    def read(self, now):
        fd = source = None
        try:
            fd = self._directory_fd()
            source = os.open(self.NAME, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=fd)
            info = os.fstat(source)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or
                    not 0 < info.st_size <= MAX_BYTES):
                return unavailable()
            with os.fdopen(source, "rb") as f:
                source = None
                return query_snapshot(f.read(MAX_BYTES+1), now)
        except (OSError, InvalidSnapshot, ValueError):
            return unavailable()
        finally:
            if source is not None:
                os.close(source)
            if fd is not None:
                os.close(fd)
