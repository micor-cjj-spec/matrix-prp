"""Exercise the exact reviewed production preservation function, without host access."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'approved/prp-release.py'


def preservation():
    tree = ast.parse(SOURCE.read_bytes())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'assert_preserved')
    namespace = {'V15_PUBLIC_FOOD_SIGNATURES': set()}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace['assert_preserved']


class ApprovedControllerTests(unittest.TestCase):
    def setUp(self):
        self.check = preservation()
        self.before = {'counts': {'prp_users': 2}, 'row_sha256': {'prp_users': {'1': 'a', '2': 'b'}}, 'videos': 'owned'}
        self.after = copy.deepcopy(self.before)
        self.after['counts']['prp_vocal_takes'] = 0
        self.after['row_sha256']['prp_vocal_takes'] = {}

    def test_reviewed_source_matches_manifest(self):
        manifest = json.loads((ROOT / 'controller-manifest.json').read_text())
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), manifest['approved_controller']['sha256'])

    def test_v20_initially_empty_table(self):
        self.check(self.before, self.after)

    def test_v20_unexpected_seed_rows_rejected(self):
        self.after['counts']['prp_vocal_takes'] = 1
        self.after['row_sha256']['prp_vocal_takes'] = {'3': 'new'}
        with self.assertRaises(AssertionError): self.check(self.before, self.after)

    def test_unknown_table_rejected_even_empty(self):
        self.after['counts']['prp_unreviewed'] = 0
        with self.assertRaises(AssertionError): self.check(self.before, self.after)

    def test_historical_changed_deleted_or_inserted_rows_rejected(self):
        for mutation in ('changed', 'deleted', 'inserted', 'missing_proof'):
            after = copy.deepcopy(self.after)
            if mutation == 'changed': after['row_sha256']['prp_users']['1'] = 'changed'
            if mutation == 'deleted': del after['row_sha256']['prp_users']['1']
            if mutation == 'inserted':
                after['row_sha256']['prp_users']['3'] = 'new'
                after['counts']['prp_users'] = 3
            if mutation == 'missing_proof': del after['row_sha256']['prp_users']
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError): self.check(self.before, after)

    def test_existing_vocal_records_protected_after_cutover(self):
        before = copy.deepcopy(self.after)
        before['counts']['prp_vocal_takes'] = 1
        before['row_sha256']['prp_vocal_takes'] = {'1': 'original'}
        self.check(before, copy.deepcopy(before))
        after = copy.deepcopy(before)
        after['row_sha256']['prp_vocal_takes']['1'] = 'changed'
        with self.assertRaises(AssertionError): self.check(before, after)

    def test_video_ownership_guard_retained(self):
        self.after['videos'] = 'different-owner'
        with self.assertRaises(AssertionError): self.check(self.before, self.after)

    def test_v19_backfill_guard_retained(self):
        self.after['counts']['prp_wellness_ai_action_targets'] = 1
        with self.assertRaises(AssertionError): self.check(self.before, self.after)
        self.after['v19_backfill'] = {'actual_count':1,'expected_count':1,'actual_sha256':'a','expected_sha256':'b'}
        with self.assertRaises(AssertionError): self.check(self.before, self.after)


if __name__ == '__main__': unittest.main()
