"""No network: host pin, key lifetime and narrow transport contract tests."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
from guard_release_engine import GateError,digest
import pinned_transaction_channel as channel


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.client=Mock()
        self.client.get_transport.return_value.get_remote_server_key.return_value.asbytes.return_value=b'fixture-host-key'
        self.manifest={'reviewed_sources':{}}
        self.c=channel.PinnedChannel(self.client,'fixture-transaction',self.manifest,digest(self.manifest))

    def test_wrong_host_never_executes_remote_command(self):
        with patch.object(channel,'call') as call:
            with self.assertRaises(GateError):self.c.read()
            call.assert_not_called()

    def test_terminal_read_has_no_key(self):
        with patch.object(self.c,'_call',return_value={'state':'ROLLED_BACK'}) as call:
            self.assertEqual(self.c.read(),({'state':'ROLLED_BACK'},None))
            call.assert_called_once_with('read')

    def test_private_key_removed_from_snapshot(self):
        import base64
        with patch.object(self.c,'_call',return_value={'state':'PREFLIGHT','key':base64.b64encode(b'x'*32).decode()}):
            snapshot,key=self.c.read()
            self.assertNotIn('key',snapshot)
            self.assertEqual(key,b'x'*32)

    def test_malformed_key_rejected(self):
        for key in ['bad!','eA==',None]:
            with patch.object(self.c,'_call',return_value={'state':'PREFLIGHT','key':key}):
                with self.assertRaises(GateError):self.c.read()

    def test_paths_and_manifest_pin_rejected(self):
        for name in ['../escape','x/y','', 'x'*101]:
            with self.assertRaises(GateError):channel.PinnedChannel(self.client,name,self.manifest,digest(self.manifest))
        with self.assertRaises(GateError):channel.PinnedChannel(self.client,'safe',self.manifest,'0'*64)

    def test_submit_requires_exact_receipt(self):
        with patch.object(self.c,'_call',return_value={'stored':False}):
            with self.assertRaises(GateError):self.c.submit(dict(deployment_id='a'*32,phase='preflight',nonce='b'*48), {})

    def test_real_phase_names_accepted_by_exact_remote_function(self):
        namespace={}
        definition=channel.REMOTE.split('import base64,hashlib,json,os,pathlib,stat,sys',1)[0]
        exec(compile(definition,'shared-remote-filename','exec'),namespace)
        for phase in ['preflight','post_reload','post_rollback']:
            job=dict(deployment_id='a'*32,phase=phase,nonce='b'*48)
            expected='a'*32+'.'+phase+'.'+'b'*48+'.json'
            self.assertEqual(namespace['inbox_filename'](job),expected)
            self.assertEqual(channel.inbox_filename(job),expected)

    def test_inbox_traversal_and_unknown_phase_rejected_before_ssh(self):
        for changes in [dict(phase='../escape'),dict(phase='deploy'),dict(nonce='../secret'),dict(deployment_id='x')]:
            job=dict(deployment_id='a'*32,phase='preflight',nonce='b'*48);job.update(changes)
            with patch.object(self.c,'_call') as call:
                with self.assertRaises(GateError):self.c.submit(job,{})
                call.assert_not_called()

    def test_remote_program_compiles_without_execution(self):
        compile(channel.REMOTE,'reviewed-private-reader','exec')


if __name__=='__main__':unittest.main()
