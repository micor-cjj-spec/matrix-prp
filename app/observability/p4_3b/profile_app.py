"""Profile composition only. No launcher, installer or actual credentials.

Trusted caller must separately provision reviewed root-owned profile, grant,
upstream and audit. Default profile reader is exact #424 approval gate.
"""
from urllib.parse import urlsplit
from auth_adapter import GrantFile, IntrospectionClient
from profile_config import approved_profile, ApprovedProfile
from query_contract import FIXTURE_PROFILE, Policy, require
from http_boundary import Budget
from owner_gateway import OwnerBoundGrafanaGateway, build_app
from bounded_sdk import BoundedSDK


def compose(*, grants, query_adapter, audit_sink, secret_reader, clock, store,
            read_profile=approved_profile):
    profile = read_profile()
    require(type(profile) is ApprovedProfile and profile.identity != FIXTURE_PROFILE
            and type(grants) is GrantFile and grants.profile == profile.identity)
    grants.current()
    def enabled():
        try:
            return read_profile() == profile
        except Exception:
            return False
    require(enabled())
    introspect = IntrospectionClient(profile.client_id, secret_reader(), profile=profile.identity)
    server = dict(policy=Policy(True), profile=profile.identity, grants=grants,
                  introspect=introspect, trusted_clock=clock, store=store)
    gateway = OwnerBoundGrafanaGateway(server=server, query_adapter=query_adapter,
                audit_sink=audit_sink, budget=Budget(), disclosure_check=enabled)
    require(enabled())
    return BoundedSDK(build_app(gateway, server, approved=profile), enabled,
                      host=urlsplit(profile.identity.resource).netloc)
