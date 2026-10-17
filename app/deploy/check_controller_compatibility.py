"""CI-only check against a reviewed controller capability ceiling; never approves drift."""
import hashlib
import json
from pathlib import Path
import re
from migration_policy import migration_policy_load, migration_policy_validate


def verify(root):
    deploy = root / 'app/deploy'
    manifest = json.loads((deploy / 'controller-manifest.json').read_text())
    source = deploy / 'approved/prp-release.py'
    candidate = manifest.get('candidate_controller', manifest['approved_controller'])
    if candidate.get('path') != manifest['approved_controller']['path']:
        raise ValueError('Candidate controller path differs from the approved production path')
    if hashlib.sha256(source.read_bytes()).hexdigest() != candidate['sha256']:
        raise ValueError('Reviewed controller candidate source does not match its approved digest')
    capability = manifest['migration_compatibility']
    migrations = {}
    migration_root=root / 'app/backend/src/main/resources/db/migration'
    for path in migration_root.rglob('*.sql'):
        if path.parent!=migration_root or re.fullmatch(r'V(\d+)__.+\.sql',path.name) is None:
            raise ValueError('Nonversioned, nested or callback SQL requires specialist review')
        version = int(re.fullmatch(r'V(\d+)__.+\.sql', path.name)[1])
        if version in migrations: raise ValueError('Duplicate migration version')
        migrations[version] = path
    validator = deploy/'migration_policy.py'
    if not validator.is_file(): raise ValueError('Missing CI migration policy validator')
    embedded = source.read_text(encoding='utf-8').split('# BEGIN VERSIONED MIGRATION POLICY\n')
    if len(embedded)!=2 or embedded[1].split('\n# END VERSIONED MIGRATION POLICY')[0]!=validator.read_text(encoding='utf-8'):
        raise ValueError('CI/runtime migration policy validator drift')
    generic = capability.get('generic_policy')
    if generic is not None and generic!={'schema_version':1,'mode':'create-empty','first_version':22}:
        raise ValueError('Unknown generic migration capability')
    if generic != {'schema_version':1,'mode':'create-empty','first_version':22} and max(migrations) > capability['reviewed_through_version']:
        raise ValueError('New migration requires production controller compatibility review before merge')
    policy_file=deploy/'migration-policy.json'
    policy=migration_policy_load(policy_file.read_bytes()) if policy_file.exists() else {'schema_version':1,'rules':[]}
    sql_files={v:(p.name,p.read_bytes().replace(b'\r\n',b'\n')) for v,p in migrations.items()}
    migration_policy_validate(policy,sql_files)
    for version, record in capability['pinned_migrations'].items():
        if int(version) not in migrations:
            raise ValueError('Reviewed migration is missing from repository')
        path = migrations[int(version)]
        if path.name != record['file'] or hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != record['sha256']:
            raise ValueError('Reviewed migration changed; independent compatibility review required')


if __name__ == '__main__':
    verify(Path(__file__).resolve().parents[2])
    print('Reviewed controller candidate/migration compatibility passed; live attestation remains mandatory')
