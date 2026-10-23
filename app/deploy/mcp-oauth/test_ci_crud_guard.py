import os
import unittest
from unittest.mock import Mock, patch
import ci_crud_flow


class CrudRunnerGuardTests(unittest.TestCase):
    def test_no_flow_calls_outside_explicit_disposable_ci(self):
        for env in ({}, {'GITHUB_ACTIONS':'true'}, {'MCP_E2E_CRUD':'true'},
                    {'GITHUB_ACTIONS':'false','MCP_E2E_CRUD':'true'}):
            flow=Mock()
            with patch.dict(os.environ,env,clear=True):
                with self.assertRaises(RuntimeError):
                    ci_crud_flow.run(flow,None,'synthetic-session','synthetic-password','synthetic-login')
            self.assertEqual(flow.mock_calls,[])

if __name__=='__main__':unittest.main()
