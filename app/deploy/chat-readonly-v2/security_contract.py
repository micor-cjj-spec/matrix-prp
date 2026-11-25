"""Offline-only security contracts for PRP readonly V2.

Not a runner, not a public interface, and not cryptographic authentication.
Caller-supplied runtime values must come from GitHub's trusted Actions
context; this module does NOT independently verify their provenance.
ReplayLedger requires an operator-controlled private SQLite directory; no
production filesystem, account, or SSH setup is implemented here.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sqlite3
import time
import uuid
from urllib.parse import quote

from readonly_ops import RejectedRequest, parse_decrypted_request

REPO = "micor-cjj-spec/matrix-prp"
REPO_ID = 1261866723
OWNER = "micor-cjj-spec"
OWNER_ID = 123868412
PREFIX = "/prp-readonly-v2"
MAX_CIPHER_B64 = 24000
EVENT_FIELDS = frozenset(("event_name", "ref", "repository", "repository_id",
                          "actor", "actor_id"))
RESULT_FIELDS = frozenset(("version", "jobId", "operation", "ok", "observedAt",
                           "data", "errorCode"))
ERROR_CODES = frozenset(("REQUEST_REJECTED", "METRIC_UNAVAILABLE",
                         "PROBE_UNAVAILABLE", "INTERNAL_UNAVAILABLE"))
OPS = frozenset(("host_root_fs_usage", "prp_app_health"))


def _uuid(value):
    if type(value) is not str:
        raise RejectedRequest("invalid request")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError("not canonical")
    except (ValueError, AttributeError) as exc:
        raise RejectedRequest("invalid request") from exc
    return value


def _no_duplicates(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise RejectedRequest("invalid result")
        result[k] = v
    return result


def parse_event_fixture(event, trusted_runtime, pinned_issue_number):
    """Pure validation of a simulated GitHub issue_comment message.

    No route number is inferred or defaulted: a separate reviewed V2 Issue
    must be pinned by a future adapter. This function must NEVER be treated
    as independent proof of ChatGPT user's conversational approval.
    """
    if (type(pinned_issue_number) is not int or pinned_issue_number <= 0 or
            type(trusted_runtime) is not dict or
            set(trusted_runtime) != EVENT_FIELDS or
            trusted_runtime != {
                "event_name": "issue_comment", "ref": "refs/heads/main",
                "repository": REPO, "repository_id": REPO_ID,
                "actor": OWNER, "actor_id": OWNER_ID,
            }):
        raise RejectedRequest("invalid event")
    if type(event) is not dict:
        raise RejectedRequest("invalid event")
    repo, sender, issue, comment = (
        event.get("repository"), event.get("sender"),
        event.get("issue"), event.get("comment"),
    )
    if any(type(x) is not dict for x in (repo, sender, issue, comment)):
        raise RejectedRequest("invalid event")
    if event.get("action") != "created":
        raise RejectedRequest("invalid event")
    if (repo.get("full_name") != REPO or type(repo.get("id")) is not int or
            repo["id"] != REPO_ID):
        raise RejectedRequest("invalid event")
    for user in (sender, comment.get("user")):
        if (type(user) is not dict or user.get("login") != OWNER or
                user.get("type") != "User" or
                type(user.get("id")) is not int or user["id"] != OWNER_ID):
            raise RejectedRequest("invalid event")
    if (type(issue.get("number")) is not int or
            issue["number"] != pinned_issue_number or
            "pull_request" in issue or
            type(comment.get("id")) is not int or comment["id"] <= 0):
        raise RejectedRequest("invalid event")
    body = comment.get("body")
    if type(body) is not str or len(body) > MAX_CIPHER_B64 + 100:
        raise RejectedRequest("invalid event")
    match = re.fullmatch(
        r"/prp-readonly-v2 ([0-9a-f-]{36}) ([A-Za-z0-9_-]{8,24000})\n?",
        body,
    )
    if match is None:
        raise RejectedRequest("invalid event")
    job = _uuid(match.group(1))
    token = match.group(2)
    try:
        binary = base64.b64decode(token + "=" * (-len(token) % 4),
                                  altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RejectedRequest("invalid event") from exc
    if base64.urlsafe_b64encode(binary).decode("ascii").rstrip("=") != token:
        raise RejectedRequest("invalid event")
    return {"jobId": job, "ciphertextB64": token, "commentId": comment["id"]}


# The issuer and verifier are deliberately absent from the runtime module.
# The only concrete crypto provider in this candidate is a disposable
# OpenSSL Ed25519 TEST fixture. No live issuer/adapter is authorized.
CONSENT_PURPOSE = "prp-readonly-v2-consent"
MAX_CONSENT_BYTES = 2048
MAX_VERIFIED_CERT_DER = 4096


def _consent_token(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9._:-]{1,96}", value) is None:
        raise RejectedRequest("authorization rejected")
    return value


def _positive_id(value):
    if type(value) is not int or not 0 < value <= (1 << 63) - 1:
        raise RejectedRequest("authorization rejected")
    return value


def verify_consent_fixture(raw_claim, signature, *, raw_request, public_job_id,
                           issuer, key_id, subject, target_instance, generation,
                           issue_number, challenge_comment_id, verified_answer_der,
                           verify_signature, now):
    """Offline contract: verify an independently approved, exact signed claim.

    All keyword-only context (except request bytes) is from a FUTURE trusted
    adapter/configuration. Never read it from the comment or signed claim.
    verified_answer_der must be the actual previously X.509-validated
    recipient certificate; this function only checks equality/fingerprint.
    verify_signature is a pinned Ed25519 verification provider, never an
    attacker-selected key/algorithm. No production provider is implemented.
    A returned digest is not an executable grant and proves no real consent.
    The signed challenge comment ID predates the authorization; binding
    it to an eventual separate execution event requires a trusted adapter.
    """
    try:
        if (type(raw_claim) is not bytes or not 0 < len(raw_claim) <= MAX_CONSENT_BYTES or
                type(signature) is not bytes or len(signature) != 64 or
                not callable(verify_signature) or
                type(verified_answer_der) is not bytes or
                not 0 < len(verified_answer_der) <= MAX_VERIFIED_CERT_DER or
                type(now) is not int or not 0 <= now <= (1 << 63) - 1):
            raise RejectedRequest("authorization rejected")
        request = parse_decrypted_request(raw_request, public_job_id, now=now)
        if not 0 <= request["issuedAt"] <= now < request["expiresAt"] <= (1 << 63) - 1:
            raise RejectedRequest("authorization rejected")
        # parse_decrypted_request checks only PEM shape. Decode and compare
        # the exact DER bytes with the independently validated certificate.
        pem = request["answerCertificate"].strip().splitlines()
        der = base64.b64decode("".join(pem[1:-1]), validate=True)
        if der != verified_answer_der:
            raise RejectedRequest("authorization rejected")
        expected = {
            "version": 1, "purpose": CONSENT_PURPOSE,
            "issuer": _consent_token(issuer), "keyId": _consent_token(key_id),
            "subject": _consent_token(subject),
            "audience": _uuid(target_instance), "generation": _uuid(generation),
            "repoId": REPO_ID, "issueNumber": _positive_id(issue_number),
            "challengeCommentId": _positive_id(challenge_comment_id),
            "jobId": request["jobId"], "operation": request["operation"],
            "parameters": {}, "nonce": request["nonce"],
            "issuedAt": request["issuedAt"], "expiresAt": request["expiresAt"],
            "answerCertificateFingerprint": hashlib.sha256(der).hexdigest(),
        }
        # This deliberately narrow profile contains only ASCII tokens,
        # bounded integers and the empty object. Exact canonical bytes
        # eliminate alternate encodings, duplicate/unknown fields, etc.
        canonical = json.dumps(expected, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False).encode("ascii")
        if raw_claim != canonical:
            raise RejectedRequest("authorization rejected")
        if verify_signature(canonical, signature) is not True:
            raise RejectedRequest("authorization rejected")
        return hashlib.sha256(canonical).hexdigest()
    except Exception as exc:
        # Only a fixed failure is exposed. No untrusted claim/certificate
        # or provider diagnostic should escape to the event/response layer.
        raise RejectedRequest("authorization rejected") from None


class ReplayLedger:
    """Offline-only replay state with explicit provisioning and pinned epoch.

    The generation must come from independent trusted configuration, NOT
    the request or SQLite itself. A live service must never initialize state.
    Restoring any same-generation snapshot remains unsafe without a trusted
    external monotonic witness; no host activation is authorized here.
    """

    # Conservative offline candidate ceilings, not approved live settings.
    # No automatic pruning: saturation closes admission rather than
    # forgetting replay history.
    MAX_DB_BYTES = 2 * 1024 * 1024
    MAX_CLAIMS = 1024
    BUSY_TIMEOUT_SECONDS = 0.5
    CLAIM_BUDGET_SECONDS = 1.0
    PROGRESS_OPS = 1000
    MAX_VM_STEPS = 500_000

    PURPOSE = "execution"
    META_SQL = ("CREATE TABLE ledger_meta (generation TEXT PRIMARY KEY NOT NULL, "
                "purpose TEXT NOT NULL)")
    CLAIMS_SQL = ("CREATE TABLE claims (job_id TEXT PRIMARY KEY, "
                  "nonce TEXT NOT NULL UNIQUE, expires_at INTEGER NOT NULL, "
                  "challenge_id INTEGER UNIQUE, execution_id INTEGER UNIQUE)")

    def __init__(self, path, generation):
        self.path = Path(path)
        self.generation = _uuid(generation)
        if not self.path.is_absolute() or self.path.is_symlink():
            raise RejectedRequest("state unavailable")

    def _check_parent(self):
        parent = self.path.parent
        for ancestor in (parent, *parent.parents):
            if stat.S_ISLNK(ancestor.lstat().st_mode):
                raise RejectedRequest("state unavailable")
        parent_stat = parent.lstat()
        if (not stat.S_ISDIR(parent_stat.st_mode) or
                parent_stat.st_uid != os.geteuid() or
                stat.S_IMODE(parent_stat.st_mode) != 0o700):
            raise RejectedRequest("state unavailable")

    def _prepare_private_file(self):
        """Runtime validation only; never creates or repairs state."""
        try:
            self._check_parent()
            st = self.path.lstat()
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                    or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1
                    or st.st_size > self.MAX_DB_BYTES):
                raise RejectedRequest("state unavailable")
        except (OSError, ValueError) as exc:
            raise RejectedRequest("state unavailable") from exc

    def _connect(self):
        existing_only = "file:" + quote(str(self.path), safe="/") + "?mode=rw"
        return sqlite3.connect(existing_only, isolation_level=None,
                               timeout=self.BUSY_TIMEOUT_SECONDS, uri=True)

    @classmethod
    def initialize(cls, path, generation):
        """Explicit synthetic provisioning, never called by claim.

        An existing file is always refused (even empty or corrupt).
        A failed initialization leaves state unusable; do not auto-retry or
        delete the file. Actual epoch rotation requires independent approval,
        revocation and expiry of all old requests.
        """
        ledger = cls(path, generation)
        connection = None
        try:
            ledger._check_parent()
            fd = os.open(str(ledger.path),
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(fd)
            ledger._prepare_private_file()
            connection = ledger._connect()
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(cls.META_SQL)
            connection.execute(cls.CLAIMS_SQL)
            connection.execute("INSERT INTO ledger_meta VALUES (?, ?)",
                               (ledger.generation, ledger.PURPOSE))
            connection.execute("COMMIT")
            return ledger
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise RejectedRequest("state unavailable") from exc
        finally:
            if connection is not None:
                connection.close()

    def _check_page_budget(self, connection):
        pages = connection.execute("PRAGMA main.page_count").fetchone()[0]
        page_size = connection.execute("PRAGMA main.page_size").fetchone()[0]
        if (type(pages) is not int or type(page_size) is not int or
                pages < 0 or page_size <= 0 or
                pages * page_size > self.MAX_DB_BYTES):
            raise RejectedRequest("state unavailable")

    def _verify_state(self, connection):
        # Exact schema and exactly one independently expected generation.
        # Reject an empty/replaced/legacy database without repairing it.
        # Enumerate every schema object, including SQLite autoindexes.
        # Never use LIKE sqlite_%: underscore is a wildcard, not literal.
        expected = {
            ("table", "ledger_meta", "ledger_meta", self.META_SQL),
            ("table", "claims", "claims", self.CLAIMS_SQL),
            ("index", "sqlite_autoindex_ledger_meta_1", "ledger_meta", None),
            ("index", "sqlite_autoindex_claims_1", "claims", None),
            ("index", "sqlite_autoindex_claims_2", "claims", None),
            ("index", "sqlite_autoindex_claims_3", "claims", None),
            ("index", "sqlite_autoindex_claims_4", "claims", None),
        }
        objects = connection.execute(
            "SELECT type, name, tbl_name, sql FROM main.sqlite_schema"
        ).fetchall()
        if len(objects) != len(expected) or set(objects) != expected:
            raise RejectedRequest("state unavailable")
        # A syntactically valid database can have missing unique-index
        # entries. INSERT alone need not detect them. Check the entire
        # database inside the same BEGIN IMMEDIATE transaction as claim;
        # quick_check does not verify table/index consistency.
        if connection.execute("PRAGMA main.integrity_check(1)").fetchall() != [("ok",)]:
            raise RejectedRequest("state unavailable")
        if connection.execute("SELECT generation, purpose FROM ledger_meta LIMIT 2"
                              ).fetchall() != [(self.generation, self.PURPOSE)]:
            raise RejectedRequest("state unavailable")

    def claim(self, job_id, nonce, expires_at, now=None, *,
              challenge_comment_id=None, execution_comment_id=None):
        _uuid(job_id)
        if challenge_comment_id is not None or execution_comment_id is not None:
            challenge_comment_id = _positive_id(challenge_comment_id)
            execution_comment_id = _positive_id(execution_comment_id)
            if challenge_comment_id == execution_comment_id:
                raise RejectedRequest("invalid request")
        elif self.PURPOSE == "receipt":
            raise RejectedRequest("invalid request")
        timestamp = int(time.time()) if now is None else now
        if (type(nonce) is not str or re.fullmatch(r"[0-9a-f]{32}", nonce) is None or
                type(expires_at) is not int or type(timestamp) is not int or
                expires_at <= timestamp or expires_at - timestamp > 180 or
                not 0 <= timestamp < expires_at <= (1 << 63) - 1):
            raise RejectedRequest("invalid request")
        connection = None
        deadline = time.monotonic() + self.CLAIM_BUDGET_SECONDS
        steps = 0

        def budget_exhausted():
            nonlocal steps
            steps += self.PROGRESS_OPS
            return int(steps >= self.MAX_VM_STEPS or
                       time.monotonic() >= deadline)

        def check_deadline():
            if time.monotonic() >= deadline:
                raise RejectedRequest("state unavailable")

        try:
            self._prepare_private_file()
            check_deadline()
            connection = self._connect()
            connection.set_progress_handler(budget_exhausted, self.PROGRESS_OPS)
            connection.execute("BEGIN IMMEDIATE")
            check_deadline()
            self._check_page_budget(connection)
            self._verify_state(connection)
            if connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0] >= self.MAX_CLAIMS:
                raise RejectedRequest("state unavailable")
            if challenge_comment_id is not None:
                # The same comment must never switch roles on another claim.
                if connection.execute(
                    "SELECT 1 FROM claims WHERE challenge_id IN (?,?) "
                    "OR execution_id IN (?,?) LIMIT 1",
                    (challenge_comment_id, execution_comment_id,
                     challenge_comment_id, execution_comment_id),
                ).fetchone() is not None:
                    raise RejectedRequest("already claimed")
            connection.execute(
                "INSERT INTO claims (job_id,nonce,expires_at,challenge_id,execution_id) "
                "VALUES (?,?,?,?,?)",
                (job_id, nonce, expires_at, challenge_comment_id, execution_comment_id),
            )
            # Do not commit growth beyond the allowed database page budget.
            self._check_page_budget(connection)
            check_deadline()
            connection.execute("COMMIT")
            return True
        except sqlite3.IntegrityError as exc:
            raise RejectedRequest("already claimed") from exc
        except (sqlite3.Error, OSError, OverflowError) as exc:
            raise RejectedRequest("state unavailable") from exc
        finally:
            # close rolls back any unfinished transaction, including a
            # RejectedRequest raised by schema/generation verification.
            if connection is not None:
                connection.close()

class ReceiptLedger(ReplayLedger):
    """Separate synthetic client-consumption state; never an execution ledger."""

    PURPOSE = "receipt"


def _safe_data(operation, data):
    if type(data) is not dict:
        raise RejectedRequest("invalid result")
    if operation == "host_root_fs_usage":
        if set(data) != {"totalBytes", "usedBytes", "freeBytes", "usagePercent"}:
            raise RejectedRequest("invalid result")
        total, used, free, pct = (
            data["totalBytes"], data["usedBytes"], data["freeBytes"],
            data["usagePercent"],
        )
        if (any(type(v) is not int or v < 0 or v > (1 << 63) - 1
                for v in (total, used, free)) or
                total == 0 or used > total or free > total or
                used + free > total or
                type(pct) not in (int, float) or not 0 <= pct <= 100 or
                abs(pct - 100 * used / total) > .02):
            raise RejectedRequest("invalid result")
    elif operation == "prp_app_health":
        if (set(data) != {"liveness", "readiness"} or
                data["liveness"] not in ("reachable", "unreachable", "unknown") or
                data["readiness"] != "unknown"):
            raise RejectedRequest("invalid result")
    else:
        raise RejectedRequest("invalid result")
    return data


def encode_result(job_id, operation, observed_at, data=None, error_code=None):
    """Produce an allowlisted JSON payload. CMS encryption is NOT provided."""
    _uuid(job_id)
    if (operation not in OPS or type(observed_at) is not int or
            observed_at < 0):
        raise RejectedRequest("invalid result")
    if error_code is None:
        payload_data = _safe_data(operation, data)
        ok = True
    else:
        if (type(error_code) is not str or error_code not in ERROR_CODES or
                data is not None):
            raise RejectedRequest("invalid result")
        payload_data = {}
        ok = False
    result = {
        "version": 2, "jobId": job_id, "operation": operation, "ok": ok,
        "observedAt": observed_at, "data": payload_data,
        "errorCode": error_code,
    }
    return json.dumps(result, sort_keys=True, separators=(",", ":")).encode()


def parse_result(raw, expected_job_id, expected_operation):
    """Validate a result AFTER authenticated CMS decryption by a caller."""
    _uuid(expected_job_id)
    if (type(expected_operation) is not str or
            expected_operation not in OPS or type(raw) is not bytes or
            not 0 < len(raw) <= 2048):
        raise RejectedRequest("invalid result")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"),
                           object_pairs_hook=_no_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               RejectedRequest("invalid result")))
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise RejectedRequest("invalid result") from exc
    if (type(value) is not dict or set(value) != RESULT_FIELDS or
            type(value["version"]) is not int or value["version"] != 2 or
            value["jobId"] != expected_job_id or
            value["operation"] != expected_operation or
            type(value["ok"]) is not bool or
            type(value["observedAt"]) is not int or value["observedAt"] < 0):
        raise RejectedRequest("invalid result")
    if value["ok"]:
        if value["errorCode"] is not None:
            raise RejectedRequest("invalid result")
        _safe_data(expected_operation, value["data"])
    else:
        if (type(value["errorCode"]) is not str or
                value["errorCode"] not in ERROR_CODES or
                value["data"] != {}):
            raise RejectedRequest("invalid result")
    return value


# Response-side binding is separate from consent and CMS confidentiality.
RESULT_PURPOSE = "prp-readonly-v2-result"
MAX_RESULT_BINDING_BYTES = 2048


def result_binding_fixture(raw_result, *, consent_digest, job_id, operation,
                           nonce, target_instance, generation, issue_number,
                           challenge_comment_id, execution_comment_id,
                           server_key_id, issued_at, expires_at, now):
    """Canonical signed metadata for an offline response, not an issuer.

    Context must come from the independently verified consent and trusted
    event/recipient configuration. Never derive expectations from response.
    The execution comment must be distinct from the inert challenge; their
    relationship is NOT independently authenticated by this function.
    """
    try:
        if (type(consent_digest) is not str or
                re.fullmatch(r"[0-9a-f]{64}", consent_digest) is None or
                type(nonce) is not str or re.fullmatch(r"[0-9a-f]{32}", nonce) is None or
                any(type(v) is not int for v in (issued_at, expires_at, now)) or
                not 0 <= issued_at <= now < expires_at <= (1 << 63) - 1 or
                not 0 < expires_at - issued_at <= 180):
            raise RejectedRequest("response rejected")
        challenge = _positive_id(challenge_comment_id)
        execution = _positive_id(execution_comment_id)
        if challenge == execution:
            raise RejectedRequest("response rejected")
        value = parse_result(raw_result, job_id, operation)
        if not issued_at <= value["observedAt"] <= now < expires_at:
            raise RejectedRequest("response rejected")
        binding = {
            "version": 1, "purpose": RESULT_PURPOSE,
            "serverKeyId": _consent_token(server_key_id),
            "consentDigest": consent_digest,
            "resultDigest": hashlib.sha256(raw_result).hexdigest(),
            "jobId": _uuid(job_id), "operation": operation, "nonce": nonce,
            "audience": _uuid(target_instance), "generation": _uuid(generation),
            "repoId": REPO_ID, "issueNumber": _positive_id(issue_number),
            "challengeCommentId": challenge, "executionCommentId": execution,
            "observedAt": value["observedAt"], "issuedAt": issued_at,
            "expiresAt": expires_at,
        }
        return json.dumps(binding, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except Exception:
        raise RejectedRequest("response rejected") from None


def verify_signed_result_fixture(raw_result, raw_binding, signature, *,
                                 verify_signature, consent_digest, job_id,
                                 operation, nonce, target_instance, generation,
                                 issue_number, challenge_comment_id,
                                 execution_comment_id, server_key_id,
                                 issued_at, expires_at, now):
    """Check exact response metadata and pinned separate server signature.

    No actual server signer/provider or trusted event adapter is implemented.
    Success proves the offline cryptographic contract only, not execution
    on a specific host. The caller is responsible for trusted expectations,
    certificate validation, revocation, and one-time response consumption.
    """
    try:
        if (type(raw_binding) is not bytes or
                not 0 < len(raw_binding) <= MAX_RESULT_BINDING_BYTES or
                type(signature) is not bytes or len(signature) != 64 or
                not callable(verify_signature)):
            raise RejectedRequest("response rejected")
        expected = result_binding_fixture(
            raw_result, consent_digest=consent_digest, job_id=job_id,
            operation=operation, nonce=nonce, target_instance=target_instance,
            generation=generation, issue_number=issue_number,
            challenge_comment_id=challenge_comment_id,
            execution_comment_id=execution_comment_id, server_key_id=server_key_id,
            issued_at=issued_at, expires_at=expires_at, now=now)
        if raw_binding != expected or verify_signature(expected, signature) is not True:
            raise RejectedRequest("response rejected")
        return parse_result(raw_result, job_id, operation)
    except Exception:
        raise RejectedRequest("response rejected") from None


def _canonical_fixture(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _check_active_fixture(provider, scope):
    """Trusted simulated revocation authority; exact True only, never cache."""
    if not callable(provider) or provider(scope) is not True:
        raise RejectedRequest("authorization unavailable")


def claim_bound_execution_fixture(event, trusted_runtime, *, raw_request,
                                  raw_claim, signature, trusted_mapping,
                                  consent_context, active_check, ledger):
    """Offline composition only; not a real GitHub or authorization adapter.

    trusted_mapping is canonical bytes from an independently authenticated
    mapping of an inert challenge to a created execution comment, ciphertext
    and decrypted request. This function never establishes that provenance.
    consent_context and active_check are independently configured fixtures.
    A successful return is a digest, not permission to execute a live command.
    """
    try:
        if (type(consent_context) is not dict or
                type(trusted_mapping) is not bytes or
                not 0 < len(trusted_mapping) <= 2048 or
                type(ledger) is not ReplayLedger):
            raise RejectedRequest("authorization unavailable")
        context = dict(consent_context)
        # No duplicate source of truth for request or public job ID.
        if "raw_request" in context or "public_job_id" in context:
            raise RejectedRequest("authorization unavailable")
        entry = parse_event_fixture(event, trusted_runtime, context["issue_number"])
        digest = verify_consent_fixture(raw_claim, signature,
            raw_request=raw_request, public_job_id=entry["jobId"], **context)
        request = parse_decrypted_request(raw_request, entry["jobId"], now=context["now"])
        challenge = _positive_id(context["challenge_comment_id"])
        execution = _positive_id(entry["commentId"])
        if challenge == execution or ledger.generation != context["generation"]:
            raise RejectedRequest("authorization unavailable")
        # Require the trusted independent mapping to bind the actual event,
        # canonical ciphertext token and exact bytes from the trusted decryptor.
        expected = _canonical_fixture({
            "purpose": "prp-readonly-v2-execution-mapping",
            "repoId": REPO_ID, "issueNumber": _positive_id(context["issue_number"]),
            "actorId": OWNER_ID, "jobId": request["jobId"],
            "nonce": request["nonce"], "consentDigest": digest,
            "challengeCommentId": challenge, "executionCommentId": execution,
            "audience": context["target_instance"], "generation": ledger.generation,
            "ciphertextDigest": hashlib.sha256(entry["ciphertextB64"].encode("ascii")).hexdigest(),
            "requestDigest": hashlib.sha256(raw_request).hexdigest(),
        })
        if trusted_mapping != expected:
            raise RejectedRequest("authorization unavailable")
        # The independent authority resolves consentDigest to issuer, key,
        # subject, recipient cert, epoch and grant; deny unknown/revoked.
        _check_active_fixture(active_check, expected)
        ledger.claim(request["jobId"], request["nonce"], request["expiresAt"],
                     context["now"], challenge_comment_id=challenge,
                     execution_comment_id=execution)
        # If authorization was revoked while claiming, burn the claim and
        # refuse the handoff. Never release/retry an uncertain claim.
        _check_active_fixture(active_check, expected)
        return digest
    except Exception:
        raise RejectedRequest("authorization unavailable") from None


def consume_signed_result_fixture(raw_result, raw_binding, signature, *,
                                  receipt_ledger, active_check, verify_signature,
                                  response_context):
    """Verify and atomically consume one result in a separate client ledger.

    Context is pinned independently of the response; its generation must
    match the receipt ledger and the original verified authorization.
    A post-claim denial burns the receipt. This does not provide a live
    revocation barrier, response delivery guarantee or rollback protection.
    """
    try:
        if type(receipt_ledger) is not ReceiptLedger or type(response_context) is not dict:
            raise RejectedRequest("response unavailable")
        context = dict(response_context)
        if receipt_ledger.generation != context["generation"]:
            raise RejectedRequest("response unavailable")
        result = verify_signed_result_fixture(raw_result, raw_binding, signature,
                                               verify_signature=verify_signature, **context)
        # A trusted authority must resolve consentDigest and serverKeyId,
        # and check certificate, instance, epoch, event and authorization.
        # Scope is already signature-verified canonical metadata.
        _check_active_fixture(active_check, raw_binding)
        receipt_ledger.claim(context["job_id"], context["nonce"], context["expires_at"],
                             context["now"],
                             challenge_comment_id=context["challenge_comment_id"],
                             execution_comment_id=context["execution_comment_id"])
        _check_active_fixture(active_check, raw_binding)
        return result
    except Exception:
        raise RejectedRequest("response unavailable") from None
