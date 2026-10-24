"""Review-only per-phase context reuse; every probe still opens fresh TLS.

Contexts are thread-local and keyed by immutable SAN/ALPN policy. No cached
socket, TLS session argument, evidence, response or certificate verdict.
Original reviewed probe source bytes are never changed or monkey-patched.
"""
import hashlib
import importlib.util
from pathlib import Path
import ssl
import threading

ORIGINAL_PROBE_SHA256='c64c0c12a0b96c134814351769206ec2af0d0b4bf41353cbfc37b8db822ab92a'


class ContextPlan:
    def __init__(self,cache):
        self.cache=cache
        self.check_hostname=True
        self.alpn=()

    def set_alpn_protocols(self,protocols):
        self.alpn=tuple(protocols)

    def wrap_socket(self,*args,**kwargs):
        # Only the exact immutable worker call shape is supported. In
        # particular, no explicit session or disabled handshake is accepted.
        if len(args)!=1 or set(kwargs)!={'server_hostname'}:
            raise ValueError('ONLY_REVIEWED_FRESH_HANDSHAKE_ALLOWED')
        return self.cache.context(self.check_hostname,self.alpn).wrap_socket(*args,**kwargs)


class ContextCache:
    def __init__(self,factory=ssl.create_default_context):
        self.factory=factory
        self.local=threading.local()

    def create_default_context(self,*args,**kwargs):
        if args or kwargs:return self.factory(*args,**kwargs)
        return ContextPlan(self)

    def context(self,hostname,alpn):
        if type(hostname) is not bool or alpn not in {('http/1.1',),('h2','http/1.1')}:
            raise ValueError('UNREVIEWED_TLS_POLICY')
        contexts=getattr(self.local,'contexts',None)
        if contexts is None:contexts={};self.local.contexts=contexts
        key=(hostname,alpn)
        if key not in contexts:
            context=self.factory()
            if context.verify_mode!=ssl.CERT_REQUIRED or not context.check_hostname:
                raise ValueError('PUBLIC_CERTIFICATE_VERIFICATION_REQUIRED')
            context.check_hostname=hostname
            context.set_alpn_protocols(list(alpn))
            contexts[key]=context
        context=contexts[key]
        if context.verify_mode!=ssl.CERT_REQUIRED or context.check_hostname is not hostname:
            raise ValueError('TLS_CONTEXT_POLICY_DRIFT')
        return context

    def __getattr__(self,name):
        # Original probes still catch the real stdlib certificate/TLS exceptions.
        return getattr(ssl,name)


def load_probes(source_path):
    path=Path(source_path)
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=ORIGINAL_PROBE_SHA256:
        raise ValueError('IMMUTABLE_PROBE_SOURCE_REQUIRED')
    spec=importlib.util.spec_from_file_location('_prp_per_phase_context_probe',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ssl=ContextCache()
    return module
