"""Offline-only overlay on exact #424/#495, no live profiles or launcher.

The existing P4.3B materializer produces the source directory first. Work on
separate disposable copies after the unchanged direct-profile regression.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "p4_3b"))
from materialize import git_blob, replace_once

PROFILE_BLOB = "4b20104853aad16997c70fab10755b70883e9b81"
APP_BLOB = "dd113e0ecad57552d1af5668512b48ebcaf87217"
TEST_BLOB = "b3f26b333ee40ddf83cb3b98d43b7e05ccca04f8"
MATERIALIZER_BLOB = "7fa0c8276757c4dc59adafc0fc42ec298262f557"


def checked(path, expected):
    raw = path.read_bytes()
    if git_blob(raw) != expected:
        raise ValueError("source blob mismatch")
    return raw.decode("utf-8")


def adapt(ops, candidate):
    ops, candidate = Path(ops), Path(candidate)
    if ops.name != "tunnel-ops" or candidate.name != "tunnel-candidate":
        raise ValueError("separate disposable copies required")
    checked(Path(__file__).resolve().parents[1] / "p4_3b/materialize.py", MATERIALIZER_BLOB)
    profile = checked(ops / "profile_config.py", PROFILE_BLOB)
    app = checked(candidate / "profile_app.py", APP_BLOB)
    test = checked(candidate / "ci_profile.py", TEST_BLOB)
    gateway = (candidate / "owner_gateway.py").read_text()
    # Exact new schema only in this separate overlay; v1 stays in P4.3B.
    profile = replace_once(profile, '"introspectionClientId"}', '"introspectionClientId","privateOrigin"}')
    profile = replace_once(profile, '    digest: str\n', '    digest: str\n    private_origin: str\n')
    profile = replace_once(profile, 'value["version"]==1', 'value["version"]==2')
    profile = replace_once(profile,
        '    rm=re.fullmatch(r"https://("+DNS+r")/mcp",resource, re.ASCII)\n'
        '    require(im is not None and rm is not None)\n'
        '    for host in (im.group(1),rm.group(1)):',
        '''    # Only the existing legacy tunnel ID form, not a generic URL/path.
    rm=re.fullmatch(r"https://("+DNS+r")/v1/mcp/tunnel_[0-9a-f]{32}",resource,re.ASCII)
    private=value["privateOrigin"]
    require(type(private) is str)
    pm=re.fullmatch(r"https://("+DNS+r")(?::([1-9][0-9]{0,4}))?",private,re.ASCII)
    require(im is not None and rm is not None and pm is not None)
    port=pm.group(2)
    require(port is None or (int(port)<=65535 and int(port)!=443))
    for host in (im.group(1),rm.group(1),pm.group(1)):''')
    profile = replace_once(profile, '    require(im.group(1)!=rm.group(1))',
        '    require(len({im.group(1),rm.group(1),pm.group(1)})==3)')
    profile = replace_once(profile, 'hashlib.sha256(raw).hexdigest())',
        'hashlib.sha256(raw).hexdigest(),private)')
    app = replace_once(app, 'host=urlsplit(profile.identity.resource).netloc)',
        'host=urlsplit(profile.private_origin).netloc)')
    # Keep SDK resource validation, verifier, exact grant, and bounded transport.
    gateway = replace_once(gateway, '    host = urlsplit(profile.resource).netloc',
        '''    if approved is None:
        raise ValueError("tunnel approval required")
    host = urlsplit(approved.private_origin).netloc
    local_metadata = "/.well-known/oauth-protected-resource/mcp"
    sdk_metadata = "/.well-known/oauth-protected-resource" + urlsplit(profile.resource).path
    sdk_origin = "https://" + urlsplit(profile.resource).netloc
    sdk_challenge = ('resource_metadata="' + sdk_origin + sdk_metadata + '"').encode("ascii")
    private_challenge = ('resource_metadata="' + approved.private_origin + local_metadata + '"').encode("ascii")''')
    gateway = replace_once(gateway, '        await sdk_app(scope, receive, send)\n',
        '''        # Outer BoundedSDK already verifies exact raw private path and Host.
        # Only the fixed private discovery GET is internally routed to the SDK
        # generated endpoint. Never accept the external tunnel path on ingress.
        if scope.get("type") == "http" and scope.get("path") == local_metadata:
            if scope.get("method") != "GET" or scope.get("raw_path") != local_metadata.encode("ascii"):
                raise ValueError("invalid metadata route")
            scope = dict(scope, path=sdk_metadata, raw_path=sdk_metadata.encode("ascii"))
        async def private_send(event):
            if event["type"] == "http.response.start":
                headers = []
                for key, value in event.get("headers", []):
                    if key.lower() == b"www-authenticate":
                        if value.count(sdk_challenge) != 1:
                            raise ValueError("unexpected SDK challenge")
                        value = value.replace(sdk_challenge, private_challenge, 1)
                    headers.append((key, value))
                event = dict(event, headers=headers)
            await send(event)
        await sdk_app(scope, receive, private_send)
''')
    # Reuse all original live SDK + mocked issuer checks with only fixture
    # configuration changed and negative cases added. No duplicate fixture.
    test = replace_once(test, 'from profile_config import approved_profile',
        'from profile_config import approved_profile, parse_profile')
    test = replace_once(test, 'RESOURCE = "https://ops.example.net/mcp"',
        'RESOURCE = "https://tunnel.example.net/v1/mcp/tunnel_" + "a"*32\n'
        'PRIVATE = "https://ops.example.net:18444"\nHOST = "ops.example.net:18444"')
    test = replace_once(test, 'dict(version=1, environment="staging", issuer=ISSUER,',
        'dict(version=2, environment="staging", issuer=ISSUER, privateOrigin=PRIVATE,')
    test = replace_once(test, 'base_url="https://ops.example.net"', 'base_url=PRIVATE')
    test = replace_once(test, '"Host":"ops.example.net"', '"Host":HOST')
    test = replace_once(test, 'RESOURCE.rsplit("/",1)[0] in unauthorized.headers.get("www-authenticate","")',
        '("resource_metadata=\\"" + PRIVATE + "/.well-known/oauth-protected-resource/mcp\\"") in unauthorized.headers.get("www-authenticate","")')
    test = replace_once(test, '        install("profile.json", raw)\n',
        '''        # Strict shape, canonical authority, no arbitrary external path.
        original = json.loads(raw)
        for key, value in (
            ("version", 1), ("resource", RESOURCE + "/"),
            ("resource", RESOURCE + "?x=1"), ("resource", RESOURCE + "#x"),
            ("resource", RESOURCE.replace("tunnel_", "other_")),
            ("resource", RESOURCE.replace("/v1/mcp/", "/mcp/")),
            ("resource", RESOURCE.replace("https:", "http:")),
            ("resource", RESOURCE.replace("tunnel.example.net", "user@tunnel.example.net")),
            ("privateOrigin", PRIVATE + "/mcp"), ("privateOrigin", "https://*.example.net"),
            ("privateOrigin", "https://ops.example.net:65536"),
            ("privateOrigin", "https://ops.example.net:443"),
            ("privateOrigin", "https://tunnel.example.net"),
            ("privateOrigin", "https://issuer.example.net"),
        ):
            try:
                parse_profile(json.dumps({**original, key: value}).encode())
            except ValueError:
                check(True, "reject-profile-" + key)
            else:
                raise AssertionError("invalid tunnel profile accepted")
        install("profile.json", raw)
''')
    test = replace_once(test, '                install("grant.json",plan(grant_raw,',
        '''                for bad_aud in ([RESOURCE, PRIVATE + "/mcp"],
                                [PRIVATE + "/mcp"], [RESOURCE[:-1] + "b"],
                                RESOURCE + "/"):
                    claims["aud"] = bad_aud
                    check(call().status_code==401 and len(calls)==1,"deny-nonexact-tunnel-aud")
                claims["aud"] = [RESOURCE]
                check(call({**headers,"Host":"tunnel.example.net"}).status_code==400
                      and len(calls)==1,"external-host-denied")
                check(call({**headers,"Host":"ops.example.net"}).status_code==400
                      and len(calls)==1,"wrong-private-port-denied")
                check(call(list(headers.items())+[("Host",HOST)]).status_code==400
                      and len(calls)==1,"duplicate-host-denied")
                check(call({**headers,"Host":"foreign.example.net","X-Forwarded-Host":HOST}).status_code==400
                      and len(calls)==1,"forwarded-host-cannot-override")
                check(client.get("/.well-known/oauth-protected-resource/v1/mcp/tunnel_"+"a"*32).status_code==400
                      and client.post("/v1/mcp/tunnel_"+"a"*32,headers=headers,json={}).status_code==400
                      and len(calls)==1,"external-path-not-ingress")
                check(client.get("/.well-known/oauth-protected-resource/mcp",headers={"Host":"tunnel.example.net"}).status_code==400,
                      "metadata-host-denied")
                # A private-host change is part of root approval, not mutable
                # transport input. No token or grant may authorize it alone.
                install("profile.json",json.dumps({**original,"privateOrigin":"https://other.example.net:18444"}).encode())
                check(call().status_code==503 and len(calls)==1,"private-origin-digest-change-denied")
                install("profile.json",raw)
                install("grant.json",plan(grant_raw,''')
    test = replace_once(test, 'OBS_P43B_PROFILE=PASS; LIVE_ISSUER_TUNNEL=NOT_ENABLED',
        'OBS_P43C3_TUNNEL_PROFILE=PASS; LIVE_ISSUER_TUNNEL=NOT_ENABLED')
    for path, content in ((ops / "profile_config.py", profile),
                          (candidate / "profile_app.py", app),
                          (candidate / "owner_gateway.py", gateway),
                          (candidate / "ci_profile.py", test)):
        compile(content, str(path), "exec")
        path.write_text(content)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(2)
    adapt(*sys.argv[1:])
