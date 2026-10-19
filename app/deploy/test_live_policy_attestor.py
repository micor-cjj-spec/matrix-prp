import base64,contextlib,copy,hashlib,importlib.util,io,json,os,struct,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import live_policy_attestor as policy
from build_policy_helper import bundle

class LivePolicyAttestorTests(unittest.TestCase):
    def test_bundled_legacy_diagnostic_stays_byte_for_byte_unchanged_before_entry(self):
        root=Path(__file__).parent
        original=(root/'read_only_diagnostic.py').read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),'bc4ba21b4efaa40efe149f9a36a553af462bb860d1dbe6b53d03abb5b735588c')
        data=bundle().decode()
        self.assertEqual(data.split('# Legacy log classifier retained; policy entry point is below.')[0],original.split('if __name__ == "__main__":')[0])
        compile(data,'candidate','exec')

    def test_challenge_accepts_only_eof_or_exact_32_bytes(self):
        for value in [b'',b'\0'*32,b'x'*32]:
            read,write=os.pipe();os.write(write,value);os.close(write)
            try:self.assertEqual(policy.read_challenge(read),value)
            finally:os.close(read)
        for value in [b'x',b'x'*31,b'x'*33,b'x'*100]:
            read,write=os.pipe();os.write(write,value);os.close(write)
            try:
                with self.assertRaises(policy.CollectionError):policy.read_challenge(read)
            finally:os.close(read)

    def test_open_stdin_does_not_hold_root_helper_indefinitely(self):
        read,write=os.pipe();os.write(write,b'x'*32)
        try:
            with self.assertRaisesRegex(policy.CollectionError,'CHALLENGE_TIMEOUT'):policy.read_challenge(read,seconds=.08)
        finally:os.close(read);os.close(write)

    def test_authorized_key_must_be_one_exact_restricted_ed25519_key(self):
        blob=struct.pack('>I',11)+b'ssh-ed25519'+struct.pack('>I',32)+b'x'*32
        line=b'restrict,command="/usr/local/bin/prp-deploy-gateway" ssh-ed25519 '+base64.b64encode(blob)+b' test\n'
        expected='SHA256:'+base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')
        self.assertEqual(policy.deployment_key(line),expected)
        for bad in [line+line,line.replace(b'restrict,',b''),line.replace(b'restrict,',b'restrict,port-forwarding,'),line.replace(b'gateway"',b'gateway unexpected"'),line.replace(b'ssh-ed25519 ',b'ssh-rsa ')]:
            with self.subTest(case=bad[:30]),self.assertRaises(policy.CollectionError):policy.deployment_key(bad)

    def fixture(self):
        chain=[{'pid':12,'exe':policy.SESSION,'start_ticks':100,'uids':(0,0,0,0),'parent':10}]
        endpoint=('192.0.2.1',22,'198.51.100.2',40000)
        key='SHA256:'+'A'*43
        record={'_PID':'12','_UID':'0','_EXE':policy.SESSION,'_BOOT_ID':'boot','_SYSTEMD_UNIT':'ssh.service',
                '_SYSTEMD_INVOCATION_ID':'a'*32,'__MONOTONIC_TIMESTAMP':'1500000','__REALTIME_TIMESTAMP':'150000000','MESSAGE':'Accepted publickey for prp-deploy from 198.51.100.2 port 40000 ssh2: ED25519 '+key}
        return chain,endpoint,key,record

    def test_authentication_is_bound_to_kernel_ancestor_and_socket_and_trusted_journal(self):
        chain,endpoint,key,record=self.fixture()
        with patch.object(policy,'process_birth',return_value=100):
            self.assertEqual(policy.journal_binds([record],chain,endpoint,key,'boot',200,'a'*32,200),chain[0])
            mutations={'_PID':'99','_UID':'1001','_EXE':'/usr/bin/logger','_BOOT_ID':'other',
                       '_SYSTEMD_UNIT':'other.service','_SYSTEMD_INVOCATION_ID':'b'*32,'__MONOTONIC_TIMESTAMP':'0','__REALTIME_TIMESTAMP':'1',
                       'MESSAGE':record['MESSAGE'].replace('40000','40001')}
            for field,value in mutations.items():
                candidate={**record,field:value}
                with self.subTest(field=field),self.assertRaises(policy.CollectionError):policy.journal_binds([candidate],chain,endpoint,key,'boot',200,'a'*32,200)
            with self.assertRaises(policy.CollectionError):policy.journal_binds([],chain,endpoint,key,'boot',200,'a'*32,200)
            with self.assertRaises(policy.CollectionError):policy.journal_binds([record],chain,endpoint,key+'B','boot',200,'a'*32,200)

    def test_loaded_configuration_requires_file_and_glob_directory_ctime_before_daemon(self):
        self.assertTrue(policy.loaded_configuration([{'ctime':1_000_000_000},{'ctime':2_000_000_000}],3))
        for records in [[],[{'ctime':4_000_000_000}],[{'missing':True}],[{}],[{'ctime':2_990_000_000}]]:
            with self.subTest(records=records),self.assertRaises(policy.CollectionError):policy.loaded_configuration(records,3)

    def test_journal_boot_generation_requires_current_master_invocation_and_kernel_birth(self):
        master={'pid':721,'start_ticks':100}
        birth=100/os.sysconf('SC_CLK_TCK')
        entry={'_UID':'0','_EXE':policy.SSHD,'_PID':'721','_SYSTEMD_UNIT':'ssh.service',
               '_SYSTEMD_INVOCATION_ID':'a'*32,'_BOOT_ID':'b'*32,
               '__MONOTONIC_TIMESTAMP':str(int((birth+.1)*1e6)),'MESSAGE':'Server listening on 192.0.2.1 port 22.'}
        self.assertEqual(policy.journal_generation([entry],master,'a'*32),'b'*32)
        mutations={'_UID':'1001','_EXE':'/usr/bin/logger','_PID':'722','_SYSTEMD_UNIT':'other.service',
                   '_SYSTEMD_INVOCATION_ID':'c'*32,'_BOOT_ID':'bad','__MONOTONIC_TIMESTAMP':'0',
                   'MESSAGE':'Untrusted result'}
        for key,value in mutations.items():
            with self.subTest(key=key),self.assertRaises(policy.CollectionError):
                policy.journal_generation([{**entry,key:value}],master,'a'*32)
        for entries in [[],[entry,{**entry,'_BOOT_ID':'c'*32}],[{**entry,'__MONOTONIC_TIMESTAMP':str(int((birth+20)*1e6))}]]:
            with self.assertRaises(policy.CollectionError):policy.journal_generation(entries,master,'a'*32)

    def daemon_fixture(self, drift=0, uptime=128800, kernel_birth=10, saved_mono=10,
                       domain_offset=0, saved=b't 100000000', mono_raw=None):
        def command(args):
            if args[-1]=='ExecMainStartTimestamp':return saved
            return mono_raw if mono_raw is not None else ('t '+str(int(saved_mono*1e6))).encode()
        def clock(which):
            return 10+uptime+(domain_offset if which==time.CLOCK_BOOTTIME else 0)
        with patch.object(policy,'bounded_command',side_effect=command), \
             patch.object(policy.time,'clock_gettime',side_effect=clock), \
             patch.object(policy.time,'time',return_value=100+uptime+drift), \
             patch.object(policy.os,'sysconf',return_value=100):
            return policy.daemon_birth({'start_ticks':int(kernel_birth*100)})

    def test_saved_daemon_birth_accepts_observed_ntp_slew_without_moving_boundary(self):
        self.assertAlmostEqual(self.daemon_fixture(drift=.519239),99.98)
        self.assertAlmostEqual(self.daemon_fixture(drift=-.519239),99.460761)
        self.assertAlmostEqual(self.daemon_fixture(),99.98)

    def test_wrong_monotonic_generation_still_fails_even_when_wall_time_matches(self):
        for values in [{'kernel_birth':11},{'saved_mono':11},{'saved_mono':0}]:
            with self.subTest(values=values),self.assertRaises(policy.CollectionError):self.daemon_fixture(**values)

    def test_large_wall_discontinuities_and_suspend_clock_domains_fail_closed(self):
        for values in [{'drift':1000},{'drift':-1000},{'drift':1,'uptime':10},
                       {'domain_offset':10},{'domain_offset':-10}]:
            with self.subTest(values=values),self.assertRaisesRegex(policy.CollectionError,'SSH_CLOCK_GENERATION_UNPROVEN'):
                self.daemon_fixture(**values)

    def test_missing_malformed_or_zero_systemd_start_properties_fail_closed(self):
        for raw in [b'',b't 0',b's 100',b't nan',b't -1',b't 100\nt 200',b't '+b'9'*21]:
            for argument in ['saved','mono_raw']:
                with self.subTest(raw=raw,argument=argument),self.assertRaises(policy.CollectionError):
                    self.daemon_fixture(**{argument:raw})

    def test_loaded_policy_still_rejects_post_start_config_after_clock_fix(self):
        boundary=self.daemon_fixture(drift=.519239)
        self.assertTrue(policy.loaded_configuration([{'ctime':50_000_000_000}],boundary))
        for records in [[{'ctime':100_000_000_000}],[{'ctime':101_000_000_000}],
                        [{'ctime':99_970_000_000}],[],[{'missing':True}]]:
            with self.subTest(records=records),self.assertRaisesRegex(policy.CollectionError,'SSH_LOADED_POLICY_UNPROVEN'):
                policy.loaded_configuration(records,boundary)

    def test_real_linux_interpreter_symlink_is_read_only_and_root_controlled(self):
        if not Path('/usr/bin/python3').exists():self.skipTest('Linux interpreter fixture absent')
        record=policy.trusted_record('/usr/bin/python3')
        self.assertTrue(policy.record_is_trusted(record))

    def test_group_writable_or_unprivileged_synthetic_metadata_cannot_pass(self):
        record={'uid':0,'mode':0o755,'parents':[['/',0,0,0o777,None]]}
        self.assertFalse(policy.record_is_trusted(record))
        link={'uid':1001,'target':{'uid':0,'mode':0o755,'parents':[]},'parents':[]}
        self.assertFalse(policy.record_is_trusted(link))

    def test_kernel_socket_address_decoding(self):
        self.assertEqual(policy.decode_address('0100007F:0016',False),('127.0.0.1',22))
        self.assertEqual(policy.decode_address('0000000000000000FFFF00000100007F:0016',True),('127.0.0.1',22))

    def test_file_metadata_cannot_turn_untrusted_owner_or_writable_path_into_pass(self):
        record={'uid':0,'mode':0o755,'parents':[['/',0,0,0o755,None]]}
        self.assertTrue(policy.record_is_trusted(record))
        for candidate in [{**record,'uid':1001},{**record,'mode':0o777},{**record,'parents':[['/unsafe',1001,1001,0o755,None]]}]:
            self.assertFalse(policy.record_is_trusted(candidate))

    def test_process_failure_output_limits_and_timeouts_fail_closed_without_exposing_output(self):
        for command,code in [([sys.executable,'-c','raise SystemExit(1)'],'POLICY_COMMAND_FAILED'),
                             ([sys.executable,'-c','print("x"*5000)'],'POLICY_COMMAND_OUTPUT_LIMIT'),
                             ([sys.executable,'-c','import time;time.sleep(10)'],'POLICY_COMMAND_TIMEOUT')]:
            with self.subTest(code=code),self.assertRaisesRegex(policy.CollectionError,code):policy.bounded_command(command,seconds=.2,limit=4096)

    def test_unverifiable_collection_emits_only_fixed_redacted_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'candidate.py';path.write_bytes(bundle())
            spec=importlib.util.spec_from_file_location('bundled',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            output=io.StringIO()
            with patch.object(module.os,'geteuid',return_value=0),patch.object(module.sys,'argv',['diagnose']),patch.object(module,'read_challenge',return_value=b'x'*32),patch.object(module,'report',return_value={}),patch.object(module,'collect_policy',side_effect=RuntimeError('PRIVATE_TOKEN_PEER_ADDRESS')),contextlib.redirect_stdout(output):
                self.assertEqual(module.policy_main(),2)
            self.assertEqual(json.loads(output.getvalue()),{'schema_version':1,'policy_error':'SSH_POLICY_UNVERIFIED'})
            self.assertNotIn('PRIVATE_TOKEN',output.getvalue())

    def test_legacy_eof_does_not_invoke_policy_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'candidate.py';path.write_bytes(bundle())
            spec=importlib.util.spec_from_file_location('bundled_legacy',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            output=io.StringIO()
            with patch.object(module.os,'geteuid',return_value=0),patch.object(module.sys,'argv',['diagnose']),patch.object(module,'read_challenge',return_value=b''),patch.object(module,'report',return_value={'schema_version':1,'state':'no_log'}),patch.object(module,'collect_policy') as collect,contextlib.redirect_stdout(output):
                self.assertEqual(module.policy_main(),0)
                collect.assert_not_called()
            self.assertEqual(json.loads(output.getvalue()),{'schema_version':1,'state':'no_log'})

if __name__=='__main__':unittest.main()
