"""Mock-only runtime tests: no installation, tunnel or registration."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import disposable_warp_runtime as warp


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.environment={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
            'RUNNER_OS':'Linux','PRP_WARP_COLLECTION_APPROVED':'true',
            'GITHUB_REPOSITORY':'micor-cjj-spec/matrix-prp',
            'GITHUB_REF':'refs/heads/fix/mcp-hosted-network-probe-20261024','RUNNER_TEMP':self.temp.name}
        self.calls=[]

    def command(self,label,args,*budgets,**kwargs):
        self.calls.append((label,args))
        if label=='client_version':return 0,b'warp-cli 2026.8.2115.0'
        if label=='readiness':return 0,b'Status update: Connected'
        if label=='cleanup_absence':return 1,b'Missing registration'
        return 0,b'UNEXPORTED SYNTHETIC PRIVATE OUTPUT'

    def enter(self,runtime):
        with patch.object(warp,'os',SimpleNamespace(name='posix',environ=self.environment)), \
             patch.object(Path,'read_text',return_value='VERSION_CODENAME=noble'):
            return runtime.__enter__()

    def test_no_extra_prp_controls_and_cleanup(self):
        runtime=warp.WarpRuntime()
        with patch.object(runtime,'run',side_effect=self.command):
            self.enter(runtime)
            runtime.__exit__(None,None,None)
        args=[arg for _,command in self.calls for arg in command]
        self.assertFalse(any('micor.top' in arg or '207.57.123.94' in arg for arg in args))
        self.assertTrue(runtime.cleanup['local_absence_confirmed'])
        self.assertNotIn('PRIVATE',repr(runtime.cleanup))

    def test_missing_explicit_approval_prevents_commands(self):
        self.environment.pop('PRP_WARP_COLLECTION_APPROVED')
        runtime=warp.WarpRuntime()
        with patch.object(runtime,'run') as run:
            with self.assertRaises(warp.RuntimeErrorSafe):self.enter(runtime)
            run.assert_not_called()

    def test_partial_registration_failure_still_cleans(self):
        runtime=warp.WarpRuntime()
        def command(label,*args,**kwargs):
            if label=='registration':raise warp.RuntimeErrorSafe('FAILED')
            return self.command(label,*args,**kwargs)
        with patch.object(runtime,'run',side_effect=command):
            with self.assertRaises(warp.RuntimeErrorSafe):self.enter(runtime)
        self.assertIn('cleanup_delete',[x[0] for x in self.calls])

    def test_cleanup_failure_cannot_produce_success(self):
        runtime=warp.WarpRuntime()
        def command(label,*args,**kwargs):
            if label=='cleanup_delete':return 1,b'PRIVATE'
            return self.command(label,*args,**kwargs)
        with patch.object(runtime,'run',side_effect=command):
            self.enter(runtime)
            with self.assertRaises(warp.RuntimeErrorSafe):runtime.__exit__(None,None,None)

    def test_version_drift_refuses_registration(self):
        runtime=warp.WarpRuntime()
        def command(label,*args,**kwargs):
            if label=='client_version':return 0,b'warp-cli 999.0'
            return self.command(label,*args,**kwargs)
        with patch.object(runtime,'run',side_effect=command):
            with self.assertRaises(warp.RuntimeErrorSafe):self.enter(runtime)
        self.assertNotIn('registration',[x[0] for x in self.calls])


if __name__=='__main__':unittest.main()
