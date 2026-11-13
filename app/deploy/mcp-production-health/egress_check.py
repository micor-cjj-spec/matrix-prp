"""Fixed public metadata/JWKS requests via the candidate broker. No tokens or logs."""
import http.client
import json
import socket
import ssl
from contract import CLIENT,JWKS,REDIRECT


def probe(port,check):
    for index,target in enumerate(('example.com:443','127.0.0.1:443','169.254.169.254:80',
                                   'chatgpt.com:80','chatgpt.com.evil.example:443','persistent.oaistatic.com:443')):
        with socket.create_connection(('127.0.0.1',port),3) as s:
            s.settimeout(5);s.sendall(('CONNECT '+target+' HTTP/1.1\r\nHost: '+target+'\r\n\r\n').encode())
            status=s.recv(200).split(b'\r\n',1)[0]
        check('egress_explicit_destination_denial_'+str(index),status==b'HTTP/1.1 403 Forbidden')
    documents=[]
    for path in ('/oauth/client.json','/oauth/jwks.json'):
        c=http.client.HTTPSConnection('127.0.0.1',port,context=ssl.create_default_context(),timeout=6)
        try:
            c.set_tunnel('chatgpt.com',443)
            c.request('GET',path,headers={'Host':'chatgpt.com','Accept':'application/json','Accept-Encoding':'identity'})
            r=c.getresponse();b=r.read(65537)
            check('public_verified_tls_json_'+str(len(documents)),r.status==200 and len(b)<=65536 and 'application/json' in r.getheader('Content-Type',''))
            documents.append(json.loads(b))
        finally:c.close()
    m,k=documents
    check('current_official_metadata_identity_and_private_jwt',m.get('client_id')==CLIENT and m.get('redirect_uris')==[REDIRECT]
          and m.get('token_endpoint_auth_method')=='private_key_jwt' and m.get('jwks_uri')==JWKS)
    check('current_official_jwks_public_signing_keys',bool(k.get('keys')) and all(
        x.get('kty')=='RSA' and x.get('kid') and not set(x)&{'d','p','q','dp','dq','qi','k'} for x in k['keys']))
    with socket.create_connection(('127.0.0.1',port),3) as s:
        s.settimeout(5);s.sendall(b'CONNECT chatgpt.com:443 HTTP/1.1\r\nHost: chatgpt.com:443\r\n\r\n')
        header=b''
        while not header.endswith(b'\r\n\r\n'):
            part=s.recv(1)
            if not part or len(header)>4096:raise RuntimeError('EGRESS_CONNECT_HEADER')
            header+=part
        check('egress_valid_connect',header.startswith(b'HTTP/1.1 200 '))
        refused=False
        try:ssl.create_default_context().wrap_socket(s,server_hostname='example.com')
        except (OSError,ssl.SSLError):refused=True
        check('egress_wrong_sni_refused',refused)
    return k


def native_signature_denial(status,body,fetched):
    # Exact 26.8.1 JWTClientAuthenticator response after verifySignature throws.
    # A key-load error, generic invalid_client or mere HTTP failure is not proof.
    return (status==400 and fetched and body.get('error')=='invalid_client' and
            body.get('error_description')=='Client authentication with signed JWT failed: Signature on JWT token failed validation')
