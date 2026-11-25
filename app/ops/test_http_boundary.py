import json
import threading
import unittest
from unittest.mock import Mock, patch
from http_boundary import (HttpBoundary, Budget, RESOURCE_PATH, METADATA_PATH,
                           PROTOCOL, RATE, CONCURRENCY)
from query_contract import Policy, TOOL, RESOURCE, ISSUER, SCOPE

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.clock=Mock(return_value=100)
        self.audit=Mock(return_value=True)
        self.marker=Mock(return_value=True)
        self.boundary=HttpBoundary(server={"policy":Policy(True)},audit_sink=self.audit,
            budget=Budget(self.clock),disclosure_check=self.marker)
        self.body=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
        self.headers=[("Host","ops.invalid"),("Content-Type","application/json"),
            ("Accept","application/json, text/event-stream"),
            ("Content-Length",str(len(self.body))),("Authorization","Bearer secret-fixture"),
            ("MCP-Protocol-Version",PROTOCOL)]

    def request(self,method="POST",target=RESOURCE_PATH,headers=None,body=None):
        return self.boundary.handle(method,target,self.headers if headers is None else headers,
            self.body if body is None else body)

    def test_public_metadata_only_fixed_resource(self):
        got=self.request("GET",METADATA_PATH,[("Host","ops.invalid")],b"")
        self.assertEqual(got.status,200)
        self.assertEqual(json.loads(got.body),{"resource":RESOURCE,"authorization_servers":[ISSUER],
            "scopes_supported":[SCOPE],"bearer_methods_supported":["header"]})
        self.marker.assert_not_called()

    def test_exact_target_and_methods(self):
        for target in ("/mcp/","/mcp?x=1","/mcp/../mcp","https://ops.invalid/mcp","/api/mcp"):
            self.assertEqual(self.request(target=target).status,404)
        for method in ("GET","DELETE","PUT","OPTIONS"):
            self.assertEqual(self.request(method=method).status,405)

    def test_duplicate_security_headers_and_header_injection_denied(self):
        for header in (("authorization","Bearer second"),("CONTENT-LENGTH",str(len(self.body))),
                       ("Host","ops.invalid"),("Origin","https://evil.invalid\nx:y"),
                       ("Content-Type","application/json"),("X-Other","bad\r\n")):
            self.assertEqual(self.request(headers=self.headers+[header]).status,400)

    def test_oversize_headers_rejected_before_character_scan(self):
        from http_boundary import parse_headers
        # Mock the scanner, not wall time; no character inspection may occur.
        with patch("http_boundary.ord",create=True,side_effect=AssertionError("oversize scan")), \
             patch("http_boundary.re.fullmatch",side_effect=AssertionError("oversize regex")):
            with self.assertRaises(ValueError):
                parse_headers([("X","x"*5000000)])
            with self.assertRaises(ValueError):
                parse_headers([("X"*5000000,"x")])

    def test_origin_host_framing_and_session_rejection(self):
        for extra,status in ((("Origin","https://evil.invalid"),403),
            (("Transfer-Encoding","chunked"),400),(("Content-Encoding","gzip"),400),
            (("Mcp-Session-Id","other"),400)):
            self.assertEqual(self.request(headers=self.headers+[extra]).status,status)
        self.assertEqual(self.request(headers=[("Host","evil.invalid")]+self.headers[1:]).status,400)
        self.assertEqual(self.request(body=self.body+b" ").status,400)

    def test_bounded_headers_body_media_and_protocol(self):
        self.assertEqual(self.request(body=b"x"*4097).status,413)
        self.assertEqual(self.request(headers=self.headers+[("X","x"*12289)]).status,400)
        for key,value,status in (("Content-Type","text/html",415),("Accept","text/html",406),
                                 ("MCP-Protocol-Version","unknown",400)):
            headers=[(k,value if k==key else v) for k,v in self.headers]
            self.assertEqual(self.request(headers=headers).status,status)

    def test_marker_default_off_and_revoked_before_return(self):
        with patch("http_boundary.dispatch_fixture",return_value=(200,{"result":{}})) as dispatch:
            self.marker.return_value=False
            self.assertEqual(self.request().status,503)
            dispatch.assert_not_called()
            self.marker.side_effect=[True,False]
            self.assertEqual(self.request().status,503)
            self.marker.side_effect=[True,True,False]
            self.assertEqual(self.request().status,503)

    def test_disabled_policy_never_dispatches(self):
        self.boundary=HttpBoundary(server={"policy":Policy()},audit_sink=self.audit,
            budget=Budget(self.clock),disclosure_check=self.marker)
        with patch("http_boundary.dispatch_fixture") as dispatch:
            got=self.request()
        self.assertEqual(got.status,401)
        self.assertIn("resource_metadata",dict(got.headers)["WWW-Authenticate"])
        dispatch.assert_not_called()

    def test_audit_only_fixed_fields_and_fail_closed(self):
        with patch("http_boundary.dispatch_fixture",return_value=(200,{"result":{"secret":"fixture-metrics"}})):
            got=self.request()
            self.assertEqual(got.status,200)
            event=self.audit.call_args.args[0]
            self.assertEqual(set(event),{"version","traceId","route","candidateStatus","outcome"})
            self.assertNotIn("secret",json.dumps(event))
            self.audit.return_value=False
            got=self.request()
            self.assertEqual(got.status,503)
            self.assertEqual(got.body,b"")

    def test_tool_error_audit_is_denied(self):
        with patch("http_boundary.dispatch_fixture",return_value=(200,{"result":{"isError":True}})):
            self.assertEqual(self.request().status,200)
            self.assertEqual(self.audit.call_args.args[0]["outcome"],"denied")

    def test_rate_limit_bounds_all_attempts_and_recovers(self):
        for _ in range(RATE):
            self.assertEqual(self.request(target="/wrong").status,404)
        self.assertEqual(self.request().status,429)
        self.assertEqual(self.audit.call_count,RATE)
        # Rejecting an unadmitted attempt never calls the durable sink.
        self.audit.return_value=False
        self.assertEqual(self.request().status,429)
        self.assertEqual(self.audit.call_count,RATE)
        self.audit.return_value=True
        self.clock.return_value=160
        self.assertEqual(self.request(target="/wrong").status,404)

    def test_global_concurrency_and_clock_regression(self):
        budget=Budget(self.clock)
        for _ in range(CONCURRENCY):
            self.assertTrue(budget.acquire())
        self.assertFalse(budget.acquire())
        budget.release()
        self.assertTrue(budget.acquire())
        for _ in range(CONCURRENCY):
            budget.release()
        self.clock.return_value=99
        with self.assertRaises(ValueError):
            budget.acquire()

    def test_final_marker_check_holds_slot_and_releases_on_denial(self):
        budget=Budget(self.clock)
        for _ in range(CONCURRENCY-1):
            self.assertTrue(budget.acquire())
        observations=[]
        def check():
            observations.append(budget.acquire())
            if observations[-1]:
                budget.release()
            return len(observations)<3
        boundary=HttpBoundary(server={"policy":Policy(True)},audit_sink=self.audit,
            budget=budget,disclosure_check=check)
        with patch("http_boundary.dispatch_fixture",return_value=(200,{"result":{}})):
            got=boundary.handle("POST",RESOURCE_PATH,self.headers,self.body)
        self.assertEqual(got.status,503)
        self.assertEqual(observations,[False,False,False])
        self.assertEqual(self.audit.call_args.args[0]["candidateStatus"],200)
        self.assertTrue(budget.acquire())
        for _ in range(CONCURRENCY):
            budget.release()

    def test_authentication_challenge_no_details(self):
        with patch("http_boundary.dispatch_fixture",return_value=(401,None)):
            got=self.request()
        self.assertEqual(got.status,401)
        self.assertEqual(got.body,b"")
        self.assertIn("resource_metadata",dict(got.headers)["WWW-Authenticate"])
