import pathlib
import sys
import unittest
import subprocess
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'release-v4'))
import linux_dns_worker as dns

def answer(kind='A',source='1.1.1.1',status='NOERROR',flags='qr rd ra',values=None):
    values=['207.57.123.94'] if values is None and kind=='A' else values or []
    return (';; ->>HEADER<<- opcode: QUERY, status: '+status+', id: 1\n;; flags: '+flags+'; QUERY: 1\n'
        ';; QUESTION SECTION:\n;micor.top. IN '+kind+'\n\n;; ANSWER SECTION:\n'+
        ''.join('micor.top. 600 IN '+kind+' '+v+'\n' for v in values)+
        '\n;; SERVER: '+source+'#53('+source+') (UDP)\n').encode()

class LinuxDnsTests(unittest.TestCase):
    def test_real_nodata_requires_successful_response(self):
        self.assertEqual(dns.parse(answer('AAAA'),'micor.top','1.1.1.1','AAAA'),[])
        for output in [b'',answer('AAAA',status='SERVFAIL'),answer('AAAA',status='NXDOMAIN')]:
            with self.assertRaises(dns.GateError):dns.parse(output,'micor.top','1.1.1.1','AAAA')

    def test_direct_a_and_source_are_checked(self):
        self.assertEqual(dns.parse(answer(),'micor.top','1.1.1.1','A'),['207.57.123.94'])
        with self.assertRaises(dns.GateError):dns.parse(answer(source='8.8.8.8'),'micor.top','1.1.1.1','A')

    def test_authority_flag_and_no_truncation(self):
        self.assertEqual(dns.parse(answer(source='8.8.8.8',flags='qr aa'),'micor.top','dns25.hichina.com','A'),['207.57.123.94'])
        for flags in ['qr','qr aa tc']:
            with self.assertRaises(dns.GateError):dns.parse(answer(flags=flags),'micor.top','dns25.hichina.com','A')

    def test_question_and_cname_not_silently_accepted(self):
        for value in [answer().replace(b';micor.top.',b';evil.invalid.'),answer().replace(b'IN A 207.57.123.94',b'IN CNAME evil.invalid.')]:
            with self.assertRaises(dns.GateError):dns.parse(value,'micor.top','1.1.1.1','A')

    def test_unapproved_inputs_never_start_process(self):
        with patch.object(dns.subprocess,'Popen') as proc:
            for host,source,kind in [('bad;id','1.1.1.1','A'),('micor.top','127.0.0.1','A'),('micor.top','1.1.1.1','TXT')]:
                with self.assertRaises(dns.GateError):dns.command(host,source,kind)
            with self.assertRaises(dns.GateError):dns.dns_linux(['micor.top'],sorted(dns.SOURCES))
            proc.assert_not_called()

    def test_shared_contract_retains_32_queries(self):
        def output(args,timeout):
            host,kind=args[2:4];source=args[1][1:]
            data=answer(kind,source if source not in dns.AUTHORITIES else '8.8.8.8',flags='qr aa' if source in dns.AUTHORITIES else 'qr rd ra')
            return data.replace(b'micor.top.',(host+'.').encode())
        with patch.object(dns,'execute',side_effect=output) as execute:
            rows=dns.dns_linux(sorted(dns.HOSTS),sorted(dns.SOURCES))
        self.assertEqual(execute.call_count,32)
        self.assertEqual(sum(len(x['queries']) for x in rows),32)

    def test_query_failure_is_not_empty_aaaa_success(self):
        with patch.object(dns,'execute',side_effect=dns.GateError('DNS_QUERY_TIMEOUT')):
            with self.assertRaises(dns.DNSFailure):dns.dns_linux(sorted(dns.HOSTS),sorted(dns.SOURCES))

    def test_timeout_kills_only_owned_process_group_and_reaps(self):
        class Child:
            pid=8123
            returncode=None
            count=0
            def communicate(self,timeout):
                self.count+=1
                if self.count==1:raise subprocess.TimeoutExpired('dig',timeout)
                self.returncode=-9
                return b'',b''
            def poll(self):return self.returncode
        child=Child()
        with patch.object(dns.sys,'platform','linux'),patch.object(dns.signal,'SIGKILL',9,create=True),patch.object(dns.subprocess,'Popen',return_value=child) as create,patch.object(dns.os,'killpg',create=True) as kill:
            with self.assertRaises(dns.GateError):dns.execute(dns.command('micor.top','1.1.1.1','A'),1)
        self.assertTrue(create.call_args.kwargs['start_new_session'])
        kill.assert_called_once_with(8123,9)
        self.assertIsNotNone(child.returncode)

if __name__=='__main__':unittest.main()
