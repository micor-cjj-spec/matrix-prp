"""One-off vulnerability evidence for public pilot images. No live host or credentials."""
import json
import os
import re
import secrets
import subprocess

from ci_smoke import IMAGES, cmd

SCANNER = "ghcr.io/aquasecurity/trivy@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb"

def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("hosted CI only")
    cache = "obs450-scan-" + secrets.token_hex(6)
    cmd("docker", "volume", "create", cache)
    try:
        cmd("docker", "pull", "--platform", "linux/amd64", SCANNER)
        print("OBS_SCAN_TOOL=" + SCANNER, flush=True)
        for key, tag in IMAGES.items():
            cmd("docker", "pull", "--platform", "linux/amd64", tag)
            repo = tag.rsplit(":", 1)[0]
            refs = json.loads(cmd("docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tag))
            ref = next((x for x in refs if x.split("@")[0] in (repo, "docker.io/" + repo)
                        and re.search(r"@sha256:[0-9a-f]{64}$", x)), None)
            if not ref:
                raise AssertionError("missing digest " + key)
            print("OBS_SCAN_DIGEST=" + key + "|" + ref, flush=True)
            result = subprocess.run(
                ["docker", "run", "--rm", "--platform", "linux/amd64", "--cap-drop", "ALL",
                 "--security-opt", "no-new-privileges",
                 "--mount", "type=volume,src=" + cache + ",dst=/cache",
                 SCANNER, "image", "--image-src", "remote", "--platform", "linux/amd64",
                 "--cache-dir", "/cache", "--scanners", "vuln", "--severity", "HIGH,CRITICAL",
                 "--ignorefile", "/dev/null", "--format", "json", "--timeout", "7m",
                 "--exit-code", "0", ref], capture_output=True, text=True, timeout=480)
            if result.returncode:
                print("OBS_SCAN_ERROR=" + key + "|exit=" + str(result.returncode), flush=True)
                raise RuntimeError("scanner execution failed; no security verdict")
            report = json.loads(result.stdout)
            results = report.get("Results")
            if not isinstance(results, list) or not results:
                raise RuntimeError("no scanned targets: " + key)
            seen = set()
            for target in results:
                for v in target.get("Vulnerabilities") or []:
                    seen.add(tuple(str(v.get(k) or "") for k in
                                   ("Severity", "VulnerabilityID", "PkgName", "InstalledVersion", "FixedVersion")))
            print("OBS_SCAN_TARGETS=" + key + "|" + str(len(results)), flush=True)
            print("OBS_SCAN_COUNTS=" + key + "|" + json.dumps({
                "critical": sum(v[0] == "CRITICAL" for v in seen),
                "high": sum(v[0] == "HIGH" for v in seen),
                "fix_available": sum(bool(v[4]) for v in seen)}), flush=True)
            for finding in sorted(seen):
                print("OBS_SCAN_FINDING=" + key + "|" + json.dumps(finding), flush=True)
        print("OBS_IMAGE_REVIEW=EVIDENCE_ONLY", flush=True)
    finally:
        cmd("docker", "volume", "rm", cache, allow_failure=True)

if __name__ == "__main__":
    main()
