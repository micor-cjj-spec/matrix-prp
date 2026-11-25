import configparser
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
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
        self.assertEqual(service["Unit"]["ConditionPathExists"],"/etc/matrix-prp-ops/ENABLE_LIVE_COLLECTION")
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
        self.assertEqual(timer["Unit"]["ConditionPathExists"],"/etc/matrix-prp-ops/ENABLE_LIVE_COLLECTION")
        cfg=timer["Timer"]
        self.assertEqual(cfg["OnBootSec"],"30s")
        self.assertEqual(cfg["OnUnitActiveSec"],"30s")
        self.assertEqual(cfg["AccuracySec"],"5s")
        self.assertEqual(cfg["Unit"],"prp-ops-collector.service")
        self.assertEqual(timer["Install"]["WantedBy"],"timers.target")
