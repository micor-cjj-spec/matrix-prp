import pathlib,subprocess,tempfile,unittest,os

class MysqlReadinessTests(unittest.TestCase):
 def run_probe(self,transient):
  source=pathlib.Path(__file__).with_name('test_full_e2e_ci.sh').read_text()
  body=source[source.index('mysql_ready() {'):source.index('echo "E2E MySQL:')]
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);docker=root/'docker'
   docker.write_text("#!/usr/bin/env python3\nimport os,pathlib,sys\np=pathlib.Path(os.environ['STATE']);n=int(p.read_text())+1 if p.exists() else 1;p.write_text(str(n))\nrequired=['--protocol=TCP','127.0.0.1','prp_e2e','matrix_prp_mcp_e2e','SELECT 1']\nsys.exit(0 if all(x in sys.argv for x in required) and os.environ['MODE']=='transient' and n>=3 else 1)\n")
   docker.chmod(0o700)
   result=subprocess.run(['bash','-c','database_user=synthetic; sleep() { :; }\n'+body],env=dict(os.environ,PATH=str(root)+os.pathsep+os.environ['PATH'],STATE=str(root/'state'),MODE='transient' if transient else 'failed'),capture_output=True,text=True)
   return result,int((root/'state').read_text())
 def test_initial_tcp_unready_state_does_not_pass(self):
  result,calls=self.run_probe(True)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(calls,4)
 def test_no_ready_application_account_fails_closed(self):
  result,calls=self.run_probe(False)
  self.assertEqual(result.returncode,1);self.assertEqual(calls,46)
  self.assertIn('application TCP account/database not ready',result.stderr)

if __name__=='__main__':unittest.main()
