"""Review-only configuration parser/compatibility checks; never start SSH or a unit."""
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
RECEIVER = "prp-remote-v11"
WORKER = "prp-remote-worker-v11"

def effective(path, user):
    return subprocess.check_output(["/usr/sbin/sshd", "-T", "-f", str(path),
        "-C", f"user={user},host=review.invalid,addr=192.0.2.10,laddr=192.0.2.20,lport=22"],
        text=True, stderr=subprocess.DEVNULL, timeout=15)

def check_receiver(raw):
    values = {}
    for line in raw.splitlines():
        key, _, val = line.partition(" ")
        values.setdefault(key, []).append(val)
    expected = {
        "authenticationmethods":"publickey","pubkeyauthentication":"yes",
        "passwordauthentication":"no","kbdinteractiveauthentication":"no",
        "gssapiauthentication":"no","hostbasedauthentication":"no",
        "permitemptypasswords":"no","strictmodes":"yes","usepam":"yes",
        "authorizedkeysfile":"/etc/matrix-prp-remote-executor-v11/authorized_keys",
        "authorizedkeyscommand":"none","trustedusercakeys":"none",
        "authorizedprincipalsfile":"none","authorizedprincipalscommand":"none",
        "forcecommand":"prp-receive-v11","permittty":"no","disableforwarding":"yes",
        "allowagentforwarding":"no","allowtcpforwarding":"no",
        "allowstreamlocalforwarding":"no","x11forwarding":"no",
        "permittunnel":"no","permituserrc":"no","permituserenvironment":"no",
        "maxsessions":"1"}
    for key, value in expected.items():
        if values.get(key) != [value]:
            raise ValueError("effective setting mismatch: " + key)
    check_env_policy(values)

def check_env_policy(values):
    # Exact Debian locale and terminal-color patterns, not arbitrary names.
    # The -I login wrapper also replaces the environment before execve.
    allowed = {"LANG", "LC_*", "COLORTERM", "NO_COLOR"}
    if any(x not in allowed for line in values.get("acceptenv", []) for x in line.split()):
        raise ValueError("unsafe AcceptEnv")
    if values.get("setenv"):
        raise ValueError("unexpected SetEnv")

def test_env_policy():
    check_env_policy({"acceptenv": ["LANG LC_* COLORTERM NO_COLOR"]})
    check_env_policy({"acceptenv": ["LANG", "LC_*", "COLORTERM", "NO_COLOR"]})
    for value in ["*", "COLORTERM*", "NO_*", "LD_PRELOAD", "LD_LIBRARY_PATH",
                  "PYTHONPATH", "BASH_ENV", "ENV", "SSH_ORIGINAL_COMMAND", "PATH"]:
        try:
            check_env_policy({"acceptenv": ["LANG LC_* " + value]})
        except ValueError as exc:
            if str(exc) != "unsafe AcceptEnv":
                raise
        else:
            raise ValueError("unsafe environment fixture accepted")
    try:
        check_env_policy({"acceptenv": ["LANG"], "setenv": ["PYTHONPATH=/tmp"]})
    except ValueError as exc:
        if str(exc) != "unexpected SetEnv":
            raise
    else:
        raise ValueError("forced environment fixture accepted")
    print("ENV_POLICY_REGRESSION=PASS")

def reject_wrapper():
    wrapper = HERE / "login-wrapper.review"
    env = {"PATH":"/usr/bin:/bin", "LANG":"C.UTF-8"}
    for args, original in [([],None),(["-c","id"],"id"),
        (["-c","prp-receive-v11"],"handoff-once"),
        (["-c","prp-receive-v11","extra"],"receive-v11"),
        (["-c","prp-receive-v11; id"],"receive-v11"),
        (["-c","prp-receive-v11"],None)]:
        e = dict(env)
        if original is not None:
            e["SSH_ORIGINAL_COMMAND"] = original
        out = subprocess.run(["/usr/bin/python3","-I",str(wrapper),*args],
                             env=e,capture_output=True,timeout=5)
        if out.returncode != 2 or out.stdout or out.stderr:
            raise ValueError("login wrapper failed closed")
    print("WRAPPER_DENIAL=PASS")

def main():
    if len(sys.argv) != 3:
        raise ValueError("usage: verify.py baseline candidate")
    baseline, candidate = map(Path, sys.argv[1:])
    for path in [baseline, candidate]:
        subprocess.run(["/usr/sbin/sshd","-t","-f",str(path)], check=True,
                       timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    test_env_policy()
    check_receiver(effective(candidate, RECEIVER))
    # Scope check for root and other existing dedicated worker.
    for user in ["root", WORKER]:
        if effective(baseline,user) != effective(candidate,user):
            raise ValueError("non-receiver config changed")
    print("SSHD_PARSE_AND_EFFECTIVE_SCOPE=PASS")
    reject_wrapper()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # No config dumps, paths/keys or raw sshd logs in public output.
        print("P73C_TEMPLATE_CHECK_FAILED: " + type(exc).__name__, file=sys.stderr)
        if isinstance(exc, ValueError):
            print(str(exc),file=sys.stderr)
        sys.exit(2)
