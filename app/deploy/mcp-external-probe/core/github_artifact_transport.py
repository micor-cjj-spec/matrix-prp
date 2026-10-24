"""Bounded read-only GitHub transport for the local administrator bridge.

API credentials go only to api.github.com, never to signed storage URLs. No
automatic redirects, environment proxies, cookies or raw exceptions escape.
This client does not receive the production evidence HMAC key.
"""
import hashlib
import re
import time
from urllib.parse import urlsplit
import requests
from attested_evidence_bridge import REPO, MAX_ARCHIVE, GateError, checked_json

class GitHubArtifactClient:
    def __init__(self,api_token):
        if not isinstance(api_token,str) or not api_token:raise GateError('GITHUB_TOKEN_REQUIRED')
        self._token=api_token

    @staticmethod
    def _positive(value):
        if type(value) is not int or value<=0:raise GateError('GITHUB_ID_INVALID')
        return str(value)

    @staticmethod
    def _allowed(url,first):
        try:
            p=urlsplit(url);host=p.hostname
            valid_host=host=='api.github.com' if first else bool(host and (host.endswith('.blob.core.windows.net') or host.endswith('.actions.githubusercontent.com')))
            return p.scheme=='https' and valid_host and p.port in (None,443) and p.username is None and p.password is None and not p.fragment
        except ValueError:return False

    def _fetch(self,url,limit,storage_redirects=False):
        deadline=time.monotonic()+25
        try:
            for hop in range(4):
                if not self._allowed(url,hop==0):raise GateError('GITHUB_REDIRECT_NOT_APPROVED')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise GateError('GITHUB_DOWNLOAD_DEADLINE')
                headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Accept-Encoding':'identity'} if hop==0 else {'Accept-Encoding':'identity'}
                if hop==0:headers['Authorization']='Bearer '+self._token
                # A fresh session per hop avoids forwarding cookies or auth state.
                with requests.Session() as session:
                    session.trust_env=False;session.verify=True
                    with session.get(url,headers=headers,stream=True,allow_redirects=False,timeout=(min(5,remaining),min(10,remaining))) as response:
                        if response.status_code in (301,302,303,307,308):
                            if not storage_redirects:raise GateError('GITHUB_API_REDIRECT_REJECTED')
                            url=response.headers.get('Location','');continue
                        if response.status_code!=200:raise GateError('GITHUB_HTTP_RESULT_UNVERIFIED')
                        if response.headers.get('Content-Encoding','identity').lower()!='identity':raise GateError('GITHUB_HTTP_ENCODING_UNAPPROVED')
                        length=response.headers.get('Content-Length')
                        if length is not None and (not length.isdigit() or int(length)>limit):raise GateError('GITHUB_DOWNLOAD_SIZE')
                        if not callable(getattr(response.raw,'read1',None)):raise GateError('GITHUB_BOUNDED_READER_UNAVAILABLE')
                        chunks=[];size=0
                        while True:
                            if time.monotonic()>=deadline:raise GateError('GITHUB_DOWNLOAD_DEADLINE')
                            chunk=response.raw.read1(min(65536,limit+1-size))
                            if not chunk:break
                            size+=len(chunk)
                            if size>limit:raise GateError('GITHUB_DOWNLOAD_SIZE')
                            chunks.append(chunk)
                        return b''.join(chunks)
            raise GateError('GITHUB_REDIRECT_LIMIT')
        except GateError:raise
        except Exception:
            # Signed URLs and request exceptions can contain temporary credentials.
            raise GateError('GITHUB_TRANSPORT_UNVERIFIED') from None

    def run(self,run_id):
        data=self._fetch('https://api.github.com/repos/'+REPO+'/actions/runs/'+self._positive(run_id),1_000_000)
        result=checked_json(data)
        if not isinstance(result,dict):raise GateError('GITHUB_RUN_FORMAT')
        return result

    def artifacts(self,run_id):
        data=self._fetch('https://api.github.com/repos/'+REPO+'/actions/runs/'+self._positive(run_id)+'/artifacts?per_page=100',1_000_000)
        result=checked_json(data)
        if not isinstance(result,dict) or not isinstance(result.get('artifacts'),list) or result.get('total_count')!=len(result['artifacts']):
            raise GateError('GITHUB_ARTIFACT_LIST_INCOMPLETE')
        return result['artifacts']

    def download(self,artifact):
        ident=self._positive(artifact.get('id'));size=artifact.get('size_in_bytes');digest=artifact.get('digest')
        if artifact.get('expired') is not False or type(size) is not int or not 1<=size<=MAX_ARCHIVE:
            raise GateError('GITHUB_ARTIFACT_METADATA_REJECTED')
        if not isinstance(digest,str) or not re.fullmatch('sha256:[0-9a-f]{64}',digest):raise GateError('GITHUB_ARTIFACT_DIGEST_REQUIRED')
        data=self._fetch('https://api.github.com/repos/'+REPO+'/actions/artifacts/'+ident+'/zip',size,True)
        if len(data)!=size or 'sha256:'+hashlib.sha256(data).hexdigest()!=digest:raise GateError('ARTIFACT_ARCHIVE_DIGEST')
        return data
