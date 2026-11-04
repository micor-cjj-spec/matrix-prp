import ast
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class BackupCandidateBoundaryTests(unittest.TestCase):
    def test_approved_fixture_still_matches_unchanged_approved_manifest(self):
        manifest = json.loads((ROOT/'controller-manifest.json').read_text())
        self.assertNotIn('candidate_controller', manifest)
        self.assertEqual(hashlib.sha256((ROOT/'approved/prp-release.py').read_bytes()).hexdigest(),
                         manifest['approved_controller']['sha256'])

    def test_uninstalled_candidate_changes_only_dump_function(self):
        def nodes(path):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            return [ast.dump(n) for n in tree.body if not isinstance(n, ast.FunctionDef) or n.name != 'dump']
        self.assertEqual(nodes(ROOT/'approved/prp-release.py'), nodes(ROOT/'candidates/private_backup_controller.py'))
        proposed = (ROOT/'candidates/private_backup_controller.py').read_text()
        self.assertIn('os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW', proposed)
        self.assertIn('os.open(path,flags,0o600)', proposed)


if __name__ == '__main__': unittest.main()
