import hashlib
import pathlib
import sys
import unittest
from unittest.mock import patch
import requests

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'release-v4'))
import github_artifact_transport as transport

class Response:
    def __init__(self,status=200,body=b'zip',headers=None):
        self.status_code=status;self.body=body;self.headers=headers or {};self.raw=self
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def read1(self,size):out=self.body[:size];self.body=self.body[size:];return out

class TransportTests(unittest.TestCase):
    def metadata(self,data=b'zip'):
        return dict(id=10,size_in_bytes=len(data),expired=False,digest='sha256:'+hashlib.sha256(data).hexdigest())

    def factory(self,responses,calls):
        class Session:
            trust_env=True
            verify=False
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def get(self,url,**kwargs):
                calls.append((url,kwargs,self.trust_env,self.verify))
                value=responses.pop(0)
                if isinstance(value,Exception):raise value
                return value
        return Session

    def test_api_token_not_forwarded_to_storage(self):
        calls=[];responses=[Response(302,headers={'Location':'https://example.blob.core.windows.net/object?sig=PRIVATE'}),Response()]
        with patch.object(transport.requests,'Session',self.factory(responses,calls)):
            self.assertEqual(transport.GitHubArtifactClient('TOKEN').download(self.metadata()),b'zip')
        self.assertEqual(calls[0][1]['headers']['Authorization'],'Bearer TOKEN')
        self.assertNotIn('Authorization',calls[1][1]['headers'])
        self.assertTrue(all(not x[2] and x[3] and x[1]['allow_redirects'] is False for x in calls))

    def test_unknown_http_userinfo_or_port_redirect_rejected(self):
        for url in ['http://example.blob.core.windows.net/blob','https://evil.invalid/blob',
                    'https://user:password@example.blob.core.windows.net/blob','https://example.blob.core.windows.net:444/blob']:
            calls=[]
            with patch.object(transport.requests,'Session',self.factory([Response(302,headers={'Location':url})],calls)):
                with self.assertRaises(transport.GateError):transport.GitHubArtifactClient('TOKEN').download(self.metadata())
            self.assertEqual(len(calls),1)

    def test_signed_url_not_exported_on_network_error(self):
        calls=[];responses=[Response(302,headers={'Location':'https://example.blob.core.windows.net/blob?sig=PRIVATE'}),requests.ConnectionError('PRIVATE SIGNED URL')]
        with patch.object(transport.requests,'Session',self.factory(responses,calls)):
            with self.assertRaises(transport.GateError) as exc:transport.GitHubArtifactClient('TOKEN').download(self.metadata())
        self.assertNotIn('PRIVATE',str(exc.exception));self.assertTrue(exc.exception.__suppress_context__)

    def test_modified_archive_rejected(self):
        calls=[]
        with patch.object(transport.requests,'Session',self.factory([Response(body=b'bad')],calls)):
            with self.assertRaises(transport.GateError):transport.GitHubArtifactClient('TOKEN').download(self.metadata())

    def test_oversized_stream_not_accepted(self):
        calls=[]
        with patch.object(transport.requests,'Session',self.factory([Response(body=b'zip-too-long')],calls)):
            with self.assertRaises(transport.GateError):transport.GitHubArtifactClient('TOKEN').download(self.metadata())

    def test_expired_artifact_never_opens_network(self):
        artifact=self.metadata();artifact['expired']=True
        with patch.object(transport.requests,'Session') as session:
            with self.assertRaises(transport.GateError):transport.GitHubArtifactClient('TOKEN').download(artifact)
            session.assert_not_called()

    def test_api_identity_redirect_not_followed(self):
        calls=[]
        with patch.object(transport.requests,'Session',self.factory([Response(302,headers={'Location':'https://example.blob.core.windows.net/a'})],calls)):
            with self.assertRaises(transport.GateError):transport.GitHubArtifactClient('TOKEN').run(11)
        self.assertEqual(len(calls),1)

    def test_missing_artifact_pagination_rejected(self):
        calls=[];body=b'{"total_count":101,"artifacts":[]}'
        with patch.object(transport.requests,'Session',self.factory([Response(body=body)],calls)):
            with self.assertRaises(transport.GateError):transport.GitHubArtifactClient('TOKEN').artifacts(11)

if __name__=='__main__':unittest.main()
