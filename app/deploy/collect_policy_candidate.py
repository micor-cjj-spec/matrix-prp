"""Collect a redacted, explicitly UNAPPROVED policy candidate; never permit deployment."""
import argparse,json,re,secrets,subprocess
from datetime import datetime,timezone
from pathlib import Path
import ssh_policy_contract as sftp_policy
from verify_controller import verify_response
from verify_ssh_boundary import Verifier

def candidate(proof,nonce,now=None):
    if not isinstance(proof,dict) or set(proof)!=sftp_policy.PROOF_FIELDS:raise ValueError()
    if type(proof['schema_version']) is not int or proof['schema_version']!=1:raise ValueError()
    if proof['challenge']!=nonce.hex():raise ValueError()
    baseline=proof['baseline']
    if not isinstance(baseline,dict) or set(baseline)!=sftp_policy.BASELINE_FIELDS:raise ValueError()
    for key,value in baseline.items():
        if key.endswith('_sha256') and (not isinstance(value,str) or re.fullmatch('[a-f0-9]{64}',value) is None):raise ValueError()
    if re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}',baseline['deployment_key_fingerprint']) is None:raise ValueError()
    if baseline['forced_command']!=sftp_policy.GATEWAY or baseline['subsystem_command']!=sftp_policy.SUBSYSTEM or baseline['behavior']!=sftp_policy.BEHAVIOR:raise ValueError()
    if any(proof[k] is not True for k in ['connection_bound','loaded_policy_verified','trusted_paths']):raise ValueError()
    stamp=proof['observed_utc']
    if not isinstance(stamp,str) or not stamp.endswith('Z'):raise ValueError()
    age=((now or datetime.now(timezone.utc))-datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds()
    if not -5<=age<=30:raise ValueError()
    return {'schema_version':1,'code':'UNAPPROVED_SSH_POLICY_CANDIDATE','approved':False,
            'production_gate_passed':False,'proof':proof}

def unique(pairs):
    data={}
    for k,v in pairs:
        if k in data:raise ValueError()
        data[k]=v
    return data

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',required=True);parser.add_argument('--identity',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result={'schema_version':1,'code':'SSH_POLICY_CANDIDATE_UNAVAILABLE','approved':False,'production_gate_passed':False}
    code=1
    try:
        manifest=json.loads(args.manifest.read_text(encoding='utf-8'));v=Verifier(args.host,args.identity,manifest)
        attested=v.call('controller-attestation',[v.destination,'controller-sha256'])
        if attested.returncode!=0:raise ValueError()
        verify_response(manifest,attested.stdout.decode('ascii'))
        nonce=secrets.token_bytes(32)
        response=subprocess.run(v.base+[v.destination,'diagnose'],input=nonce,capture_output=True,timeout=20)
        if len(response.stdout)>8192 or len(response.stderr)>8192:raise ValueError()
        body=json.loads(response.stdout,object_pairs_hook=unique)
        if response.returncode!=0 or not isinstance(body,dict) or set(body)!={'schema_version','state','code','stage','table','exception','timestamp_utc','ssh_policy'}:raise ValueError()
        result=candidate(body['ssh_policy'],nonce);code=0
    except Exception:pass
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('Policy evidence collected; approval and production acceptance NOT granted' if code==0 else 'Policy evidence unavailable; deployment remains blocked')
    return code

if __name__=='__main__':raise SystemExit(main())
