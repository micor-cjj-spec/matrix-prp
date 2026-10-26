import unittest
from approval_routes_pending import render_approval_routes, EXACT, REGEX

class ApprovalRouteTests(unittest.TestCase):
 def test_only_fixed_loopback_upstream_and_verified_tls(self):
  text=render_approval_routes('/tmp/approved-ca.pem')
  self.assertEqual(text.count('proxy_ssl_verify on;'),15)
  self.assertEqual(text.count('proxy_pass https://127.0.0.1:18443;'),15)
  self.assertEqual(text.count('proxy_ssl_name prp-test.micor.top;'),15)
 def test_no_generic_frontend_business_or_admin_route(self):
  self.assertNotIn('/prp/',EXACT);self.assertNotIn('/api/',EXACT)
  for path in ['/api/tasks','/api/auth/register','/admin','/realms/master']:
   self.assertNotIn(path,EXACT)
 def test_state_changes_require_post(self):
  for path in ['/api/auth/login','/api/mcp/identity/tickets','/api/mcp/identity/unlink','/api/mcp/clients/revoke','/api/mcp/clients/pairing']:
   self.assertEqual(EXACT[path],'POST')
 def test_browser_pairing_route_exact_and_not_broad(self):
  # ci_browser_pairing_flow.py calls this route in the real isolated SPA
  # pairing flow; the public proposal must not silently omit it.
  self.assertEqual(EXACT['/api/mcp/clients/pairing'],'POST')
  text=render_approval_routes('/tmp/approved-ca.pem')
  self.assertIn('location = /api/mcp/clients/pairing {',text)
  self.assertIn('location = /api/mcp/link {',text)
  for forbidden in ['location ^~ /api/', 'location /api/', '/api/auth/register',
                    '/api/mcp/approval/drafts/submit']:
   self.assertNotIn(forbidden,text)
 def test_certificate_path_cannot_inject_nginx_directives(self):
  for path in ['/tmp/ca.pem; ssl_verify off;', '/tmp/../ca.pem','relative.pem','/tmp/ca.pem\n']:
   with self.assertRaises(ValueError):render_approval_routes(path)
 def test_invalid_ports_refused(self):
  for value in [True,443,65536,'18443']:
   with self.assertRaises(ValueError):render_approval_routes('/tmp/ca.pem',value)

if __name__=='__main__':unittest.main()
