import json
from pathlib import Path
import tempfile
import unittest
from release_control import publication_allowed, publication_summary


class PublicationHoldTests(unittest.TestCase):
    def test_absence_allows_release_and_presence_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertTrue(publication_allowed(root))
            path=root/'app/deploy/publication-hold.json';path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'schema_version':1,'reason':'controller only'}))
            self.assertFalse(publication_allowed(root))
            path.unlink()
            self.assertTrue(publication_allowed(root))

    def test_invalid_hold_fails_closed(self):
        for value in [{},{'schema_version':True,'reason':'x'},{'schema_version':1,'reason':'x','allow':True},'invalid']:
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);path=root/'app/deploy/publication-hold.json';path.parent.mkdir(parents=True)
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError): publication_allowed(root)


    def test_summary_explicitly_disambiguates_hold_from_deployment(self):
        held = publication_summary(False)
        self.assertIn('HELD', held)
        self.assertIn('NOT DEPLOYED', held)
        self.assertIn('publication-hold.json', held)
        self.assertIn('green release-control job', held)
        self.assertNotIn('deployment succeeded', held.lower())

    def test_allowed_summary_does_not_claim_successful_deployment(self):
        allowed = publication_summary(True)
        self.assertIn('ALLOWED', allowed)
        self.assertIn('not yet deployed', allowed)
        self.assertIn('publish job', allowed)


if __name__=='__main__': unittest.main()
