"""CI-only check against a reviewed controller capability ceiling; never approves drift."""
import hashlib
import json
from pathlib import Path
import re


def verify(root):
    deploy = root / 'app/deploy'
    manifest = json.loads((deploy / 'controller-manifest.json').read_text())
    source = deploy / 'approved/prp-release.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest['approved_controller']['sha256']:
        raise ValueError('Reviewed production controller source does not match approved digest')
    capability = manifest['migration_compatibility']
    migrations = {}
    for path in (root / 'app/backend/src/main/resources/db/migration').glob('V*__*.sql'):
        version = int(re.fullmatch(r'V(\d+)__.+\.sql', path.name)[1])
        if version in migrations: raise ValueError('Duplicate migration version')
        migrations[version] = path
    if max(migrations) > capability['reviewed_through_version']:
        raise ValueError('New migration requires production controller compatibility review before merge')
    for version, record in capability['pinned_migrations'].items():
        path = migrations[int(version)]
        if path.name != record['file'] or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != record['sha256']:
            raise ValueError('Reviewed migration changed; independent compatibility review required')


if __name__ == '__main__':
    verify(Path(__file__).resolve().parents[2])
    print('Reviewed controller/migration compatibility passed; live attestation remains mandatory')
