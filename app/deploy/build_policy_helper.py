"""Deterministically bundle the existing diagnostic plus the reviewed live collector."""
from pathlib import Path
import ast,hashlib,sys

def bundle():
    root=Path(__file__).parent
    legacy=(root/'read_only_diagnostic.py').read_text(encoding='utf-8')
    anchor='if __name__ == "__main__":\n    raise SystemExit(main())'
    if legacy.count(anchor)!=1:raise ValueError('Legacy diagnostic entry changed; review required')
    source=legacy.replace(anchor,'# Legacy log classifier retained; policy entry point is below.')+'\n'+(root/'live_policy_attestor.py').read_text(encoding='utf-8')
    ast.parse(source)
    return source.encode()

if __name__=='__main__':
    data=bundle();Path(sys.argv[1]).write_bytes(data)
    print('Candidate helper SHA256:',hashlib.sha256(data).hexdigest())
