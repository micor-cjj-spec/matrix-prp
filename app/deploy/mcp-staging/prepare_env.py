#!/usr/bin/env python3
"""Create owner-only staging secrets for a brand-new, separate Docker project.

No PRP production settings are read or mutated. Never displays the secrets.
"""
import argparse
import os
from pathlib import Path
import re
import secrets
from check_env import check, parse_env


def make_config(stage_host, auth_host, admin_username):
    stage_host = stage_host.lower()
    auth_host = auth_host.lower()
    values = {
        "PRP_STAGE_PUBLIC_HOST": stage_host,
        "PRP_STAGE_PUBLIC_URL": "https://" + stage_host,
        "PRP_STAGE_MCP_RESOURCE": "https://" + stage_host + "/api/mcp",
        "PRP_STAGE_AUTH_PUBLIC_URL": "https://" + auth_host,
        "PRP_STAGE_AUTH_ISSUER": "https://" + auth_host + "/realms/prp-mcp",
        "PRP_STAGE_AUTH_JWKS_URI":
            "https://" + auth_host + "/realms/prp-mcp/protocol/openid-connect/certs",
        "PRP_STAGE_DB_ROOT_PASSWORD": secrets.token_hex(32),
        "PRP_STAGE_DB_PASSWORD": secrets.token_hex(32),
        "PRP_STAGE_JWT_SECRET": secrets.token_hex(32),
        "PRP_STAGE_ADMIN_USERNAME": admin_username,
        "PRP_STAGE_ADMIN_PASSWORD": secrets.token_urlsafe(32),
        "PRP_STAGE_MCP_ENABLED": "false",
        "PRP_STAGE_OAUTH_ENABLED": "false",
    }
    check(values)
    return values


def write_secrets_file(output, values):
    data = "# Isolated PRP MCP staging ONLY; do not commit this file.\n"
    data += "".join(f"{key}={value}\n" for key, value in values.items())
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output


def main():
    p = argparse.ArgumentParser(description="Generate fresh isolated staging configuration")
    p.add_argument("--stage-host", default="prp-test.micor.top")
    p.add_argument("--auth-host", default="auth-test.micor.top")
    p.add_argument("--admin-username", default="stage_admin")
    p.add_argument("--output", type=Path, default=Path(__file__).with_name(".env"))
    args = p.parse_args()
    values = make_config(args.stage_host, args.auth_host, args.admin_username)
    write_secrets_file(args.output, values)
    print("Created staging-only secrets with mode 0600 at: " + str(args.output))
    print("MCP and OAuth remain DISABLED. Bootstrap credentials are not printed.")
    print("The operator can securely inspect the private file locally for the test login.")


if __name__ == "__main__":
    main()
