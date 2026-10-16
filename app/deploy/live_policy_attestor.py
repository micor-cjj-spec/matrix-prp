"""Linux/OpenSSH policy collector, bundled into the existing root diagnose helper.

No network calls, caller-selected paths, environment-based session evidence or
production writes. Unsupported layouts fail closed. Root/OS compromise is outside
this trust model; the client must separately approve the installed helper hash.
"""
import base64
from datetime import datetime, timezone
import glob
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import selectors
import shlex
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

GATEWAY = "/usr/local/bin/prp-deploy-gateway"
HELPER = "/usr/local/sbin/prp-diagnose"
SESSION = "/usr/lib/openssh/sshd-session"
SSHD = "/usr/sbin/sshd"
KEYFILE = "/home/prp-deploy/.ssh/authorized_keys"
SUBSYSTEM = "/usr/lib/openssh/sftp-server"
SAFE_FAILURES={'SSH_LOADED_POLICY_UNPROVEN','SSH_AUTHENTICATION_UNPROVEN','SSH_IDENTITY_UNPROVEN',
               'SSH_POLICY_CHANGED_DURING_PROOF','SSH_MATCH_POLICY_UNSUPPORTED','SSH_CLOCK_GENERATION_UNPROVEN',
               'SSH_DAEMON_OPTIONS_UNSUPPORTED','SSH_BINARY_DRIFT','SSH_VERSION_UNREVIEWED',
               'SSH_EFFECTIVE_POLICY_UNSUPPORTED','POLICY_PATH_UNTRUSTED','POLICY_FILE_UNTRUSTED',
               'SSH_KEY_POLICY_UNSUPPORTED','SSH_AUTHORIZATION_SOURCE_UNSUPPORTED','CHALLENGE_INVALID',
               'CHALLENGE_TIMEOUT','POLICY_TOTAL_TIMEOUT'}


class CollectionError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise CollectionError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def bounded_command(args, seconds=2, limit=524288, stderr_output=False):
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    buffers = [bytearray(), bytearray()]
    deadline = time.monotonic() + seconds
    try:
        with selectors.DefaultSelector() as selector:
            for stream, buf in zip([process.stdout, process.stderr], buffers):
                selector.register(stream, selectors.EVENT_READ, buf)
            while selector.get_map():
                require(time.monotonic() < deadline, "POLICY_COMMAND_TIMEOUT")
                for event, _ in selector.select(0.05):
                    buf = event.data
                    chunk = os.read(event.fd, min(4096, limit + 1 - len(buf)))
                    if not chunk:
                        selector.unregister(event.fileobj)
                    buf.extend(chunk)
                    require(len(buf) <= limit, "POLICY_COMMAND_OUTPUT_LIMIT")
        require(process.wait(timeout=max(.001, deadline-time.monotonic())) == 0, "POLICY_COMMAND_FAILED")
        if stderr_output:
            require(not buffers[0],"POLICY_COMMAND_UNEXPECTED_OUTPUT")
        return bytes(buffers[1] if stderr_output else buffers[0])
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=1)
        process.stdout.close(); process.stderr.close()


def bounded_file(path, limit=10485760):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "POLICY_FILE_INVALID")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        require(len(data) <= limit and (before.st_ino,before.st_ctime_ns,before.st_size) ==
                (after.st_ino,after.st_ctime_ns,after.st_size), "POLICY_FILE_CHANGED")
    return data


def trusted_record(path, missing=False):
    p = Path(path)
    require(p.is_absolute(), "POLICY_PATH_INVALID")
    parents = []
    for parent in reversed(p.parents):
        st = parent.lstat()
        require(st.st_uid == 0, "POLICY_PATH_UNTRUSTED")
        # Debian merged-/usr links are permitted only when both link and target are root controlled.
        if stat.S_ISLNK(st.st_mode):
            trusted_record(str(parent.resolve(strict=True)))
        else:
            require(not st.st_mode & 0o022,"POLICY_PATH_UNTRUSTED")
        parents.append([str(parent),st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode),os.readlink(parent) if parent.is_symlink() else None,st.st_ctime_ns if parent.is_symlink() else None])
    try:
        st = p.lstat()
    except FileNotFoundError:
        require(missing, "POLICY_FILE_MISSING")
        return {"path":str(p),"missing":True,"parents":parents}
    require(st.st_uid == 0, "POLICY_FILE_UNTRUSTED")
    if stat.S_ISLNK(st.st_mode):
        target = p.resolve(strict=True)
        return {"path":str(p),"link":str(target),"uid":st.st_uid,"gid":st.st_gid,"ctime":st.st_ctime_ns,"parents":parents,"target":trusted_record(str(target))}
    require(not st.st_mode & 0o022,"POLICY_FILE_UNTRUSTED")
    require(stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode), "POLICY_FILE_INVALID")
    return {"path":str(p),"uid":st.st_uid,"gid":st.st_gid,"mode":stat.S_IMODE(st.st_mode),
            "mtime":st.st_mtime_ns,"ctime":st.st_ctime_ns,"size":st.st_size,
            "sha256":sha(bounded_file(p)) if stat.S_ISREG(st.st_mode) else None,"parents":parents}


def process_info(pid):
    base = Path('/proc') / str(pid)
    fields = (base/'stat').read_text().rsplit(')',1)[1].split()
    status = dict(line.split(':',1) for line in (base/'status').read_text().splitlines() if ':' in line)
    return {"pid":pid,"parent":int(fields[1]),"start_ticks":int(fields[19]),
            "uids":tuple(map(int,status['Uid'].split())),"exe":str((base/'exe').resolve(strict=True))}


def process_birth(process):
    boot = time.time() - time.clock_gettime(time.CLOCK_BOOTTIME)
    return boot + process['start_ticks'] / os.sysconf('SC_CLK_TCK')


def daemon_birth(process):
    # Use systemd's saved realtime timestamp, not only today's wall/boot offset.
    # A clock discontinuity cannot silently make a newer config look pre-start.
    raw=bounded_command(['/usr/bin/busctl','get-property','org.freedesktop.systemd1',
                         '/org/freedesktop/systemd1/unit/ssh_2eservice',
                         'org.freedesktop.systemd1.Service','ExecMainStartTimestamp']).decode().strip()
    require(re.fullmatch(r't [0-9]+',raw) is not None,'SSH_START_TIME_UNPROVEN')
    saved=int(raw.split()[1])/1e6;estimated=process_birth(process)
    require(abs(saved-estimated)<.1,'SSH_CLOCK_GENERATION_UNPROVEN')
    return min(saved,estimated)-.02


def decode_address(value, ipv6):
    address,port = value.split(':')
    raw = bytes.fromhex(address)[::-1] if not ipv6 else b''.join(bytes.fromhex(address[i:i+8])[::-1] for i in range(0,32,8))
    ip = ipaddress.ip_address(raw)
    if isinstance(ip,ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return str(ip),int(port,16)


def connection(chain):
    inodes = set()
    for process in chain:
        for fd in (Path('/proc')/str(process['pid'])/'fd').iterdir():
            try:
                match = re.fullmatch(r'socket:\[(\d+)\]',os.readlink(fd))
                if match:inodes.add(match[1])
            except FileNotFoundError:
                continue
    matches = set()
    for name,ipv6 in [('tcp',False),('tcp6',True)]:
        for line in (Path('/proc/net')/name).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == '01' and fields[9] in inodes:
                local,lport = decode_address(fields[1],ipv6);peer,pport = decode_address(fields[2],ipv6)
                matches.add((local,lport,peer,pport))
    require(len(matches)==1,"SSH_CONNECTION_AMBIGUOUS")
    return next(iter(matches))


def deployment_key(data):
    lines = [line.strip() for line in data.decode('ascii').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    require(len(lines)==1,"SSH_KEY_POLICY_UNSUPPORTED")
    pattern = r'restrict,command="'+re.escape(GATEWAY)+r'" ssh-ed25519 ([A-Za-z0-9+/]+={0,2})(?: [^\r\n]*)?'
    match = re.fullmatch(pattern,lines[0]);require(match is not None,"SSH_KEY_POLICY_UNSUPPORTED")
    blob = base64.b64decode(match[1],validate=True)
    require(len(blob)==51 and blob[:19]==struct.pack('>I',11)+b'ssh-ed25519'+struct.pack('>I',32),"SSH_KEY_POLICY_UNSUPPORTED")
    return 'SHA256:'+base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')


def journal_binds(entries,chain,endpoint,fingerprint,boot_id,now):
    by_pid = {p['pid']:p for p in chain if p['exe']==SESSION}
    accepted = []
    pattern = r'Accepted publickey for prp-deploy from (\S+) port (\d+) ssh2: ED25519 (SHA256:[A-Za-z0-9+/]{43})'
    for entry in entries:
        if not isinstance(entry,dict):continue
        if entry.get('_UID')!='0' or entry.get('_EXE')!=SESSION or entry.get('_BOOT_ID')!=boot_id:continue
        if entry.get('_SYSTEMD_UNIT')!='ssh.service':continue
        try:
            pid = int(entry['_PID']);stamp = int(entry['__REALTIME_TIMESTAMP'])/1e6
            match = re.fullmatch(pattern,entry.get('MESSAGE',''))
            if pid not in by_pid or not match:continue
            if (str(ipaddress.ip_address(match[1])),int(match[2])) != endpoint[2:]:continue
            if match[3]!=fingerprint or not process_birth(by_pid[pid])-1 <= stamp <= now+1:continue
            accepted.append(pid)
        except (ValueError,KeyError,TypeError):continue
    require(len(set(accepted))==1,"SSH_AUTHENTICATION_UNPROVEN")
    return by_pid[accepted[0]]


def configuration_files():
    files = set();directories = set()
    def walk(path,depth=0):
        require(depth<=4 and len(files)<32,"SSH_CONFIG_LIMIT")
        p = Path(path);require(str(p).startswith('/etc/ssh/') and not p.is_symlink(),"SSH_CONFIG_UNSUPPORTED")
        if p in files:return
        files.add(p);directories.add(p.parent)
        for line in bounded_file(p,65536).decode('utf-8').splitlines():
            tokens = shlex.split(line,comments=True)
            if not tokens:continue
            # A conservative first version supports global policy only. Match requires another reviewed collector.
            require(tokens[0].lower()!='match',"SSH_MATCH_POLICY_UNSUPPORTED")
            if tokens[0].lower()=='include':
                for pattern in tokens[1:]:
                    if not pattern.startswith('/'):pattern='/etc/ssh/'+pattern
                    require(pattern.startswith('/etc/ssh/') and '..' not in Path(pattern).parts,"SSH_CONFIG_UNSUPPORTED")
                    directories.add(Path(pattern).parent)
                    for include in sorted(glob.glob(pattern)):walk(include,depth+1)
    walk('/etc/ssh/sshd_config')
    return sorted(files),sorted(directories)


def loaded_configuration(records,daemon_birth):
    # ctime cannot be restored by the unprivileged deployment account. No reload is performed.
    verified=bool(records) and all(not r.get('missing') and r.get('ctime',float('inf'))/1e9 + .02 < daemon_birth for r in records)
    require(verified,"SSH_LOADED_POLICY_UNPROVEN")
    return verified


def record_is_trusted(record):
    parents=all(p[1]==0 and (p[4] is not None or not p[3]&0o022) for p in record.get('parents',[]))
    if record.get('missing'):return parents
    if 'target' in record:return parents and record_is_trusted(record['target'])
    return parents and record.get('uid')==0 and not record.get('mode',0o777)&0o022


def collect_policy(challenge):
    require(os.geteuid()==0 and len(challenge)==32,"POLICY_CALL_INVALID")
    started=time.monotonic(); records={}
    def record(path,missing=False):
        value=trusted_record(path,missing);records[str(path)]=value;return value
    master_pid=int(bounded_command(['/usr/bin/systemctl','show','ssh.service','-p','MainPID','--value']).strip())
    master=process_info(master_pid);require(master['exe']==SSHD and master['uids'][1]==0,"SSH_DAEMON_UNPROVEN")
    version=bounded_command([SSHD,'-V'],stderr_output=True)
    require(re.match(rb'OpenSSH_10\.0p2(?:[ ,]|$)',version) is not None,"SSH_VERSION_UNREVIEWED")
    title=(Path('/proc')/str(master_pid)/'cmdline').read_bytes().replace(b'\0',b' ').decode().strip()
    require(re.fullmatch(r'sshd: /usr/sbin/sshd -D \[listener\](?: [0-9]+ of [0-9]+-[0-9]+ startups)?',title) is not None,"SSH_DAEMON_OPTIONS_UNSUPPORTED")
    for process in [master]:
        require(os.stat('/proc/'+str(process['pid'])+'/exe').st_ino==os.stat(process['exe']).st_ino,"SSH_BINARY_DRIFT")
    chain=[];pid=os.getpid()
    for _ in range(24):
        if pid==master_pid:break
        require(pid>1,"SSH_ANCESTRY_UNPROVEN")
        info=process_info(pid);chain.append(info);pid=info['parent']
    require(pid==master_pid,"SSH_ANCESTRY_UNPROVEN")
    account=pwd.getpwnam('prp-deploy')
    require(account.pw_shell=='/bin/sh' and any(p['uids'][0]==account.pw_uid for p in chain),"SSH_IDENTITY_UNPROVEN")
    sessions=[p for p in chain if p['exe']==SESSION];require(sessions,"SSH_ANCESTRY_UNPROVEN")
    for p in sessions:
        require(os.stat('/proc/'+str(p['pid'])+'/exe').st_ino==os.stat(SESSION).st_ino,"SSH_BINARY_DRIFT")
    endpoint=connection(sessions)
    key_record=record(KEYFILE);fingerprint=deployment_key(bounded_file(KEYFILE,16384))
    alternate=record('/home/prp-deploy/.ssh/authorized_keys2',missing=True)
    require(alternate.get('missing') is True,"SSH_AUTHORIZATION_SOURCE_UNSUPPORTED")
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    journal=bounded_command(['/usr/bin/journalctl','-u','ssh.service','-n','96','-o','json','--no-pager',
                             '--output-fields=_UID,_EXE,_PID,_BOOT_ID,_SYSTEMD_UNIT,__REALTIME_TIMESTAMP,MESSAGE'])
    entries=[json.loads(line) for line in journal.splitlines()]
    auth=journal_binds(entries,chain,endpoint,fingerprint,boot_id,time.time())
    require(key_record['ctime']/1e9 < process_birth(auth),"SSH_KEY_CHANGED_AFTER_AUTHENTICATION")
    files,directories=configuration_files()
    config_records=[record(str(p)) for p in [*files,*directories]]
    loaded=loaded_configuration(config_records,daemon_birth(master))
    args=['/usr/sbin/sshd','-T','-C','user=prp-deploy,host='+endpoint[2]+',addr='+endpoint[2]+',laddr='+endpoint[0]+',lport='+str(endpoint[1])]
    output=bounded_command(args).decode('utf-8')
    effective={}
    for line in output.splitlines():
        name,value=line.split(' ',1)
        effective.setdefault(name,[]).append(value)
    required={'pubkeyauthentication':'yes','strictmodes':'yes','usedns':'no','permituserenvironment':'no',
              'authorizedkeyscommand':'none','trustedusercakeys':'none','authorizedprincipalsfile':'none',
              'authorizedkeysfile':'.ssh/authorized_keys .ssh/authorized_keys2','forcecommand':'none',
              'subsystem':'sftp '+SUBSYSTEM,'permituserrc':'yes','chrootdirectory':'none'}
    require(all(effective.get(k)==[v] for k,v in required.items()),"SSH_EFFECTIVE_POLICY_UNSUPPORTED")
    # restrict on the sole authenticated key disables user rc, forwarding, agent, X11 and PTY.
    for path in [GATEWAY,HELPER,SSHD,SESSION,SUBSYSTEM,'/usr/bin/python3','/bin/sh','/usr/bin/sudo','/usr/bin/journalctl','/usr/bin/systemctl','/usr/bin/busctl','/etc/passwd','/etc/group','/etc/nsswitch.conf','/etc/sudoers','/etc/sudoers.d','/home/prp-deploy/.ssh']:
        record(path)
    for path in sorted(Path('/etc/sudoers.d').iterdir()):record(str(path))
    record('/etc/ssh/sshrc',missing=True)
    require(records['/etc/ssh/sshrc'].get('missing') is True,"SSH_SYSTEM_RC_UNSUPPORTED")
    # Validate both names and trusted targets for merged-/usr symlinks.
    for module in tuple(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_absolute() and Path(path).is_file():record(str(Path(path).resolve()))
    for path,value in records.items():
        require(trusted_record(path,missing=value.get('missing',False))==value,"SSH_POLICY_CHANGED_DURING_PROOF")
    require(process_info(master_pid)==master and process_info(auth['pid'])==auth,"SSH_DAEMON_GENERATION_CHANGED")
    require(int(bounded_command(['/usr/bin/systemctl','show','ssh.service','-p','MainPID','--value']).strip())==master_pid,'SSH_DAEMON_GENERATION_CHANGED')
    require(time.monotonic()-started<7,"POLICY_TOTAL_TIMEOUT")
    return {'schema_version':1,'challenge':challenge.hex(),'observed_utc':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            'baseline':{'gateway_sha256':records[GATEWAY]['sha256'],'authorized_keys_sha256':key_record['sha256'],
                        'effective_sshd_sha256':sha(canonical(effective)),'policy_files_sha256':sha(canonical(records)),
                        'attestor_sha256':records[HELPER]['sha256'],'deployment_key_fingerprint':fingerprint,
                        'subsystem_command':SUBSYSTEM,'forced_command':GATEWAY,'behavior':'openssh-10.0-subsystem-stderr-ignore'},
            'connection_bound':auth['pid'] in {p['pid'] for p in sessions},'loaded_policy_verified':loaded,
            'trusted_paths':all(record_is_trusted(value) for value in records.values())}


def read_challenge(fd=0,seconds=1):
    data=bytearray();deadline=time.monotonic()+seconds
    with selectors.DefaultSelector() as selector:
        try:selector.register(fd,selectors.EVENT_READ)
        except PermissionError:
            require(stat.S_ISCHR(os.fstat(fd).st_mode),'CHALLENGE_INPUT_UNSUPPORTED')
            require(os.read(fd,1)==b'','CHALLENGE_INPUT_UNSUPPORTED');return b''
        while True:
            require(time.monotonic()<deadline,'CHALLENGE_TIMEOUT')
            if not selector.select(min(.05,max(0,deadline-time.monotonic()))):continue
            block=os.read(fd,33-len(data))
            if not block:break
            data.extend(block);require(len(data)<=32,'CHALLENGE_INVALID')
    require(len(data) in (0,32),'CHALLENGE_INVALID')
    return bytes(data)


def policy_main():
    if len(sys.argv)!=1 or os.geteuid()!=0:return 2
    def deadline(*unused):raise CollectionError('POLICY_TOTAL_TIMEOUT')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(9)
    try:
        challenge=read_challenge()
        result=report()
        if challenge:result['ssh_policy']=collect_policy(challenge)
        print(json.dumps(result,ensure_ascii=True,separators=(',',':')))
        return 0
    except Exception as error:
        # No raw exception, environment, journal message, peer address or config reaches stdout/stderr.
        code=error.args[0] if isinstance(error,CollectionError) and error.args and error.args[0] in SAFE_FAILURES else 'SSH_POLICY_UNVERIFIED'
        print(json.dumps({'schema_version':1,'policy_error':code},separators=(',',':')))
        return 2
    finally:signal.alarm(0)


if __name__=='__main__':
    raise SystemExit(policy_main())
