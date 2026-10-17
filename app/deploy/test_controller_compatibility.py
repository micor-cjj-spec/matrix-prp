import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('compatibility', ROOT/'app/deploy/check_controller_compatibility.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ControllerCompatibilityTests(unittest.TestCase):
    def test_current_reviewed_migrations(self): module.verify(ROOT)

    def test_future_duplicate_or_modified_migration_fails_closed(self):
        for mutation in ('future','duplicate','modified','controller'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                deploy=root/'app/deploy'
                (deploy/'approved').mkdir(parents=True)
                for name in ('controller-manifest.json','approved/prp-release.py'):
                    (deploy/name).write_bytes((ROOT/'app/deploy'/name).read_bytes())
                migrations=root/'app/backend/src/main/resources/db/migration'
                migrations.mkdir(parents=True)
                source_dir=ROOT/'app/backend/src/main/resources/db/migration'
                for source in source_dir.glob('V*__*.sql'):
                    (migrations/source.name).write_bytes(source.read_bytes())
                source=migrations/'V20__vocal_training.sql'
                if mutation=='future': (migrations/'V22__unreviewed.sql').write_text('CREATE TABLE unknown_table(id BIGINT);')
                if mutation=='duplicate': (migrations/'V20__duplicate.sql').write_text('SELECT 1;')
                if mutation=='modified': (migrations/source.name).write_text('DROP TABLE prp_users;')
                if mutation=='controller': (deploy/'approved/prp-release.py').write_text('pass')
                with self.assertRaises(ValueError): module.verify(root)


if __name__=='__main__': unittest.main()
