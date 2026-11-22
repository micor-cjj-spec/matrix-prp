"""Encrypted GitHub comment protocol for PRP operations (no credentials)."""
import base64
import json
import re
import subprocess
import time
import uuid

MAGIC_COMMAND = '/prp-shell-v1'
MAGIC_RESULT = '/prp-shell-result-v1'
TARGET = 'prp-production'
ACTOR = 'micor-cjj-spec'
REPOSITORY = 'micor-cjj-spec/matrix-prp'
MAX_COMMAND = 8192
MAX_CIPHER_B64 = 40000
MAX_RESULT_B64 = 60000

class InvalidJob(Exception):
    pass

def json_object_no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise InvalidJob('duplicate json field')
        out[k] = v
    return out

def strict_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=json_object_no_duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(InvalidJob('invalid number')))
    except (UnicodeError, ValueError, TypeError) as e:
        raise InvalidJob('invalid JSON') from e

def b64_encode(blob):
    return base64.urlsafe_b64encode(blob).decode().rstrip('=')

def b64_decode(s, limit):
    if not isinstance(s, str) or not (8 <= len(s) <= limit) or re.fullmatch(r'[A-Za-z0-9_-]+', s) is None:
        raise InvalidJob('invalid ciphertext encoding')
    try:
        data = base64.b64decode(s + '=' * (-len(s) % 4), altchars=b'-_', validate=True)
    except (ValueError, base64.binascii.Error) as e:
        raise InvalidJob('invalid ciphertext encoding') from e
    if b64_encode(data) != s:
        raise InvalidJob('noncanonical ciphertext encoding')
    return data

def openssl_cms_encrypt(plain, recipient_cert_pem):
    if not isinstance(recipient_cert_pem, bytes) or len(recipient_cert_pem) > 5000 or not recipient_cert_pem.startswith(b'-----BEGIN CERTIFICATE-----'):
        raise InvalidJob('recipient certificate invalid')
    if not isinstance(plain, bytes) or len(plain) > 18000:
        raise InvalidJob('plaintext too long')
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        cert = Path(directory) / 'recipient.crt'
        cert.write_bytes(recipient_cert_pem)
        r = subprocess.run(['openssl','cms','-encrypt','-binary','-aes-256-gcm',
                            '-outform','DER',str(cert)], input=plain,
                           capture_output=True, timeout=10)
    if r.returncode or not r.stdout:
        raise InvalidJob('CMS encryption failed')
    return r.stdout

def openssl_cms_decrypt(encrypted, recipient_key_path, recipient_cert_path):
    if len(encrypted) > 46000:
        raise InvalidJob('CMS ciphertext too long')
    r = subprocess.run(['openssl','cms','-decrypt','-binary','-inform','DER',
                        '-inkey',str(recipient_key_path), '-recip',str(recipient_cert_path)],
                       input=encrypted, capture_output=True, timeout=10)
    if r.returncode or len(r.stdout) > 18000:
        raise InvalidJob('CMS decryption failed')
    return r.stdout

def create_result_identity():
    """Generate a transient client-only decryption identity; never print its private key."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        key = Path(directory) / 'answer.key'
        cert = Path(directory) / 'answer.crt'
        r = subprocess.run(['openssl','req','-new','-x509','-nodes','-newkey','rsa:3072',
             '-days','1','-subj','/CN=PRP-shell-reply', '-keyout',str(key), '-out',str(cert)],
             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if r.returncode:
            raise InvalidJob('temporary reply certificate generation failed')
        return key.read_bytes(), cert.read_bytes()

def build_command(comment_command, server_cert_pem, timeout=20, now=None):
    """Call only after user explicitly approved the exact shown command.
    Returns (job_uuid, encrypted_public_comment_body, private_answer_key, answer_cert).
    """
    if not isinstance(comment_command, str) or not comment_command.strip() or '\0' in comment_command or len(comment_command.encode('utf-8')) > MAX_COMMAND:
        raise InvalidJob('empty or oversized command')
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise InvalidJob('invalid timeout')
    now = int(time.time() if now is None else now)
    answer_key, answer_cert = create_result_identity()
    job_id = str(uuid.uuid4())
    payload = {'version':1, 'jobId':job_id, 'target':TARGET, 'actor':ACTOR,
               'command':comment_command, 'runSeconds':timeout,
               'issuedAt':now, 'expiresAt':now + 180, 'nonce':uuid.uuid4().hex,
               'answerCertificate':answer_cert.decode('ascii')}
    raw = json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    ciphertext = b64_encode(openssl_cms_encrypt(raw,server_cert_pem))
    if len(ciphertext) > MAX_CIPHER_B64:
        raise InvalidJob('encrypted command too large')
    return job_id, f'{MAGIC_COMMAND} {job_id} {ciphertext}', answer_key, answer_cert

def parse_command_comment(body):
    if not isinstance(body,str) or len(body) > MAX_CIPHER_B64 + 100:
        raise InvalidJob('invalid command comment')
    match = re.fullmatch(r'/prp-shell-v1 ([0-9a-f-]{36}) ([A-Za-z0-9_-]{8,40000})\n?', body)
    if not match:
        raise InvalidJob('invalid command format')
    try:
        if str(uuid.UUID(match.group(1))) != match.group(1):
            raise ValueError()
    except ValueError as e:
        raise InvalidJob('invalid job identifier') from e
    b64_decode(match.group(2), MAX_CIPHER_B64)
    return match.group(1), match.group(2)

def validate_payload(payload, public_job_id, now=None):
    names = {'version','jobId','target','actor','command','runSeconds','issuedAt','expiresAt','nonce','answerCertificate'}
    if not isinstance(payload,dict) or set(payload)!= names or type(payload['version']) is not int or payload['version'] != 1:
        raise InvalidJob('wrong fields')
    if payload['jobId'] != public_job_id or payload['actor'] != ACTOR or payload['target'] != TARGET:
        raise InvalidJob('wrong job, actor or target')
    if not isinstance(payload['nonce'],str) or not re.fullmatch(r'[0-9a-f]{32}',payload['nonce']):
        raise InvalidJob('bad nonce')
    if type(payload['runSeconds']) is not int or not 1 <= payload['runSeconds'] <= 30:
        raise InvalidJob('invalid timeout')
    if type(payload['issuedAt']) is not int or type(payload['expiresAt']) is not int:
        raise InvalidJob('invalid timestamps')
    t = int(time.time() if now is None else now)
    if payload['issuedAt'] > t + 15 or payload['issuedAt'] < t - 300 or not t < payload['expiresAt'] <= payload['issuedAt'] + 300:
        raise InvalidJob('expired job')
    cmd = payload['command']
    if not isinstance(cmd,str) or not cmd.strip() or '\0' in cmd or len(cmd.encode('utf8')) > MAX_COMMAND:
        raise InvalidJob('invalid command')
    cert = payload['answerCertificate']
    if not isinstance(cert,str) or not cert.startswith('-----BEGIN CERTIFICATE-----') or len(cert)>5000:
        raise InvalidJob('invalid result certificate')
    try:
        if str(uuid.UUID(payload['jobId'])) != payload['jobId']:
            raise ValueError()
    except (ValueError,TypeError) as e:
        raise InvalidJob('invalid job UUID') from e
    return payload

def parse_result_comment(body, expected_job_id, answer_key_pem, answer_cert_pem):
    match = re.fullmatch(r'/prp-shell-result-v1 ([0-9a-f-]{36}) ([A-Za-z0-9_-]{8,60000})\n?',body)
    if not match or match.group(1)!=expected_job_id:
        raise InvalidJob('unexpected result comment')
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        key=Path(directory)/'key.pem'
        cert=Path(directory)/'cert.pem'
        key.write_bytes(answer_key_pem)
        key.chmod(0o600)
        cert.write_bytes(answer_cert_pem)
        raw=openssl_cms_decrypt(b64_decode(match.group(2),MAX_RESULT_B64),key,cert)
    data=strict_json(raw)
    if not isinstance(data,dict) or data.get('jobId')!=expected_job_id:
        raise InvalidJob('wrong result job id')
    return data
