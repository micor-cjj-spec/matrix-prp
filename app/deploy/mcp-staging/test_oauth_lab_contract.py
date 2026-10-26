from pathlib import Path
import unittest
import importlib.util
import os
import tempfile


class OAuthLabContractTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'Linux permission boundary')
    def test_unprivileged_keycloak_can_traverse_import_under_private_umask(self):
        script=Path(__file__).resolve().parent.parent/'mcp-oauth-stage/prepare.py'
        spec=importlib.util.spec_from_file_location('lab_prepare',script)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            previous=os.umask(0o077)
            try:
                path=Path(temp)/'realm';module.import_directory(path)
                self.assertEqual(path.stat().st_mode & 0o777,0o755)
            finally:os.umask(previous)

    def test_loopback_only_and_separate_persistent_store(self):
        lab = Path(__file__).resolve().parent.parent / 'mcp-oauth-stage'
        compose = (lab / 'compose.yaml').read_text()
        self.assertIn('127.0.0.1:18443:443', compose)
        self.assertEqual(compose.count('ports:'), 1)
        self.assertIn('oauth_pgdata:/var/lib/postgresql/data', compose)
        self.assertIn('auth_private: {internal: true}', compose)
        self.assertNotIn('network_mode: host', compose)
        overlay = (lab / 'backend-overlay.yaml').read_text()
        self.assertIn("MATRIX_PRP_MCP_WRITE_ENABLED: 'false'", overlay)
        self.assertIn("MATRIX_PRP_MCP_OAUTH_ADVERTISED_SCOPES: 'prp.tasks.read'", overlay)
        self.assertNotIn('MATRIX_PRP_DB_', overlay)
        self.assertNotIn('MATRIX_PRP_JWT_SECRET', overlay)

    def test_server_e2e_reuses_strict_public_scope_checker(self):
        source = (Path(__file__).resolve().parent.parent /
                  'mcp-oauth-stage/server_e2e.py').read_text()
        self.assertIn('from ci_public_readonly_probe import resource_check', source)
        self.assertIn('    resource_check(protected)\n', source)

    def test_preparation_checks_capacity_and_never_overwrites_env(self):
        lab = Path(__file__).resolve().parent.parent / 'mcp-oauth-stage'
        source = (lab / 'prepare.py').read_text()
        self.assertIn('available < 2 * 1024**3', source)
        self.assertIn('free < 25 * 1024**3', source)
        self.assertIn("(state / '.env').open('x')", source)
        self.assertIn('ssl_reject_handshake on', source)
        self.assertIn('access_log off', source)
        self.assertIn('keyUsage=critical,keyCertSign,cRLSign', source)
        self.assertIn("'verify','-x509_strict'", source)
        self.assertNotIn('CERT_NONE', source)
        self.assertNotIn('verify=False', source)

    def test_public_vhosts_are_review_only_and_verify_internal_tls(self):
        script=Path(__file__).resolve().parent.parent/'mcp-oauth-stage/public_nginx.py'
        spec=importlib.util.spec_from_file_location('lab_public',script)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        config=module.render()
        self.assertIn('proxy_ssl_verify on',config)
        self.assertIn('proxy_ssl_name auth-test.micor.top',config)
        self.assertIn('location ^~ /admin/ { return 404; }',config)
        self.assertIn('location ^~ /realms/master/ { return 404; }',config)
        self.assertEqual(config.count('server_name '),3) # two vhosts + upstream SNI
        self.assertNotIn('server_name micor.top;',config)


if __name__ == '__main__':
    unittest.main()
