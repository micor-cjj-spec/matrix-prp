"""Back up and replace only the four explicitly reviewed candidate helpers."""
import hashlib,json,os
from pathlib import Path

ALLOWED={'pinned_transaction_channel.py','disposable_warp_runtime.py',
         'test_pinned_transaction_channel.py','test_disposable_warp_runtime.py'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic(path,raw,mode):
    pending=path.with_name(path.name+'.helper-upgrade-pending')
    fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    try:
        with os.fdopen(fd,'wb') as file:file.write(raw);file.flush();os.fsync(file.fileno())
        os.chmod(pending,mode);os.replace(pending,path)
    finally:
        if pending.exists():pending.unlink()

def restore(root,backup,changes):
    for name,change in changes.items():
        assert sha(backup/name)==change['before']
    records=json.loads((backup/'metadata.private.json').read_text())
    for name,record in records.items():
        assert name in ALLOWED
        target=root/name
        assert not target.is_symlink() and sha(target) in {changes[name]['before'],changes[name]['after']}
        atomic(target,(backup/name).read_bytes(),record['mode'])
        assert sha(target)==changes[name]['before']

def upgrade(root,backup,changes,sources,check):
    root,backup=Path(root),Path(backup)
    assert set(changes)==set(sources)==ALLOWED
    # Parse and hash every proposed byte before backing up or touching a target.
    for name,raw in sources.items():
        assert hashlib.sha256(raw).hexdigest()==changes[name]['after']
        compile(raw,name,'exec')
        target=root/name
        assert not target.is_symlink() and target.is_file()
    if all(sha(root/name)==change['after'] for name,change in changes.items()):
        assert backup.is_dir()
        for name,change in changes.items():assert sha(backup/name)==change['before']
        check()
        return {'already_upgraded':True,'backup_verified':True}
    assert all(sha(root/name)==change['before'] for name,change in changes.items())
    backup.mkdir(mode=0o700)
    records={}
    for name,change in changes.items():
        source=root/name;st=source.stat();raw=source.read_bytes()
        with (backup/name).open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
        (backup/name).chmod(0o600)
        assert sha(backup/name)==change['before']
        records[name]={'mode':st.st_mode&0o777,'uid':st.st_uid,'gid':st.st_gid}
    (backup/'metadata.private.json').write_text(json.dumps(records));(backup/'metadata.private.json').chmod(0o600)
    try:
        for name,raw in sources.items():
            atomic(root/name,raw,records[name]['mode'])
            assert sha(root/name)==changes[name]['after']
        check()
    except BaseException:
        restore(root,backup,changes)
        raise
    return {'already_upgraded':False,'backup_verified':True,'files_changed':4}
