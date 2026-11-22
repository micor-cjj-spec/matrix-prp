"""End-to-end offline bridge contract: no actual GitHub API, SSH or server calls."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from protocol import (InvalidJob, b64_decode, b64_encode, build_command,
                      create_result_identity, openssl_cms_encrypt,
                      parse_command_comment, parse_result_comment)
from github_bridge import ssh_exchange, post_private_result

class BridgeTransportContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        cls.key=Path(cls.folder.name)/'recipient.key'
        cls.crt=Path(cls.folder.name)/'recipient.crt'
        p=subprocess.run(['openssl','req','-new','-x509','-nodes',
            '-newkey','rsa:3072','-days','1','-subj','/CN=PRP-test-bridge',
            '-keyout',str(cls.key),'-out',str(cls.crt)],
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=20)
        if p.returncode:
            raise RuntimeError('openssl certificate generation failed')
    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_bridge_preserves_encrypted_payload_and_only_publishes_ciphertext(self):
        command="printf 'sensitive output only in memory'"
        job_id,comment,reply_key,reply_cert=build_command(
            command,self.crt.read_bytes(),now=1795344000)
        _,cipher=parse_command_comment(comment)
        result={'jobId':job_id,'version':1,'stdout':'secret simulated result','stderr':'',
                'exitCode':0,'timedOut':False,'truncated':False}
        reply_cipher=b64_encode(openssl_cms_encrypt(
            json.dumps(result).encode(),reply_cert))
        mock_ssh_result=subprocess.CompletedProcess([],0,json.dumps({
            'jobId':job_id,'ciphertext':reply_cipher}).encode(),b'')
        with mock.patch('github_bridge.subprocess.run',return_value=mock_ssh_result) as fake:
            response=ssh_exchange(job_id,cipher,'127.0.0.1',
                     'dummy-key-not-a-real-ssh-key', '127.0.0.1 ssh-ed25519 dummy')
        self.assertEqual(response,reply_cipher)
        argv=fake.call_args.args[0]
        self.assertIn('-T',argv)
        self.assertIn('BatchMode=yes',argv)
        self.assertIn('StrictHostKeyChecking=yes',argv)
        self.assertIn('ClearAllForwardings=yes',argv)
        self.assertEqual(argv[-2:],['prp-chat-shell@127.0.0.1','run'])
        sent=fake.call_args.kwargs['input']
        self.assertNotIn(command.encode(),sent)
        self.assertEqual(json.loads(sent),{'jobId':job_id,'ciphertext':cipher})
        self.assertEqual(
            parse_result_comment('/prp-shell-result-v1 '+job_id+' '+response,
                                  job_id,reply_key,reply_cert)['stdout'],
            'secret simulated result')

        class FakeResponse:
            status=201
            def __enter__(self):
                return self
            def __exit__(self,*args):
                pass
        with mock.patch('github_bridge.urllib.request.urlopen',return_value=FakeResponse()) as posted:
            post_private_result(job_id,response,'dummy-gh-token-for-unit-test')
        req=posted.call_args.args[0]
        encoded_comment=json.loads(req.data.decode())['body']
        self.assertTrue(encoded_comment.startswith('/prp-shell-result-v1 '+job_id+' '))
        self.assertNotIn('secret simulated result',encoded_comment)
        self.assertNotIn(command,encoded_comment)
        self.assertNotIn('dummy-gh-token',encoded_comment)

    def test_wrong_ssh_response_job_id_rejected_without_result_post(self):
        job_id,comment,_,_=build_command('id -u',self.crt.read_bytes(),now=1795344000)
        _,cipher=parse_command_comment(comment)
        foreign_job='11111111-1111-4111-8111-111111111111'
        result={'jobId':foreign_job,'ciphertext':cipher}
        fake_result=subprocess.CompletedProcess([],0,json.dumps(result).encode(),b'')
        with mock.patch('github_bridge.subprocess.run',return_value=fake_result):
            with self.assertRaises(InvalidJob):
                ssh_exchange(job_id,cipher,'127.0.0.1','dummy-key','dummy-known-hosts')

    def test_shell_metacharacters_cannot_enter_ssh_destination(self):
        with self.assertRaises(InvalidJob):
            ssh_exchange('id','abcdefghi','127.0.0.1; touch /tmp/pwn',
                'dummy-key','dummy-known-hosts')

if __name__=='__main__':
    unittest.main()
