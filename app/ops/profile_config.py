"""Independent non-production runtime profile. No provisioner or live values."""
import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from query_contract import IdentityProfile, require
from snapshot_contract import strict_json

DIRECTORY=Path("/etc/matrix-prp-ops")
PROFILE_NAME="profile.json"
APPROVAL_NAME="ENABLE_MCP_PROFILE"
PROFILE_LIMIT=2048
KEYS={"version","environment","issuer","resource","subject","introspectionClientId"}
CLIENT_ID="prp-ops-staging-resource"
LABEL=r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DNS=LABEL+r"(?:\."+LABEL+r")+"

@dataclass(frozen=True)
class ApprovedProfile:
    identity: IdentityProfile
    client_id: str
    digest: str

def parse_profile(raw):
    value=strict_json(raw,PROFILE_LIMIT)
    require(type(value) is dict and set(value)==KEYS)
    require(type(value["version"]) is int and value["version"]==1
            and value["environment"]=="staging"
            and value["introspectionClientId"]==CLIENT_ID)
    issuer,resource,subject=(value[k] for k in ("issuer","resource","subject"))
    require(type(issuer) is str and type(resource) is str and type(subject) is str)
    im=re.fullmatch(r"https://("+DNS+r")/realms/prp-ops-staging",issuer, re.ASCII)
    rm=re.fullmatch(r"https://("+DNS+r")/mcp",resource, re.ASCII)
    require(im is not None and rm is not None)
    for host in (im.group(1),rm.group(1)):
        require(len(host)<=253 and not host.endswith((".invalid",".localhost",".local",".test",".example"))
                and re.search(r"[a-z]",host.rsplit(".",1)[-1]) is not None)
    require(im.group(1)!=rm.group(1))
    require(re.fullmatch(r"[A-Za-z0-9_-]{1,128}",subject,re.ASCII) is not None
            and subject!="synthetic-staging-owner")
    return ApprovedProfile(IdentityProfile(issuer,resource,subject),CLIENT_ID,
                           hashlib.sha256(raw).hexdigest())

def read_fixed(fd,name,*,owner,gid,mode,limit):
    source=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
    try:
        info=os.fstat(source)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==owner and info.st_gid==gid
                and stat.S_IMODE(info.st_mode)==mode and info.st_nlink==1
                and 0<info.st_size<=limit)
        with os.fdopen(source,"rb") as stream:
            source=None
            raw=stream.read(limit+1)
        require(len(raw)==info.st_size)
        return raw
    finally:
        if source is not None:
            os.close(source)

def approved_profile(directory=DIRECTORY,*,owner=0,gid=0):
    """Trusted fixture path injection only; service always uses fixed defaults.

    Root-owned ancestry in the deployed path is independently checked. The
    exact approved digest prevents accidental replacement; root compromise or
    restoring both files together is not detected.
    """
    fd=None
    try:
        path=Path(directory)
        require(path.is_absolute() and type(owner) is int and type(gid) is int)
        flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
        fd=os.open("/",flags)
        for part in path.parts[1:]:
            require(part not in ("",".",".."))
            child=os.open(part,flags,dir_fd=fd)
            os.close(fd)
            fd=child
            info=os.fstat(fd)
            if owner==0 and path==DIRECTORY:
                require(info.st_uid==0 and info.st_gid==0 and not info.st_mode&0o022)
        info=os.fstat(fd)
        require(info.st_uid==owner and info.st_gid==gid and stat.S_IMODE(info.st_mode)==0o755)
        marker=read_fixed(fd,APPROVAL_NAME,owner=owner,gid=gid,mode=0o644,limit=128)
        raw=read_fixed(fd,PROFILE_NAME,owner=owner,gid=gid,mode=0o644,limit=PROFILE_LIMIT)
        profile=parse_profile(raw)
        require(marker==("profile-sha256="+profile.digest+"\n").encode("ascii"))
        return profile
    except Exception:
        return None
    finally:
        if fd is not None:
            os.close(fd)
