import hashlib,importlib.util,io,json,tarfile,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('release',Path(__file__).with_name('server-release.py'))
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class DeploymentBoundaryTests(unittest.TestCase):
 def artifact(self,root,extra=None,wrong_hash=False):
  payload=root/'payload';payload.mkdir();(payload/'web').mkdir();(payload/'web/index.html').write_text('PRP')
  with zipfile.ZipFile(payload/'backend.jar','w') as jar:
   jar.writestr('BOOT-INF/classes/db/migration/V7__legacy.sql','-- fixture')
   jar.writestr('BOOT-INF/classes/com/matrix/prp/deployment/DatabaseTool.class',b'fixture')
  files={str(p.relative_to(payload)):hashlib.sha256(p.read_bytes()).hexdigest() for p in payload.rglob('*') if p.is_file()}
  if wrong_hash:files['backend.jar']='0'*64
  (payload/'release.json').write_text(json.dumps({'id':'test-1','commit':'a'*40,'schema_version':7,'files':files}))
  archive=root/'artifact.tgz'
  with tarfile.open(archive,'w:gz') as tar:
   for p in payload.iterdir():tar.add(p,arcname=p.name)
   if extra:tar.addfile(extra,io.BytesIO(b'x') if extra.isfile() else None)
  return archive
 def test_valid_artifact(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);out=root/'out';out.mkdir()
   self.assertEqual(release.unpack(self.artifact(root),out)['id'],'test-1')
 def test_path_traversal_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);out=root/'out';out.mkdir();member=tarfile.TarInfo('../escape');member.size=1
   with self.assertRaises(ValueError):release.unpack(self.artifact(root,member),out)
   self.assertFalse((root/'escape').exists())
 def test_symlink_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);out=root/'out';out.mkdir();member=tarfile.TarInfo('web/link');member.type=tarfile.SYMTYPE;member.linkname='/etc'
   with self.assertRaises(ValueError):release.unpack(self.artifact(root,member),out)
 def test_checksum_mismatch_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);out=root/'out';out.mkdir()
   with self.assertRaises(ValueError):release.unpack(self.artifact(root,wrong_hash=True),out)
 def test_cross_schema_rollback_never_stops_service(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);old=root/'old';old.mkdir();(old/'release.json').write_text(json.dumps({'schema_version':7}))
   with patch.object(release,'BASE',root),patch.object(release,'schema_version',return_value=13),patch.object(release,'run') as command:
    with self.assertRaises(ValueError):release.rollback('old')
    command.assert_not_called()
 def test_video_ownership_changes_block_migration(self):
  with self.assertRaises(AssertionError):release.assert_preserved({'counts':{'prp_video_assets':427},'videos':'owner2'},{'counts':{'prp_video_assets':427},'videos':'owner1'})
 def test_additive_food_rows_are_allowed_only_if_original_rows_are_identical(self):
  before={'counts':{'prp_wellness_foods':2,'prp_video_assets':3},
    'food_row_sha256':{'1':'abc','2':'def'},'videos':'unchanged'}
  after={'counts':{'prp_wellness_foods':145,'prp_video_assets':3},
    'food_row_sha256':{'1':'abc','2':'def','3':'new'},'videos':'unchanged'}
  release.assert_preserved(before,after)
  with self.assertRaises(AssertionError):
   release.assert_preserved(before,{**after,'food_row_sha256':{'1':'abc','2':'modified'}})
  with self.assertRaises(AssertionError):
   release.assert_preserved(before,{**after,'food_row_sha256':{'1':'abc'}})
  with self.assertRaises(AssertionError):
   release.assert_preserved(before,{**after,'counts':{'prp_wellness_foods':1,'prp_video_assets':3}})
 def test_food_snapshot_never_silently_skips_missing_fingerprints(self):
  before={'counts':{'prp_wellness_foods':1},'videos':'same','food_row_sha256':{'7':'xyz'}}
  after={'counts':{'prp_wellness_foods':3},'videos':'same'}
  with self.assertRaises(AssertionError):
   release.assert_preserved(before,after)
 def test_other_business_table_counts_must_still_match(self):
  before={'counts':{'prp_wellness_meals':3},'videos':'same'}
  after={'counts':{'prp_wellness_meals':4},'videos':'same'}
  with self.assertRaises(AssertionError):
   release.assert_preserved(before,after)

if __name__=='__main__':unittest.main()
