#!/usr/bin/env python3
"""GitHub Actions -> dedicated SSH forced-command bridge.

Public issue transports only encrypted CMS, never plaintext commands or output.
All event/body access uses a JSON file, not workflow expression interpolation.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

from protocol import (ACTOR, REPOSITORY, InvalidJob, MAGIC_RESULT,
                      MAX_RESULT_B64, b64_decode, parse_command_comment)
ISSUE = 277

def verify_github_event(event, repo=None, ref=None):
    if repo != REPOSITORY or ref != 'refs/heads/main' or not isinstance(event,dict):
        raise InvalidJob('repository or branch mismatch')
    if event.get('action') != 'created' or event.get('repository',{}).get('full_name') != REPOSITORY:
        raise InvalidJob('invalid GitHub event')
    sender = event.get('sender',{})
    author = event.get('comment',{}).get('user',{})
    if (sender.get('login') != ACTOR or sender.get('type') != 'User' or
            author.get('login') != ACTOR or author.get('type') != 'User'):
        raise InvalidJob('untrusted GitHub actor')
    issue = event.get('issue',{})
    if issue.get('number') != ISSUE or issue.get('state') != 'open' or issue.get('pull_request') is not None:
        raise InvalidJob('wrong issue')
    comment = event.get('comment',{})
    if type(comment.get('id')) is not int or comment['id'] <= 0:
        raise InvalidJob('invalid comment')
    return parse_command_comment(comment.get('body'))

def ssh_exchange(job_id,ciphertext,host,private_key,known_hosts):
    if not isinstance(host,str) or not re.fullmatch(r'[A-Za-z0-9.-]{3,253}',host):
        raise InvalidJob('invalid SSH host')
    with tempfile.TemporaryDirectory() as directory:
        key_path=Path(directory)/'ssh.key'
        known_path=Path(directory)/'known_hosts'
        key_path.write_text(private_key)
        known_path.write_text(known_hosts)
        key_path.chmod(0o600); known_path.chmod(0o600)
        if not private_key.strip() or not known_hosts.strip():
            raise InvalidJob('SSH credentials unavailable')
        command=['ssh','-T','-o','BatchMode=yes','-o','IdentitiesOnly=yes',
                 '-o','StrictHostKeyChecking=yes',
                 '-o',f'UserKnownHostsFile={known_path}',
                 '-o','ClearAllForwardings=yes','-o','ConnectTimeout=15',
                 '-o','ConnectionAttempts=1','-o','ForwardAgent=no',
                 '-i',str(key_path),f'prp-chat-shell@{host}','run']
        request=json.dumps({'jobId':job_id,'ciphertext':ciphertext},separators=(',',':')).encode()
        try:
            completed=subprocess.run(command,input=request,capture_output=True,timeout=65)
        except subprocess.TimeoutExpired as exc:
            raise InvalidJob('SSH timed out, command status uncertain') from exc
    if completed.returncode or len(completed.stdout) > 85000:
        raise InvalidJob('remote execution rejected or unavailable')
    try:
        result=json.loads(completed.stdout)
    except (ValueError,UnicodeDecodeError) as exc:
        raise InvalidJob('invalid encrypted response') from exc
    if (not isinstance(result,dict) or set(result) != {'jobId','ciphertext'} or
            result['jobId']!=job_id):
        raise InvalidJob('response job ID mismatch')
    b64_decode(result['ciphertext'],MAX_RESULT_B64)
    return result['ciphertext']

def post_private_result(job_id,ciphertext,token):
    if not isinstance(token,str) or len(token)<10:
        raise InvalidJob('missing GitHub token')
    # All submitted contents remain encrypted. No logs or artifacts carry output.
    body=f'{MAGIC_RESULT} {job_id} {ciphertext}'
    data=json.dumps({'body':body},separators=(',',':')).encode()
    url=f'https://api.github.com/repos/{REPOSITORY}/issues/{ISSUE}/comments'
    request=urllib.request.Request(url,data=data,method='POST',headers={
        'Authorization':'Bearer '+token,
        'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28',
        'Content-Type':'application/json',
        'User-Agent':'prp-shell-github-bridge'})
    try:
        with urllib.request.urlopen(request,timeout=15) as response:
            if response.status != 201:
                raise InvalidJob('encrypted result publish failed')
    except Exception as exc:
        raise InvalidJob('encrypted result publish failed') from exc

def main():
    event_path=os.environ['GITHUB_EVENT_PATH']
    event_bytes=Path(event_path).read_bytes()
    if len(event_bytes)>100000:
        raise InvalidJob('event oversized')
    event=json.loads(event_bytes)
    job_id,ciphertext=verify_github_event(event,os.getenv('GITHUB_REPOSITORY'),os.getenv('GITHUB_REF'))
    response=ssh_exchange(job_id,ciphertext,os.environ.get('PRP_SHELL_HOST'),
             os.environ.get('PRP_SHELL_SSH_KEY',''),os.environ.get('PRP_SHELL_KNOWN_HOSTS',''))
    post_private_result(job_id,response,os.getenv('GH_TOKEN',''))
    print('PRP_CHAT_SHELL_ENCRYPTED_RESULT_POSTED')

if __name__=='__main__':
    try:
        main()
    except Exception:
        # Fail safely without ever printing user commands, credentials or output.
        print('PRP_CHAT_SHELL_FAILED_OR_UNCERTAIN',file=sys.stderr)
        sys.exit(1)
