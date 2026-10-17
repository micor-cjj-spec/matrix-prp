import json
from pathlib import Path
import tempfile
import unittest
from release_control import publication_allowed


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


if __name__=='__main__': unittest.main()
