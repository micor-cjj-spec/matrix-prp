"""CONNECT only to reviewed chatgpt.com:443, public DNS pin per tunnel, exact SNI.
No TLS interception, no keys, no arbitrary forward destination, no raw request logs.
"""
import concurrent.futures,ipaddress,json,os,select,socket,struct,threading,time
from pathlib import Path
COUNTS={};LOCK=threading.Lock();SLOTS=threading.BoundedSemaphore(8)
RESOLVER=concurrent.futures.ThreadPoolExecutor(max_workers=2)
def is_public_address(value):
 ip=ipaddress.ip_address(value)
 return ip.is_global and not (ip.is_multicast or ip.is_unspecified or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip.is_private)
def count(name):
 with LOCK:
  COUNTS[name]=COUNTS.get(name,0)+1
  try:Path('/state/counters.safe.json').write_text(json.dumps(COUNTS))
  except OSError:pass
def receive(sock,n,deadline):
 data=b''
 while len(data)<n:
  if time.monotonic()>deadline:raise TimeoutError()
  b=sock.recv(n-len(data))
  if not b:raise ValueError('EOF')
  data+=b
 return data
def client_hello(sock):
 deadline=time.monotonic()+5;wire=b'';hello=b''
 while len(wire)<32768:
  header=receive(sock,5,deadline);kind,version,length=struct.unpack('!BHH',header)
  if kind!=22 or version<0x0301 or not 1<=length<=16384:raise ValueError('TLS_RECORD')
  body=receive(sock,length,deadline);wire+=header+body;hello+=body
  if len(hello)>=4 and len(hello)>=4+int.from_bytes(hello[1:4],'big'):break
 if len(hello)<4 or hello[0]!=1:raise ValueError('HELLO')
 data=hello[4:4+int.from_bytes(hello[1:4],'big')];i=34
 i+=1+data[i];i+=2+int.from_bytes(data[i:i+2],'big');i+=1+data[i]
 end=i+2+int.from_bytes(data[i:i+2],'big');i+=2;names=[]
 while i+4<=end:
  typ,n=struct.unpack('!HH',data[i:i+4]);ext=data[i+4:i+4+n];i+=4+n
  if typ==0:
   j=2
   while j+3<=len(ext):
    k=ext[j];length=int.from_bytes(ext[j+1:j+3],'big');name=ext[j+3:j+3+length];j+=3+length
    if k==0:names.append(name.decode('ascii'))
 if names!=['chatgpt.com']:raise ValueError('SNI')
 return wire
def serve(client):
 try:
  with client:
   client.settimeout(5);deadline=time.monotonic()+3;header=b''
   while not header.endswith(b'\r\n\r\n'):
    if len(header)>=8192 or time.monotonic()>deadline:raise ValueError('HEADER')
    header+=receive(client,1,deadline)
   first=header.split(b'\r\n',1)[0]
   if first not in (b'CONNECT chatgpt.com:443 HTTP/1.1',b'CONNECT chatgpt.com:443 HTTP/1.0'):
    count('rejected_authority');client.sendall(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n');return
   future=RESOLVER.submit(socket.getaddrinfo,'chatgpt.com',443,0,socket.SOCK_STREAM)
   try:resolved={x[4][0] for x in future.result(timeout=2)}
   except concurrent.futures.TimeoutError:
    future.cancel();count('rejected_dns_timeout');return
   if not resolved or any(not is_public_address(x) for x in resolved):
    count('rejected_dns');client.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n');return
   # Pin this validated public address for the tunnel: no second DNS resolution.
   public_v4=sorted(x for x in resolved if ipaddress.ip_address(x).version==4)
   if not public_v4:raise ValueError('NO_IPV4')
   upstream=socket.create_connection((public_v4[0],443),timeout=3)
   with upstream:
    client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
    try:hello=client_hello(client)
    except (ValueError,IndexError,UnicodeError,struct.error):count('rejected_sni');return
    upstream.sendall(hello);count('allowed_connect');peers={client:upstream,upstream:client};deadline=time.monotonic()+12;total=0
    while time.monotonic()<deadline:
     readable,_,_=select.select(list(peers),[],[],2)
     if not readable:continue
     for s in readable:
      b=s.recv(16384)
      if not b:return
      total+=len(b)
      if total>262144:count('output_limit');return
      peers[s].sendall(b)
    count('tunnel_deadline')
 except (OSError,TimeoutError,ValueError,IndexError):count('transport_failure')
 finally:SLOTS.release()
if __name__=='__main__':
 with socket.socket() as listener,concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);listener.bind(('0.0.0.0',3128));listener.listen(8)
  while True:
   client,_=listener.accept()
   if not SLOTS.acquire(blocking=False):client.close();count('capacity_rejected')
   else:pool.submit(serve,client)
