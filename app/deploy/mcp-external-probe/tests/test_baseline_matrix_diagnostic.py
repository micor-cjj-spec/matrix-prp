"""Virtual baseline telemetry; no requests, credentials or acceptance proof."""
import json
import datetime
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'release-v4'))
import baseline_matrix_diagnostic as diagnostic
from guard_release_engine import GateError,utc

class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads((Path(__file__).resolve().parent.parent/'release-v4/manifest.candidate.json').read_text())

    def test_parent_change_refused_before_network(self):
        self.manifest['max_observation_age_seconds']=301
        with patch.object(diagnostic,'dns_linux') as dns:
            with self.assertRaises(GateError):diagnostic.diagnose(self.manifest)
            dns.assert_not_called()

    def test_full_matrix_is_always_diagnostic_and_uses_two_workers(self):
        def schedule(requests,probe,deadline,concurrency):
            self.assertEqual(len(requests),682);self.assertEqual(concurrency,2)
            for spec in requests.values():probe(spec)
        def probe(spec,isolated):
            self.assertFalse(isolated)
            return {'started_utc':utc(),'error':None,'body':'SECRET-CANARY'}
        with patch.object(diagnostic,'validate'),patch.object(diagnostic,'dns_linux',return_value=[]),patch.object(diagnostic,'schedule',side_effect=schedule),patch.object(diagnostic,'http_probe',side_effect=probe),patch.object(diagnostic,'tls_probe',side_effect=probe),patch.object(diagnostic,'h2_probe',side_effect=probe):
            result=diagnostic.diagnose(self.manifest)
        self.assertEqual(result['completed_requests'],682)
        self.assertFalse(result['production_acceptance']);self.assertFalse(result['root_job_used'])
        self.assertNotIn('SECRET',json.dumps(result))

    def test_arbitrary_exception_message_never_exported(self):
        with patch.object(diagnostic,'validate'),patch.object(diagnostic,'dns_linux',side_effect=RuntimeError('TOKEN-SECRET')):
            result=diagnostic.diagnose(self.manifest)
        self.assertEqual(result['failure_type'],'OTHER_EXCEPTION')
        self.assertNotIn('SECRET',json.dumps(result));self.assertFalse(result['production_acceptance'])

    def test_stale_telemetry_never_becomes_acceptable(self):
        stamp=datetime.datetime.fromtimestamp(time.time()-301,datetime.timezone.utc).isoformat()
        def schedule(requests,probe,deadline,concurrency):probe(next(iter(requests.values())))
        def probe(spec,isolated):return {'started_utc':stamp,'error':None}
        with patch.object(diagnostic,'validate'),patch.object(diagnostic,'dns_linux',return_value=[{'utc':stamp}]),patch.object(diagnostic,'schedule',side_effect=schedule),patch.object(diagnostic,'http_probe',side_effect=probe):
            result=diagnostic.diagnose(self.manifest)
        self.assertEqual(result['stale_request_count'],1);self.assertEqual(result['stale_dns_rows'],1)
        self.assertEqual(result['freshness_limit_seconds'],300)
        self.assertFalse(result['production_acceptance'])

    def test_partial_deadline_keeps_completed_telemetry_without_retry(self):
        def schedule(requests,probe,deadline,concurrency):
            probe(next(iter(requests.values())))
            raise TimeoutError('SECRET-CANARY')
        with patch.object(diagnostic,'validate'),patch.object(diagnostic,'dns_linux',return_value=[]),patch.object(diagnostic,'schedule',side_effect=schedule) as scheduler,patch.object(diagnostic,'http_probe',return_value={'started_utc':utc(),'error':'SECRET-CANARY'}):
            result=diagnostic.diagnose(self.manifest)
        self.assertEqual(result['completed_requests'],1)
        self.assertEqual(result['transport_error_counts'],{'OTHER_ERROR':1})
        self.assertEqual(result['failure_type'],'TimeoutError')
        self.assertNotIn('SECRET',json.dumps(result));scheduler.assert_called_once()

if __name__=='__main__':unittest.main()
