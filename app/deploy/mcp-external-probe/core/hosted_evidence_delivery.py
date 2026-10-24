"""Local bridge composition. Does not start a transaction or expose a CLI."""
import io
import re
import stat
import zipfile
from attested_evidence_bridge import GateError, checked_json
from trusted_phase_context import accept_with_trusted_reader


def signature_bundle(archive):
    if not isinstance(archive,bytes) or not 1 <= len(archive) <= 3_000_000:
        raise GateError('BUNDLE_ARCHIVE_LIMIT')
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            entries=z.infolist()
            if len(entries)!=1:raise GateError('BUNDLE_FILE_SET')
            item=entries[0]
            if (not re.fullmatch('[A-Za-z0-9_.-]+[.]json',item.filename)
                    or item.file_size>2_000_000 or item.flag_bits&1
                    or stat.S_ISLNK(item.external_attr>>16)):
                raise GateError('BUNDLE_FILE_POLICY')
            raw=z.read(item)
    except (zipfile.BadZipFile,RuntimeError,ValueError):
        raise GateError('BUNDLE_ZIP_INVALID') from None
    if not isinstance(checked_json(raw),dict):raise GateError('BUNDLE_JSON_OBJECT_REQUIRED')
    return raw


class DeliveryVerifier:
    def __init__(self,channel,manifest,pin,cli_path,cli_sha256):
        self.channel,self.manifest,self.pin=channel,manifest,pin
        self.cli_path,self.cli_sha256=cli_path,cli_sha256

    def __call__(self,result,job,key):
        bundle=signature_bundle(result['bundle_archive'])
        def context():
            snapshot,current_key=self.channel.read()
            # A key rotation or changed active phase invalidates this delivery.
            if current_key!=key:raise GateError('DELIVERY_SESSION_CHANGED')
            return snapshot.get('context',{})
        return accept_with_trusted_reader(result['run'],result['artifact'],result['archive'],
            bundle,result['expected'],job,self.manifest,self.pin,key,
            self.cli_path,self.cli_sha256,context)
