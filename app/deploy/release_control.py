"""A checked-in hold adds a gate; only deleting it restores ordinary publication."""
import json
import os
from pathlib import Path


def publication_allowed(root):
    path = root/'app/deploy/publication-hold.json'
    if not path.exists() and not path.is_symlink(): return True
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError('Invalid publication hold')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data,dict) or set(data)!={'schema_version','reason'}
            or type(data['schema_version']) is not int or data['schema_version']!=1
            or not isinstance(data['reason'],str) or not 1<=len(data['reason'])<=200):
        raise ValueError('Invalid publication hold schema')
    return False


def publication_summary(allowed):
    """Explain gate outcomes without implying a deployment has happened."""
    if allowed:
        return (
            "### PRP production publication gate: ALLOWED (not yet deployed)\n\n"
            "The checked-in publication hold does not block this candidate. "
            "A successful build, protected production approval, and a successful "
            "publish job are still required before claiming a release.\n"
        )
    return (
        "### PRP production publication gate: HELD — NOT DEPLOYED\n\n"
        "The checked-in `app/deploy/publication-hold.json` blocks normal "
        "application publication. A green release-control job means the hold "
        "was checked, **not** that a new version was deployed. "
        "Explicit read-only production checks remain separate.\n"
    )


if __name__=='__main__':
    allowed=publication_allowed(Path(__file__).resolve().parents[2])
    with Path(os.environ['GITHUB_OUTPUT']).open('a',encoding='utf-8') as stream:
        stream.write('publish_allowed='+str(allowed).lower()+'\n')
    print('Ordinary publication enabled' if allowed else 'Controller upgrade only: application publication held; read-only checks remain available')
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with Path(summary_path).open('a', encoding='utf-8') as stream:
            stream.write(publication_summary(allowed))
