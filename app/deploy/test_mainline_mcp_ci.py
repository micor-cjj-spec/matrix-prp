"""The actual main CI must run the reviewed integration suites at one SHA."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MainlineMcpCITests(unittest.TestCase):
    def test_all_required_suites_are_unconditional_local_reusable_jobs(self):
        contract = json.loads((ROOT/'app/deploy/mainline-mcp-ci-contract.json').read_text())
        ci = (ROOT/'.github/workflows/ci.yml').read_text()
        headers = list(re.finditer(r'(?m)^  ([a-zA-Z0-9_-]+):\s*$', ci))
        bodies = {m.group(1): ci[m.end():headers[i+1].start() if i+1 < len(headers) else len(ci)]
                  for i, m in enumerate(headers)}
        for job, filename in contract['required_reusable_jobs'].items():
            with self.subTest(job=job):
                self.assertIn(job, bodies)
                lines = [x.strip() for x in bodies[job].splitlines() if x.strip() and not x.lstrip().startswith('#')]
                # No paths/if/continue-on-error/secrets: inherit can turn a suite optional.
                self.assertEqual(lines, [f'uses: ./.github/workflows/{filename}', 'permissions:', 'contents: read'])
                workflow = (ROOT/'.github/workflows'/filename).read_text()
                self.assertIn('\non:\n  workflow_call:\n', workflow)
                self.assertNotIn('secrets: inherit', workflow)
                self.assertNotRegex(workflow, r'(?m)^\s*environment:')
        for job in contract['required_local_jobs']:
            self.assertIn(job, bodies)

    def test_application_publication_remains_held(self):
        path = ROOT/'app/deploy/release_control.py'
        spec = importlib.util.spec_from_file_location('mcp_integration_release_control', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertIs(module.publication_allowed(ROOT), False)
        workflow = (ROOT/'.github/workflows/deploy-prp.yml').read_text()
        self.assertIn("needs.release_control.outputs.publish_allowed == 'true'", workflow)
        self.assertIn('environment:\n      name: production', workflow)


if __name__ == '__main__': unittest.main()
