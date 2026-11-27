"""CI-only isolated Nginx 1.26.3 + TLS loopback acceptance.

Never run on a target server. No real domain, issuer, credentials or service
configuration. All listeners are random loopback ports on the disposable CI
runner. The Nginx image uses host networking only for these local fixtures;
no Docker socket is mounted and the fixture directory is mounted read-only.
"""
import http.client
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from ci_process_smoke import BODY, TOKEN, check
from audit_store import AUDIT_NAME
from http_boundary import METADATA_PATH
from query_contract import ISSUER, RESOURCE, CLIENT, SUBJECT, SCOPE
from snapshot_contract import SnapshotStore
from test_snapshot_contract import NOW, sample

IMAGE_TAG="nginx:1.26.3"
EXPECTED_VERSION="nginx/1.26.3"

def run(args, **kw):
    return subprocess.run(args,check=True,timeout=60,**kw)

def cert(root, name, sans):
    run(["openssl","req","-x509","-newkey","rsa:2048","-nodes","-days","1",
         "-subj","/CN=ops.invalid","-addext","subjectAltName="+sans,
         "-keyout",str(root/(name+"-key.pem")),"-out",str(root/(name+".pem"))],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def render(root, port, upstream_port, bad_ca=False):
    template=(Path(__file__).parent/"prp-ops-https-vhost.conf.example").read_text()
    substitutions={
        "    listen 443 ssl;\n    listen [::]:443 ssl;":f"    listen 127.0.0.1:{port} ssl;",
        "https://127.0.0.1:18444;":f"https://127.0.0.1:{upstream_port};",
        "/REPLACE_WITH_APPROVED_PUBLIC_CERT_CHAIN":"/fixture/front.pem",
        "/REPLACE_WITH_APPROVED_PUBLIC_CERT_KEY":"/fixture/front-key.pem",
        "/REPLACE_WITH_APPROVED_UPSTREAM_CA":"/fixture/front.pem" if bad_ca else "/fixture/cert.pem",
        "/var/log/nginx/prp-ops-vhost-error.log":"/tmp/ops-error.log",
    }
    for old,new in substitutions.items():
        check(template.count(old)==1,"unexpected template anchor")
        template=template.replace(old,new)
    # Independent synthetic existing/default vhost. No production config copied.
    config=f"""worker_processes 1;
pid /tmp/nginx.pid;
error_log /tmp/nginx-error.log crit;
events {{ worker_connections 32; }}
http {{
    access_log off;
    client_body_temp_path /tmp/body;
    proxy_temp_path /tmp/proxy;
    fastcgi_temp_path /tmp/fastcgi;
    uwsgi_temp_path /tmp/uwsgi;
    scgi_temp_path /tmp/scgi;
    server {{
        listen 127.0.0.1:{port} ssl default_server;
        server_name existing.invalid;
        ssl_certificate /fixture/front.pem;
        ssl_certificate_key /fixture/front-key.pem;
        return 418;
    }}
{template}
}}
"""
    (root/"nginx.conf").write_text(config)

def start_proxy(root, image, name):
    base=["docker","run","--rm","--network","host","--read-only",
          "--cap-drop","ALL","--security-opt","no-new-privileges",
          "--user",f"{os.getuid()}:{os.getgid()}","--tmpfs","/tmp:rw,noexec,nosuid,size=16m",
          "--mount",f"type=bind,source={root},target=/fixture,readonly",
          "--entrypoint","nginx"]
    run(base+[image,"-t","-p","/tmp/","-c","/fixture/nginx.conf"],
        stdout=subprocess.DEVNULL)
    run(base+["--name",name,"-d",image,"-p","/tmp/","-c","/fixture/nginx.conf",
              "-g","daemon off;"],stdout=subprocess.DEVNULL)

def stop_proxy(name):
    subprocess.run(["docker","rm","-f",name],stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL,timeout=20,check=False)

def parent():
    run(["docker","pull",IMAGE_TAG])
    image=run(["docker","image","inspect","--format","{{.Id}}",IMAGE_TAG],
              capture_output=True,text=True).stdout.strip()
    check(image.startswith("sha256:") and len(image)==71,"image identity missing")
    version=run(["docker","run","--rm","--network","none","--entrypoint","nginx",image,"-v"],
                capture_output=True,text=True)
    check(version.stderr.strip()=="nginx version: "+EXPECTED_VERSION,"wrong nginx version")
    print("OPS_NGINX_VERSION="+EXPECTED_VERSION,flush=True)
    print("OPS_NGINX_IMAGE_ID="+image,flush=True)
    with tempfile.TemporaryDirectory(prefix="prp-ops-nginx-ci-") as tmp:
        root=Path(tmp)
        (root/"snapshot").mkdir(mode=0o700)
        (root/"audit").mkdir(mode=0o700)
        (root/"audit"/AUDIT_NAME).touch(mode=0o600)
        SnapshotStore(root/"snapshot").write(sample())
        grant={"version":1,"grantId":str(uuid.uuid4()),"issuer":ISSUER,
            "resource":RESOURCE,"client":CLIENT,"subject":SUBJECT,"environment":"staging",
            "scope":SCOPE,"issuedAt":NOW-20,"expiresAt":NOW+600,"active":True}
        def write_grant(active):
            p=root/"next-grant.json"
            p.write_text(json.dumps(dict(grant,active=active)))
            os.replace(p,root/"synthetic-grant.json")
        write_grant(True)
        cert(root,"backend","DNS:ops.invalid")
        (root/"backend.pem").rename(root/"cert.pem")
        (root/"backend-key.pem").rename(root/"key.pem")
        cert(root,"front","DNS:ops.invalid,DNS:existing.invalid")
        context=ssl.create_default_context(cafile=str(root/"front.pem"))
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as upstream:
            upstream.bind(("127.0.0.1",0))
            upstream.listen(16)
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1",0))
                port=reservation.getsockname()[1]
            render(root,port,upstream.getsockname()[1])
            child=subprocess.Popen([sys.executable,str(Path(__file__).with_name("ci_process_smoke.py")),
                "--child",str(upstream.fileno()),tmp],pass_fds=(upstream.fileno(),),
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            name="prp-ops-nginx-ci-"+uuid.uuid4().hex
            def request(method,target,body=b"",extra=(),sni="ops.invalid",host="ops.invalid",
                        auth=True,content_length=True,pace=True):
                # Actual raw HTTP/1.1 via independently verified frontend TLS.
                if pace:
                    time.sleep(1.05) # respect the unmodified template rate limit
                headers=[("Host",host),("Connection","close")]
                if method=="POST":
                    headers += [("Content-Type","application/json"),
                                ("Accept","application/json, text/event-stream")]
                    if content_length:
                        headers.append(("Content-Length",str(len(body))))
                    if auth:
                        headers.append(("Authorization","Bearer "+TOKEN))
                headers.extend(extra)
                raw=(method+" "+target+" HTTP/1.1\r\n" +
                    "".join(k+": "+v+"\r\n" for k,v in headers)+"\r\n").encode("ascii")+body
                with socket.create_connection(("127.0.0.1",port),timeout=3) as conn:
                    with context.wrap_socket(conn,server_hostname=sni) as tls:
                        tls.sendall(raw)
                        response=http.client.HTTPResponse(tls)
                        response.begin()
                        data=response.read(32769)
                        check(len(data)<=32768,"response too large")
                        return response.status,data,dict(response.getheaders())
            def deny(label,result,expected):
                status,data,_=result
                check(status in expected,label+": unexpected status "+str(status))
                check(b"structuredContent" not in data and TOKEN.encode() not in data,
                      label+": sensitive response")
                print("OPS_NGINX_CASE="+label+":PASS",flush=True)
            try:
                start_proxy(root,image,name)
                end=time.monotonic()+12
                while True:
                    check(child.poll() is None,"backend exited")
                    try:
                        status,data,_=request("GET",METADATA_PATH,pace=False)
                        if status==200:
                            check(json.loads(data)["resource"]==RESOURCE,"metadata mismatch")
                            break
                    except (OSError,http.client.HTTPException):
                        pass
                    if time.monotonic()>=end:
                        raise AssertionError("proxy readiness failed")
                    time.sleep(.2)
                print("OPS_NGINX_CASE=metadata:PASS",flush=True)
                deny("missing-bearer",request("POST","/mcp",BODY,auth=False),{401})
                status,data,headers=request("POST","/mcp",BODY)
                check(status==200 and json.loads(data)["result"]["structuredContent"]["status"]=="fresh",
                      "valid tool query failed")
                print("OPS_NGINX_CASE=authorized:PASS",flush=True)
                deny("duplicate-authorization",request("POST","/mcp",BODY,
                    extra=[("Authorization","Bearer other")]),{400})
                deny("duplicate-origin",request("POST","/mcp",BODY,extra=[
                    ("Origin","https://chatgpt.com"),("Origin","https://evil.invalid")]),{400,403})
                deny("duplicate-host",request("POST","/mcp",BODY,
                    extra=[("Host","existing.invalid")]),{400})
                deny("duplicate-content-length",request("POST","/mcp",BODY,
                    extra=[("Content-Length",str(len(BODY)))]),{400})
                deny("raw-encoded-path",request("POST","/%6dcp",BODY),{404})
                deny("query-string",request("POST","/mcp?x=1",BODY),{404})
                deny("oversize",request("POST","/mcp",b"x"*4097),{413})
                deny("chunked",request("POST","/mcp",b"0\r\n\r\n",
                    extra=[("Transfer-Encoding","chunked")],content_length=False),{400})
                deny("ambiguous-framing",request("POST","/mcp",BODY,
                    extra=[("Transfer-Encoding","chunked")]),{400})
                deny("compression",request("POST","/mcp",BODY,
                    extra=[("Content-Encoding","gzip")]),{400})
                deny("sni-mismatch",request("POST","/mcp",BODY,sni="existing.invalid"),{421})
                deny("existing-vhost",request("GET","/",sni="existing.invalid",host="existing.invalid"),{418})
                write_grant(False)
                deny("revocation",request("POST","/mcp",BODY),{401})
                records=[json.loads(line) for line in (root/"audit"/AUDIT_NAME).read_bytes().splitlines()]
                check(any(row["route"]=="mcp" and row["outcome"]=="handled" for row in records),"audit missing")
                check(all(TOKEN not in json.dumps(row) for row in records),"audit secret leak")
                stop_proxy(name)
                render(root,port,upstream.getsockname()[1],bad_ca=True)
                start_proxy(root,image,name)
                # Test certificate validation with deliberately wrong CA.
                end=time.monotonic()+8
                while True:
                    try:
                        result=request("GET",METADATA_PATH,pace=False)
                        break
                    except OSError:
                        if time.monotonic()>=end:
                            raise
                        time.sleep(.1)
                deny("untrusted-upstream",result,{502})
                print("OPS_NGINX_TLS_PROXY_SMOKE=PASS",flush=True)
            finally:
                stop_proxy(name)
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

if __name__=="__main__":
    if len(sys.argv)!=1 or os.environ.get("GITHUB_ACTIONS")!="true" or os.environ.get("RUNNER_ENVIRONMENT")!="github-hosted":
        raise SystemExit(78)
    parent()
