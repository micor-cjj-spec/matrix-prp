"""Offline crypto/authorization regression. No GitHub tokens or production SSH."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

from protocol import (ACTOR, REPOSITORY, InvalidJob, b64_decode, b64_encode,
                      build_command, openssl_cms_encrypt, openssl_cms_decrypt,
                      parse_command_comment, parse_result_comment, strict_json, validate_payload)
import prp_shell_executor as executor
from github_bridge import ISSUE, verify_github_event

TIME=1795344000

class CommandCryptography(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context=tempfile.TemporaryDirectory()
        cls.folder=Path(cls.context.name)
        cls.server_key=cls.folder/'server.key'
        cls.server_cert=cls.folder/'server.crt'
        result=subprocess.run(['openssl','req','-new','-x509','-nodes','-newkey','rsa:3072',
            '-days','1','-subj','/CN=PRP-shell-offline-test',
            '-keyout',str(cls.server_key),'-out',str(cls.server_cert)],
            capture_output=True,timeout=20)
        if result.returncode: raise RuntimeError('OpenSSL required for offline test')

    @classmethod
    def tearDownClass(cls):
        cls.context.cleanup()

    def test_arbitrary_shell_is_sealed_no_plaintext_public(self):
        cmd="echo 'secret test marker 1452'\nprintf '%s\\n' done | wc -l; find /tmp -type f"
        job_id,public_comment,answer_key,answer_cert=build_command(cmd,self.server_cert.read_bytes(),20,now=TIME)
        self.assertNotIn(cmd,public_comment)
        self.assertNotIn('secret test marker',public_comment)
        parsed_id,encoded=parse_command_comment(public_comment)
        plain=openssl_cms_decrypt(b64_decode(encoded,40000),self.server_key,self.server_cert)
        job=validate_payload(strict_json(plain),parsed_id,now=TIME)
        self.assertEqual(cmd,job['command'])
        self.assertEqual('prp-production',job['target'])
        self.assertEqual(20,job['runSeconds'])
        result={'jobId':job_id,'version':1,'exitCode':0,'stdout':'secret output','stderr':'','truncated':False,'timedOut':False}
        cipher=b64_encode(openssl_cms_encrypt(json.dumps(result).encode(),answer_cert))
        result_comment=f'/prp-shell-result-v1 {job_id} {cipher}'
        self.assertNotIn('secret output',result_comment)
        self.assertEqual('secret output',parse_result_comment(result_comment,job_id,answer_key,answer_cert)['stdout'])
        with self.assertRaises(InvalidJob):
            parse_result_comment(result_comment,str(uuid4()),answer_key,answer_cert)

    def test_tampering_cms_bytes_fails_authentication(self):
        job_id,comment,_,_=build_command('id -u',self.server_cert.read_bytes(),now=TIME)
        _,encoded=parse_command_comment(comment)
        original=b64_decode(encoded,40000)
        tampered=original[:-3]+bytes([original[-3]^1])+original[-2:]
        with self.assertRaises(InvalidJob):
            openssl_cms_decrypt(tampered,self.server_key,self.server_cert)

    def test_server_rejects_expired_target_command_timeout_and_actor(self):
        job_id,comment,_,_=build_command('date',self.server_cert.read_bytes(),now=TIME)
        _,enc=parse_command_comment(comment)
        original=strict_json(openssl_cms_decrypt(b64_decode(enc,40000),self.server_key,self.server_cert))
        cases=[('target','attacker'),('actor','not-owner'),('expiresAt',TIME-1),
               ('runSeconds',31),('command',''),('nonce','aaa'),('answerCertificate','')]
        for key,value in cases:
            with self.subTest(key=key),self.assertRaises(InvalidJob):
                validate_payload({**original,key:value},job_id,now=TIME)
        with self.assertRaises(InvalidJob):
            validate_payload(original,job_id,now=TIME+301)
        with self.assertRaises(InvalidJob):
            validate_payload(original,str(uuid4()),now=TIME)

    def test_duplicate_payload_json_is_rejected(self):
        with self.assertRaises(InvalidJob):
            strict_json(b'{"command":"safe","command":"bad"}')

    def test_exact_once_claim_before_exec(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(executor,'STATE_DB',Path(d)/'state.db'):
                executor.claim(str(uuid4()),'a'*32)
                with self.assertRaises(InvalidJob):
                    executor.claim(str(uuid4()),'a'*32)
                fixed=str(uuid4())
                executor.claim(fixed,'b'*32)
                with self.assertRaises(InvalidJob):
                    executor.claim(fixed,'c'*32)

    def test_github_event_owner_issue_and_ref_only(self):
        job_id,comment,_,_=build_command('true',self.server_cert.read_bytes(),now=TIME)
        event={'action':'created','repository':{'full_name':REPOSITORY},
               'sender':{'login':ACTOR,'type':'User'},
               'comment':{'id':123,'body':comment,'user':{'login':ACTOR,'type':'User'}},
               'issue':{'number':ISSUE,'state':'open'}}
        self.assertEqual(job_id,verify_github_event(event,REPOSITORY,'refs/heads/main')[0])
        candidates=[{'sender':{'login':'attacker','type':'User'}},
                    {'sender':{'login':ACTOR,'type':'Bot'}},
                    {'issue':{'number':ISSUE+1,'state':'open'}},
                    {'issue':{'number':ISSUE,'state':'open','pull_request':{}}},
                    {'comment':{'id':123,'body':'/prp-shell-v1 forged','user':{'login':ACTOR,'type':'User'}}},
                    {'action':'edited'}]
        for variation in candidates:
            with self.subTest(variation=variation),self.assertRaises(InvalidJob):
                verify_github_event({**event,**variation},REPOSITORY,'refs/heads/main')
        with self.assertRaises(InvalidJob):
            verify_github_event(event,REPOSITORY,'refs/heads/some-feature')

    def test_gateway_has_single_forced_command_and_no_wildcard_sudo(self):
        gateway=Path(__file__).with_name('gateway.sh').read_text()
        self.assertIn('SSH_ORIGINAL_COMMAND',gateway)
        self.assertIn('run) exec sudo -n /usr/local/sbin/prp-chat-shell-executor',gateway)
        self.assertNotIn('sudo -n sh',gateway)
        self.assertNotIn('sudo -n bash',gateway)

if __name__=='__main__':
    unittest.main()
