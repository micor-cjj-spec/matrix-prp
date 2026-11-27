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
# Exact hashes agree in both hosted CI jobs 140258996902 and 140258997230.
# Linux x64 CPython 3.13.5 only; all downloads are hash-required.
RUNTIME_LOCK = """annotated-types==0.8.0 --hash=sha256:f072f4d804ea359e4eaf198b1af7a8b0943881a87f31bb764f8bf219bb9419e0
anyio==4.16.0 --hash=sha256:c66ae634e0b8228396b801741beb3294326d4b6102f7bba4041c0dfb58c29026
attrs==26.1.0 --hash=sha256:c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309
certifi==2026.11.20 --hash=sha256:7422df25243767b9877031a2248cb14d09ddac9beee846f4cef3d5c9191d488f
cffi==2.1.1 --hash=sha256:a931079504ecc49efed7744c476a5c343a92fabf66dec2db95edb1b2fdc770e2
click==8.5.1 --hash=sha256:8bb5376d2006950386f8c6427613334a2acadc5f559cb80e638d00b4df957e37
cryptography==50.0.2 --hash=sha256:9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079
h11==0.16.0 --hash=sha256:63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86
httpcore==1.0.9 --hash=sha256:2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55
httpcore2==2.16.2 --hash=sha256:16051ae2a42f776007543f32de9349a317b23d2cbb4e1456b4bac0e88b87419a
httpx==0.28.1 --hash=sha256:d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad
httpx2==2.16.2 --hash=sha256:f05c13aade4c45dbf1c9060647a1058f0acad62398fad96e741269edb33d46f5
idna==3.20 --hash=sha256:ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c
jsonschema==4.26.0 --hash=sha256:d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce
jsonschema-specifications==2025.9.1 --hash=sha256:98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe
mcp==2.3.0 --hash=sha256:dd0c44c089d16453e8ae31a3877a0054d7a2314caaa81f5e0541b9b1734b2377
mcp-types==2.3.0 --hash=sha256:968efdbdaedfab06adae40d378a34395f1090c5921d4be3c9cde283aaf76d91d
opentelemetry-api==1.45.2 --hash=sha256:2cbd737377e710ee740d261c94e93fa0f08e6d037c18f17513cc0a2d94479a34
pip==26.3 --hash=sha256:f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13
pycparser==3.12 --hash=sha256:a076f3f489b39b43ed13563a1dafe42447445bec2e294154ec5c57fcdda4c85e
pydantic==2.14.4 --hash=sha256:653a2ad9f6d8858529c77c72717d0ea991d6c6837fe683246b2f4b2bbfc3fadc
pydantic-core==2.50.5 --hash=sha256:cbfde3ad127786f1dea1a6cd89a5eb824a16203f24743ad2b4e07506f43bc844
pyjwt==2.15.1 --hash=sha256:42d59d631f7768a1028a64c7ff581a9bf7519804daf91fc5b6c56e30eec5e193
python-multipart==0.0.34 --hash=sha256:ebacd224bd686eee2f9aa1066a657affe07435a185834e05e5235e2e59173e91
referencing==0.37.0 --hash=sha256:381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231
rpds-py==2026.9.1 --hash=sha256:7868b85224291c6cb6759f9b5adb9745f486d226f62b16a614dd5a2a5ab2b35b
sse-starlette==3.7.1 --hash=sha256:c1bb3af0508c6c24cd4ab6257047654bbec01456a424bed36b36e8020cd7a37f
starlette==1.10.0 --hash=sha256:478c0ab3b4ced6e82719849c118fa406f0278a3499c1a898cd15cd31bdc38ce4
truststore==0.10.5 --hash=sha256:9aaaedaefaf06d8b206278cf8b5012bc897f485a874503501e12d776df78951c
typing-extensions==4.16.0 --hash=sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8
typing-inspection==0.4.5 --hash=sha256:bc210535442b39e1bf2805e0c7a17dfd6a4ace760c84c7f7d16245d23a6b1c39
uvicorn==0.54.0 --hash=sha256:505bdb0f318731d45f1f712071fc781a8981f6847a31c902c9f5e652d4f67faf"""


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
    expected = dict(line.split()[0].split("==") for line in RUNTIME_LOCK.splitlines())
    pinned = {line.split("==")[0]: line.split("--hash=sha256:")[1]
              for line in RUNTIME_LOCK.splitlines()}
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
            "--only-binary=:all:", "--no-deps", "--require-hashes",
            "--dest", str(wheels), "-r", str(versions))
        hashes = {}
        for wheel in sorted(wheels.iterdir()):
            if not wheel.is_file() or not wheel.name.endswith(".whl"):
                raise ValueError("non-wheel dependency")
            name, version = wheel.name.split("-")[:2]
            name = norm(name)
            if expected.get(name) != version or name in hashes:
                raise ValueError("wheel does not match exact version lock")
            with wheel.open("rb") as stream:
                sha = hashlib.file_digest(stream, "sha256").hexdigest()
            if sha != pinned[name]:
                raise ValueError("repository-pinned wheel digest mismatch")
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
        print("OBS_P43B_VERSION_LOCK=PASS; PYPI_WHEEL_HASHES=32; PREPINNED_HASHES=YES", flush=True)

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--install-locked":
        install_locked(sys.argv[2])
        sys.exit(0)
    if len(sys.argv) != 4:
        raise SystemExit(2)
    materialize(*sys.argv[1:])
