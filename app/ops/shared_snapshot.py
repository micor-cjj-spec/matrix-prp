"""Separate-UID, shared-group snapshot boundary for the offline ops design.

Production identity values are fixed by the service installer, never by a
request. The test suite injects a temporary directory and synthetic UID/GID.
"""
import os
import stat
from pathlib import Path
from snapshot_contract import MAX_BYTES, encode, query_snapshot, unavailable

SNAPSHOT_DIRECTORY = Path("/var/lib/prp-ops")
WRITER_ACCOUNT = "prp-ops-collector"
READER_ACCOUNT = "prp-ops-mcp"
SHARED_GROUP = "prp-ops-snapshot"
DIRECTORY_MODE = 0o2750
FILE_MODE = 0o640
LOCKED_NAME = "status.json"

class SnapshotAccessDenied(PermissionError):
    pass

def _open_directory(directory, writer_uid, shared_gid):
    path = Path(directory)
    if not path.is_absolute():
        raise SnapshotAccessDenied("snapshot unavailable")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            if part in ("", ".", ".."):
                raise SnapshotAccessDenied("snapshot unavailable")
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != writer_uid or
                info.st_gid != shared_gid or stat.S_IMODE(info.st_mode) != DIRECTORY_MODE):
            raise SnapshotAccessDenied("snapshot unavailable")
        return fd
    except BaseException:
        os.close(fd)
        raise

class SharedSnapshotWriter:
    """Collector-only writer. No read method; never accepts a model path."""
    def __init__(self, directory=SNAPSHOT_DIRECTORY, writer_uid=None, shared_gid=None):
        self.directory = Path(directory)
        self.writer_uid = writer_uid
        self.shared_gid = shared_gid

    def _identity(self):
        if type(self.writer_uid) is not int or type(self.shared_gid) is not int:
            raise SnapshotAccessDenied("snapshot unavailable")
        if os.geteuid() != self.writer_uid:
            raise SnapshotAccessDenied("snapshot unavailable")

    def write(self, value):
        self._identity()
        raw = encode(value)
        fd = _open_directory(self.directory, self.writer_uid, self.shared_gid)
        temporary = None
        try:
            name = ".status-" + os.urandom(16).hex()
            out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                          os.O_NOFOLLOW | os.O_CLOEXEC, FILE_MODE, dir_fd=fd)
            temporary = name
            try:
                os.fchmod(out, FILE_MODE)
                info = os.fstat(out)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.writer_uid or
                        info.st_gid != self.shared_gid or stat.S_IMODE(info.st_mode) != FILE_MODE or
                        info.st_nlink != 1):
                    raise SnapshotAccessDenied("snapshot unavailable")
                with os.fdopen(out, "wb") as stream:
                    out = -1
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                if out >= 0:
                    os.close(out)
            os.replace(temporary, LOCKED_NAME, src_dir_fd=fd, dst_dir_fd=fd)
            temporary = None
            os.fsync(fd)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=fd)
                except FileNotFoundError:
                    pass
            os.close(fd)

class SharedSnapshotReader:
    """Read-only MCP-side projection. Deliberately has no write method."""
    def __init__(self, directory=SNAPSHOT_DIRECTORY, writer_uid=None, shared_gid=None):
        self.directory = Path(directory)
        self.writer_uid = writer_uid
        self.shared_gid = shared_gid

    def _identity(self):
        if type(self.writer_uid) is not int or type(self.shared_gid) is not int:
            raise SnapshotAccessDenied("snapshot unavailable")
        if os.geteuid() == self.writer_uid:
            raise SnapshotAccessDenied("snapshot unavailable")
        groups = set(os.getgroups())
        groups.add(os.getegid())
        if self.shared_gid not in groups:
            raise SnapshotAccessDenied("snapshot unavailable")

    def read_raw(self):
        fd = source = None
        try:
            self._identity()
            fd = _open_directory(self.directory, self.writer_uid, self.shared_gid)
            source = os.open(LOCKED_NAME, os.O_RDONLY | os.O_NOFOLLOW |
                             os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd)
            info = os.fstat(source)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.writer_uid or
                    info.st_gid != self.shared_gid or stat.S_IMODE(info.st_mode) != FILE_MODE or
                    info.st_nlink != 1 or not 0 < info.st_size <= MAX_BYTES):
                return None
            with os.fdopen(source, "rb") as stream:
                source = None
                return stream.read(MAX_BYTES + 1)
        except (OSError, SnapshotAccessDenied, ValueError):
            return None
        finally:
            if source is not None:
                os.close(source)
            if fd is not None:
                os.close(fd)

    def read(self, now):
        return query_snapshot(self.read_raw(), now)
