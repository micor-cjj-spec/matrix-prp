import configparser
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SERVICE=ROOT/"app/deploy/systemd/prp-ops-collector.service"
TIMER=ROOT/"app/deploy/systemd/prp-ops-collector.timer"

def unit(path):
    parser=configparser.ConfigParser(interpolation=None,strict=True)
    parser.optionxform=str
    parser.read(path)
    return parser

class DeploymentContractTests(unittest.TestCase):
    def test_collector_service_is_disabled_by_default_and_non_root(self):
        service=unit(SERVICE)
        self.assertEqual(service["Unit"]["ConditionPathExists"],"/etc/matrix-prp-ops/ALLOW_HOST_METRICS")
        cfg=service["Service"]
        self.assertEqual(cfg["Type"],"oneshot")
        self.assertEqual(cfg["User"],"prp-ops-collector")
        self.assertEqual(cfg["Group"],"prp-ops-snapshot")
        self.assertEqual(cfg["UMask"],"0027")
        self.assertEqual(cfg["ExecStart"],"/usr/bin/python3 /usr/local/libexec/prp-ops/collector_runtime.py")
        self.assertNotIn("ExecStartPre",cfg)
        self.assertEqual(cfg["NoNewPrivileges"],"yes")
        self.assertEqual(cfg["ProtectSystem"],"strict")
        self.assertEqual(cfg["ProtectHome"],"yes")
        self.assertEqual(cfg["PrivateDevices"],"yes")
        self.assertEqual(cfg["PrivateTmp"],"yes")
        self.assertEqual(cfg["RestrictAddressFamilies"],"AF_UNIX")
        self.assertEqual(cfg["CapabilityBoundingSet"],"")
        self.assertEqual(cfg["AmbientCapabilities"],"")
        self.assertEqual(cfg["ReadWritePaths"],"/var/lib/prp-ops")
        self.assertEqual(cfg["RuntimeDirectory"],"prp-ops-collector")
        self.assertEqual(cfg["RuntimeDirectoryMode"],"0700")
        self.assertEqual(cfg["TimeoutStartSec"],"8s")
        self.assertEqual(cfg["Restart"],"no")
        self.assertNotIn("EnvironmentFile",cfg)
        self.assertNotIn("Shell",cfg["ExecStart"])

    def test_timer_is_gated_and_thirty_second_monotonic(self):
        timer=unit(TIMER)
        self.assertEqual(timer["Unit"]["ConditionPathExists"],"/etc/matrix-prp-ops/ALLOW_HOST_METRICS")
        cfg=timer["Timer"]
        self.assertEqual(cfg["OnBootSec"],"30s")
        self.assertEqual(cfg["OnUnitActiveSec"],"30s")
        self.assertEqual(cfg["AccuracySec"],"5s")
        self.assertEqual(cfg["Unit"],"prp-ops-collector.service")
        self.assertEqual(timer["Install"]["WantedBy"],"timers.target")

    def test_reader_service_template_has_no_auto_install_or_restart(self):
        path=ROOT/"app/deploy/systemd/prp-ops-mcp.service"
        raw=path.read_text()
        creds=[line for line in raw.splitlines() if line.startswith("LoadCredential=")]
        self.assertEqual(len(creds),3)
        self.assertEqual(set(creds),{
            "LoadCredential=introspection-secret:/etc/matrix-prp-ops/credentials/introspection-secret",
            "LoadCredential=tls-cert.pem:/etc/matrix-prp-ops/credentials/tls-cert.pem",
            "LoadCredential=tls-key.pem:/etc/matrix-prp-ops/credentials/tls-key.pem"})
        cfg=configparser.ConfigParser(interpolation=None,strict=True)
        cfg.optionxform=str
        cfg.read_string("\n".join(line for line in raw.splitlines() if not line.startswith("LoadCredential=")))
        self.assertEqual(cfg["Unit"]["ConditionPathExists"],"/etc/matrix-prp-ops/ENABLE_MCP_PROFILE")
        self.assertEqual(cfg["Service"]["User"],"prp-ops-mcp")
        self.assertEqual(cfg["Service"]["Group"],"prp-ops-mcp")
        self.assertEqual(cfg["Service"]["SupplementaryGroups"],"prp-ops-snapshot")
        self.assertEqual(cfg["Service"]["ReadOnlyPaths"],"/var/lib/prp-ops /etc/matrix-prp-ops")
        self.assertEqual(cfg["Service"]["ReadWritePaths"],"/var/lib/prp-ops-audit")
        self.assertEqual(cfg["Service"]["Restart"],"no")
        self.assertEqual(cfg["Service"]["ProtectSystem"],"strict")
        self.assertEqual(cfg["Service"]["NoNewPrivileges"],"yes")
        self.assertNotIn("Install",cfg)

    def test_ingress_candidates_use_same_fixed_loopback_port(self):
        from service_entry import BIND_HOST,BIND_PORT
        self.assertEqual((BIND_HOST,BIND_PORT),("127.0.0.1",18444))
        stream=(ROOT/"app/ops/prp-ops-stream.conf.example").read_text()
        vhost=(ROOT/"app/ops/prp-ops-https-vhost.conf.example").read_text()
        self.assertIn("NO-GO on the checked target",stream)
        self.assertIn("proxy_pass 127.0.0.1:18444;",stream)
        self.assertIn("proxy_pass https://127.0.0.1:18444;",vhost)
        self.assertNotIn("127.0.0.1:18443;",stream+vhost)

    def test_named_https_template_is_review_only_and_verifies_upstream(self):
        vhost=(ROOT/"app/ops/prp-ops-https-vhost.conf.example").read_text()
        for directive in ("server_name ops.invalid;","proxy_ssl_verify on;",
                "proxy_ssl_name ops.invalid;","proxy_ssl_trusted_certificate /REPLACE_WITH_APPROVED_UPSTREAM_CA;",
                "proxy_pass_request_headers on;","proxy_cache off;","proxy_next_upstream off;",
                "client_max_body_size 4k;","access_log off;",
                'if ($ssl_server_name != ops.invalid) { return 421; }',
                'if ($http_host != ops.invalid) { return 421; }',
                'if ($http_transfer_encoding != "") { return 400; }'):
            self.assertIn(directive,vhost)
        active=[line.strip() for line in vhost.splitlines() if not line.lstrip().startswith("#")]
        self.assertFalse(any("default_server" in line or "proxy_set_header Authorization" in line or
                             "proxy_ssl_verify off" in line or "rewrite " in line for line in active))
