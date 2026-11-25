"""Fixed-source Linux metrics collector; disabled unless root marker is present.

No shell, subprocess, network, DB, Docker socket, arbitrary paths or CLI args.
"""
import errno
import fcntl
import grp
import os
import pwd
import stat
import sys
import time
from pathlib import Path

from shared_snapshot import SNAPSHOT_DIRECTORY, WRITER_ACCOUNT, SHARED_GROUP, SharedSnapshotWriter
from snapshot_contract import build_snapshot

PROC_SOURCES = {"stat": "/proc/stat", "meminfo": "/proc/meminfo"}
ROOT_FILESYSTEM = "/"
ENABLE_DIRECTORY = "/etc/matrix-prp-ops"
ENABLE_MARKER = "ENABLE_LIVE_COLLECTION"
RUNTIME_DIRECTORY = "/run/prp-ops-collector"
LOCK_NAME = "collector.lock"
MARKER_CONTENT = b"enabled=1\n"
PROC_LIMITS = {"stat": 512, "meminfo": 65536}

def _open_directory(path):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for part in Path(path).parts[1:]:
            if part in ("", ".", ".."):
                raise OSError(errno.EPERM, "invalid fixed directory")
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.ENOTDIR, "invalid fixed directory")
        return fd
    except BaseException:
        os.close(fd)
        raise

def live_collection_enabled():
    """Require an exact root-owned opt-in marker; absent by default."""
    directory_fd = marker_fd = None
    try:
        directory_fd = _open_directory(ENABLE_DIRECTORY)
        directory = os.fstat(directory_fd)
        if directory.st_uid != 0 or stat.S_IMODE(directory.st_mode) != 0o755:
            return False
        marker_fd = os.open(ENABLE_MARKER, os.O_RDONLY | os.O_NOFOLLOW |
                            os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory_fd)
        info = os.fstat(marker_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or
                stat.S_IMODE(info.st_mode) != 0o644 or info.st_nlink != 1 or
                info.st_size != len(MARKER_CONTENT)):
            return False
        return os.read(marker_fd, len(MARKER_CONTENT) + 1) == MARKER_CONTENT
    except OSError:
        return False
    finally:
        if marker_fd is not None:
            os.close(marker_fd)
        if directory_fd is not None:
            os.close(directory_fd)

def read_fixed_proc(name):
    """Read one allowlisted procfs file with a strict byte ceiling."""
    path = PROC_SOURCES.get(name)
    if path is None:
        raise OSError(errno.EPERM, "source not allowlisted")
    limit = PROC_LIMITS[name]
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, "unexpected proc source")
        chunks = bytearray()
        while len(chunks) <= limit:
            part = os.read(fd, min(4096, limit + 1 - len(chunks)))
            if not part:
                break
            chunks.extend(part)
            if name == "stat" and b"\n" in chunks:
                # Only the aggregate CPU line is required; avoid scaling with CPU count.
                return bytes(chunks.split(b"\n", 1)[0] + b"\n")
        if not chunks or len(chunks) > limit:
            raise OSError(errno.EFBIG, "proc source size invalid")
        return bytes(chunks)
    finally:
        os.close(fd)

def read_root_statvfs():
    """The only filesystem queried is the fixed root filesystem."""
    return os.statvfs(ROOT_FILESYSTEM)

def collect_once(*, proc_reader, disk_reader, sleeper, wall_clock, writer):
    """Dependency-injected one-shot collector; production passes fixed adapters."""
    try:
        cpu_before = proc_reader("stat")
    except OSError:
        cpu_before = None
    sleeper(1)
    try:
        cpu_after = proc_reader("stat")
    except OSError:
        cpu_after = None
    try:
        meminfo = proc_reader("meminfo")
    except OSError:
        meminfo = None
    try:
        disk = disk_reader()
    except OSError:
        disk = None
    snapshot = build_snapshot(
        observed_at=int(wall_clock()),
        cpu_before=cpu_before,
        cpu_after=cpu_after,
        meminfo=meminfo,
        statvfs_fixture=disk,
        http_status=None,
        http_body=b"",
    )
    writer.write(snapshot)
    return snapshot

def acquire_single_writer_lock():
    """Use systemd's private RuntimeDirectory; skip a concurrent invocation."""
    directory_fd = None
    try:
        directory_fd = _open_directory(RUNTIME_DIRECTORY)
        directory = os.fstat(directory_fd)
        uid = os.geteuid()
        if (directory.st_uid != uid or stat.S_IMODE(directory.st_mode) != 0o700):
            raise OSError(errno.EPERM, "runtime directory ownership mismatch")
        fd = os.open(LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW |
                     os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            os.close(fd)
            raise OSError(errno.EPERM, "lock file ownership mismatch")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        return fd
    finally:
        if directory_fd is not None:
            os.close(directory_fd)

def create_writer():
    writer_uid = pwd.getpwnam(WRITER_ACCOUNT).pw_uid
    shared_gid = grp.getgrnam(SHARED_GROUP).gr_gid
    return SharedSnapshotWriter(SNAPSHOT_DIRECTORY, writer_uid, shared_gid)

def main():
    # The service unit has the same condition, but direct execution must fail closed too.
    if not live_collection_enabled():
        return 78
    lock_fd = acquire_single_writer_lock()
    if lock_fd is None:
        return 0
    try:
        collect_once(proc_reader=read_fixed_proc, disk_reader=read_root_statvfs,
                     sleeper=time.sleep, wall_clock=time.time, writer=create_writer())
        return 0
    except Exception:
        sys.stderr.write("PRP ops collection failed; details suppressed.\n")
        return 1
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)

if __name__ == "__main__":
    raise SystemExit(main())
