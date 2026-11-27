"""Deterministic minimal adaptation of exact accepted source, offline only.

No modification to accepted PRs. Generate reviewable candidate modules in a
disposable directory; never install them or change real configuration.
"""
import hashlib
from pathlib import Path
import sys

GATEWAY_BLOB = "9898d0102fb75bf538a1eadfea5c25dbb300e826"
RUNTIME_BLOB = "a8442994f4e52ba6b5189d9ddeb60f0c4b019b57"


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError("accepted source anchor mismatch")
    return source.replace(before, after)


def materialize(gateway_path, runtime_path, destination):
    gateway_raw = Path(gateway_path).read_bytes()
    runtime_raw = Path(runtime_path).read_bytes()
    if git_blob(gateway_raw) != GATEWAY_BLOB or git_blob(runtime_raw) != RUNTIME_BLOB:
        raise ValueError("accepted source blob mismatch")
    g = gateway_raw.decode("utf-8")
    g = replace_once(g, "def build_app(gateway, server):",
        "def build_app(gateway, server, *, approved=None):")
    g = replace_once(g,
        '    if profile != FIXTURE_PROFILE:\n        raise ValueError("only the offline fixture profile is supported")',
        '''    from profile_config import ApprovedProfile
    from urllib.parse import urlsplit
    if profile == FIXTURE_PROFILE:
        if approved is not None:
            raise ValueError("fixture cannot use live approval")
    elif type(approved) is not ApprovedProfile or approved.identity != profile:
        raise ValueError("approved identity required")
    if gateway._server != server:
        raise ValueError("identity configuration mismatch")
    host = urlsplit(profile.resource).netloc''')
    g = replace_once(g, 'allowed_hosts=["ops.invalid"],', 'allowed_hosts=[host],')
    # #494 transport remains unchanged apart from a fixed server-owned host.
    rt = runtime_raw.decode("utf-8")
    rt = replace_once(rt, 'def __init__(self, app, enabled):\n        self.app, self.enabled = app, enabled',
        '''def __init__(self, app, enabled, *, host="ops.invalid"):
        self.app, self.enabled = app, enabled
        self.host = host''')
    rt = replace_once(rt, 'headers.get("host") != "ops.invalid"', 'headers.get("host") != self.host')
    # Exclude synthetic launcher and credentials from the profile candidate.
    # Keep only the actual bounded transport classes and their fixed imports.
    start = rt.index("class RequestRejected(ValueError):")
    end = rt.index("\ndef main():", start)
    bounded = '''"""Exact #494 bounded SDK transport with server-pinned host."""
import asyncio
from asgi_runtime import extract_scope, send_response, MAX_BODY_EVENTS, SEND_SECONDS
from http_boundary import parse_headers, response, MAX_RESPONSE, CONCURRENCY
from query_contract import require
from rpc_adapter import MAX_RPC
DEADLINE = 8

''' + rt[start:end]
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=False)
    (dest / "owner_gateway.py").write_text(g)
    (dest / "bounded_sdk.py").write_text(bounded)



# Exact 32-distribution version lock from the previously green dependency job.
# Hash receipts are obtained from PyPI for the selected Linux x64 CPython wheel
# and recorded by CI; they are not pre-approved immutable hashes.
RUNTIME_LOCK = """annotated-types==0.8.0
anyio==4.16.0
attrs==26.1.0
certifi==2026.11.20
cffi==2.1.1
click==8.5.1
cryptography==50.0.2
h11==0.16.0
httpcore==1.0.9
httpcore2==2.16.2
httpx==0.28.1
httpx2==2.16.2
idna==3.20
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
mcp==2.3.0
mcp-types==2.3.0
opentelemetry-api==1.45.2
pip==26.3
pycparser==3.12
pydantic==2.14.4
pydantic-core==2.50.5
pyjwt==2.15.1
python-multipart==0.0.34
referencing==0.37.0
rpds-py==2026.9.1
sse-starlette==3.7.1
starlette==1.10.0
truststore==0.10.5
typing-extensions==4.16.0
typing-inspection==0.4.5
uvicorn==0.54.0"""


def install_locked(venv):
    """Hosted CI only: version-locked wheelhouse, hash-verified offline install."""
    import json
    import os
    import re
    import subprocess
    import tempfile
    import urllib.request
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise SystemExit("disposable hosted CI only")
    python = str(Path(venv).resolve() / "bin/python")
    norm = lambda s: re.sub(r"[-_.]+", "-", s).lower()
    expected = dict(line.split("==") for line in RUNTIME_LOCK.splitlines())
    if len(expected) != 32:
        raise ValueError("runtime lock size")
    def pip(*args):
        subprocess.run([python, "-m", "pip", "--isolated", *args], check=True)
    with tempfile.TemporaryDirectory(prefix="p43b-wheels-") as temp:
        work = Path(temp)
        wheels = work / "wheels"
        wheels.mkdir()
        versions = work / "versions.txt"
        versions.write_text(RUNTIME_LOCK + "\n")
        pip("download", "--index-url", "https://pypi.org/simple", "--no-cache-dir",
            "--only-binary=:all:", "--no-deps", "--dest", str(wheels), "-r", str(versions))
        hashes = {}
        for wheel in sorted(wheels.iterdir()):
            if not wheel.is_file() or not wheel.name.endswith(".whl"):
                raise ValueError("non-wheel dependency")
            name, version = wheel.name.split("-")[:2]
            name = norm(name)
            if expected.get(name) != version or name in hashes:
                raise ValueError("wheel does not match exact version lock")
            sha = hashlib.file_digest(wheel.open("rb"), "sha256").hexdigest()
            with urllib.request.urlopen(
                    "https://pypi.org/pypi/" + name + "/" + version + "/json",
                    timeout=20) as response:
                metadata = json.load(response)
            matches = [x for x in metadata["urls"] if x["filename"] == wheel.name
                       and x["packagetype"] == "bdist_wheel" and not x["yanked"]]
            if len(matches) != 1 or matches[0]["digests"]["sha256"] != sha:
                raise ValueError("PyPI wheel digest mismatch")
            hashes[name] = sha
            print("OBS_P43B_WHEEL=" + name + "==" + version + "|" + wheel.name + "|" + sha,
                  flush=True)
        if set(hashes) != set(expected):
            raise ValueError("incomplete wheelhouse")
        hashed = work / "hashes.txt"
        hashed.write_text("".join(name + "==" + version + " --hash=sha256:" + hashes[name] + "\n"
                                  for name, version in sorted(expected.items())))
        pip("install", "--no-index", "--find-links", str(wheels), "--only-binary=:all:",
            "--no-deps", "--require-hashes", "--force-reinstall", "-r", str(hashed))
        pip("check")
        installed = json.loads(subprocess.check_output(
            [python, "-m", "pip", "--isolated", "list", "--format=json"]))
        if {norm(x["name"]): x["version"] for x in installed} != expected:
            raise ValueError("installed closure differs from lock")
        print("OBS_P43B_VERSION_LOCK=PASS; PYPI_WHEEL_HASHES=32; PREPINNED_HASHES=NO", flush=True)

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--install-locked":
        install_locked(sys.argv[2])
        sys.exit(0)
    if len(sys.argv) != 4:
        raise SystemExit(2)
    materialize(*sys.argv[1:])
