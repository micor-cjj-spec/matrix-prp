import copy,json,os,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import collect_policy_candidate as collector
import admin_upgrade_policy_helper as installer
import ssh_policy_contract as contract

class PolicyCandidateTests(unittest.TestCase):
    def proof(self):
        fields={k:'a'*64 for k in contract.BASELINE_FIELDS if k.endswith('_sha256')}
        fields.update(deployment_key_fingerprint='SHA256:'+'A'*43,subsystem_command=contract.SUBSYSTEM,forced_command=contract.GATEWAY,behavior=contract.BEHAVIOR)
        return {'schema_version':1,'challenge':(b'x'*32).hex(),'observed_utc':'2026-10-17T00:00:00Z','baseline':fields,
                'connection_bound':True,'loaded_policy_verified':True,'trusted_paths':True}

    def test_well_formed_candidate_is_never_approval_or_production_acceptance(self):
        result=collector.candidate(self.proof(),b'x'*32,now=datetime(2026,10,17,tzinfo=timezone.utc))
        self.assertFalse(result['approved']);self.assertFalse(result['production_gate_passed'])
        self.assertEqual(result['code'],'UNAPPROVED_SSH_POLICY_CANDIDATE')

    def test_unknown_extra_fields_bad_nonce_unverified_flags_and_stale_proof_are_rejected(self):
        variants=[]
        for field,value in [('challenge','0'*64),('trusted_paths',1),('loaded_policy_verified',False),('connection_bound',False),('observed_utc','2000-01-01T00:00:00Z')]:
            data=self.proof();data[field]=value;variants.append(data)
        data=self.proof();data['private_field']='PRIVATE_TOKEN';variants.append(data)
        data=self.proof();data['baseline']['gateway_sha256']='PRIVATE_TOKEN';variants.append(data)
        for data in variants:
            with self.assertRaises((ValueError,TypeError)):collector.candidate(data,b'x'*32,now=datetime(2026,10,17,tzinfo=timezone.utc))

    def test_duplicate_remote_json_is_not_accepted(self):
        with self.assertRaises(ValueError):json.loads('{"key":1,"key":2}',object_pairs_hook=collector.unique)

    def test_installer_atomic_replacement_only_changes_selected_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'helper';target.write_text('print("old")\n');target.chmod(0o750)
            sentinel=Path(tmp)/'controller';sentinel.write_text('unchanged')
            with patch.object(installer,'TARGET',target):installer.replace(b'print("new")\n')
            self.assertEqual(target.read_bytes(),b'print("new")\n')
            self.assertEqual(target.stat().st_mode&0o777,0o750)
            self.assertEqual(sentinel.read_text(),'unchanged')

    def test_bad_candidate_syntax_cannot_replace_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'helper';original=b'print("old")\n';target.write_bytes(original)
            with patch.object(installer,'TARGET',target),self.assertRaises(SyntaxError):installer.replace(b'if this is not valid python')
            self.assertEqual(target.read_bytes(),original)

if __name__=='__main__':unittest.main()
