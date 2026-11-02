#!/usr/bin/env python3
"""Fail-closed preflight for future real-Nginx V2 guard tests in a NEW netns.

No host nginx start/reload, no Docker use, no remote traffic, no config edits.
Unshare probe creates a short-lived empty network namespace only.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import audit_v2_route_semantics as semantic
import isolated_v2_nginx_syntax as pinned

def check_host(binaries=None, runner=None):
    binaries = binaries if binaries is not None else shutil.which
    runner = runner if runner is not None else subprocess.run
    # Confirm the pinned candidate pair still passes the no-network gate.
    inventory = semantic.inspect()
    site = inventory["test"]
    if (site["v2_behind_non_exact_locations"] != 0 or
            site["v2_proxy_directives"] != 2 or
            site["broad_prefix_with_proxy"] != 0 or
            site["nonloopback_or_variable_upstream_directives"] != 0):
        raise ValueError("TEST_VHOST_ROUTE_ENVELOPE_CHANGED")
    tools = {key: binaries(key) for key in
             ("unshare", "ip", "nginx", "openssl", "python3")}
    result = {
        "status": "ISOLATED_NETNS_PREFLIGHT_BLOCKED",
        "pinned_sources_verified": True,
        "test_broad_proxy_count": site["broad_prefix_with_proxy"],
        "test_nonloopback_or_variable_upstreams": site[
            "nonloopback_or_variable_upstream_directives"],
        "all_required_binaries_present": all(tools.values()),
        "unshare_netns_available": False,
        "host_nginx_started_or_reloaded": False,
        "host_network_configuration_changed": False,
        "public_or_api_requests_executed": False,
        "release_approved": False,
    }
    if not all(tools.values()):
        result["blocker"] = "REQUIRED_LOCAL_BINARY_MISSING"
        result["missing_binary_count"] = sum(not path for path in tools.values())
        return result
    # This process immediately exits without opening sockets, routes or
    # interfaces in the test namespace, and cannot mutate the host namespace.
    try:
        probe = runner(
            [tools["unshare"], "--net", "--fork", "/bin/true"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=6, check=False)
    except subprocess.TimeoutExpired:
        result["blocker"] = "NEW_NETWORK_NAMESPACE_PROBE_TIMEOUT"
        return result
    if probe.returncode:
        result["blocker"] = "NEW_NETWORK_NAMESPACE_NOT_PERMITTED"
        return result
    result["unshare_netns_available"] = True
    result["status"] = "ISOLATED_NETNS_PREFLIGHT_READY"
    result["blocker"] = None
    return result

if __name__ == "__main__":
    try:
        data = check_host()
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError) as error:
        data = {
            "status": "ISOLATED_NETNS_PREFLIGHT_BLOCKED",
            "blocker": str(error) if isinstance(error, ValueError) else
                       type(error).__name__,
            "host_nginx_started_or_reloaded": False,
            "host_network_configuration_changed": False,
            "public_or_api_requests_executed": False,
            "release_approved": False,
        }
    print(json.dumps(data, indent=2, sort_keys=True))
    if data["status"] != "ISOLATED_NETNS_PREFLIGHT_READY":
        sys.exit(2)
