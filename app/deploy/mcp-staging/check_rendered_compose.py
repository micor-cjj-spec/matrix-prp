#!/usr/bin/env python3
"""Validate resolved, non-secret *shape* of staged Compose. No containers start.

This subprocess captures the entire rendered Compose JSON privately. It
NEVER prints the configuration, env values, credentials or failing stderr.
"""
import argparse
import json
from pathlib import Path
import subprocess
from check_env import check, parse_env


def validate(compose, config):
    checked = check(config)
    backend = compose["services"]["backend"]["environment"]
    gateway = compose["services"]["gateway"]["build"]["args"]
    assert backend["MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_ENABLED"] == (
        "true" if checked["first_party_enabled"] else "false"
    ), "STAGE_PKCE_ENABLE_MISMATCH"
    assert backend["MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_CLIENT_ID"] == (
        config.get("PRP_STAGE_FIRST_PARTY_CLIENT_ID") or ""
    ), "STAGE_PKCE_CLIENT_MISMATCH"
    assert backend["MATRIX_PRP_MCP_OAUTH_FIRST_PARTY_LINK_REDIRECT_URI"] == (
        config.get("PRP_STAGE_FIRST_PARTY_REDIRECT_URI") or ""
    ), "STAGE_PKCE_CALLBACK_MISMATCH"
    assert gateway["VITE_MCP_FIRST_PARTY_AUTHORIZATION_ENDPOINT"] == (
        config["PRP_STAGE_AUTH_ISSUER"] + "/protocol/openid-connect/auth"
    ), "STAGE_KEYCLOAK_ISSUER_BUILD_MISMATCH"
    assert backend["MATRIX_PRP_MCP_WRITE_ENABLED"] == "false", "STAGE_MCP_WRITE_MUST_BE_OFF"
    assert compose["services"]["gateway"]["ports"][0]["published"] == "18081", (
        "STAGE_GATEWAY_PORT_CHANGED"
    )
    assert compose["services"]["gateway"]["ports"][0]["host_ip"] == "127.0.0.1", (
        "STAGE_GATEWAY_EXPOSED_PUBLICLY"
    )


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--env-file", type=Path, required=True)
    args = cli.parse_args()
    env = parse_env(args.env_file.read_text(encoding="utf-8"))
    check(env)
    command = ["docker", "compose", "--env-file", str(args.env_file),
               "-f", str(Path(__file__).with_name("compose.yaml")),
               "config", "--format", "json"]
    try:
        p = subprocess.run(command, capture_output=True, text=True,
                           check=False, timeout=30)
        if p.returncode:
            raise ValueError("COMPOSE_PRIVATE_RENDER_FAILED")
        resolved = json.loads(p.stdout)
        validate(resolved, env)
    except (OSError, ValueError, AssertionError, KeyError, IndexError,
            TypeError, subprocess.TimeoutExpired) as exc:
        # Never render subprocess stdout/stderr or the exception payload.
        raise SystemExit("FAIL: staging Compose configuration contract not met") from None
    print("PASS: parsed Compose first-party PKCE stage remains default-OFF, "
          "pins issuer/client/callback, has no MCP writes, and binds loopback.")


if __name__ == "__main__":
    main()
