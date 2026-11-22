"""Offline-only PRP ChatGPT V2 read-only protocol and projection functions.

NOT AN ENTRYPOINT. Does not implement CMS, GitHub events, SSH, network probes,
replay persistence or user-approval attestation. Never deploy this module as an
authorized remote endpoint without separately reviewed adapters and gates.
"""
import json
import os
import re
import time
import uuid

ACTOR = "micor-cjj-spec"
TARGET = "prp-readonly"
HOST_OPERATIONS = frozenset(("host_root_fs_usage", "prp_app_health"))
REQUEST_FIELDS = frozenset((
    "version", "jobId", "target", "actor", "operation", "parameters",
    "issuedAt", "expiresAt", "nonce", "answerCertificate",
))
MAX_REQUEST_BYTES = 8192
MAX_CERT_CHARS = 5000


class RejectedRequest(Exception):
    """An invalid request; callers must not echo the rejected input."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RejectedRequest("invalid request")
        result[key] = value
    return result


def _bad_number(_value):
    raise RejectedRequest("invalid request")


def parse_decrypted_request(raw, public_job_id, now=None):
    """Validate *already authenticated and CMS-decrypted* request bytes.

    This parser alone cannot authenticate the GitHub event, prove a user's
    ChatGPT consent, decrypt ciphertext, or protect against replay.
    The trusted transport must enforce those boundaries independently.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_REQUEST_BYTES:
        raise RejectedRequest("invalid request")
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"),
                             object_pairs_hook=_unique_object,
                             parse_constant=_bad_number)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise RejectedRequest("invalid request") from exc
    if type(payload) is not dict or set(payload) != REQUEST_FIELDS:
        raise RejectedRequest("invalid request")
    if type(payload["version"]) is not int or payload["version"] != 2:
        raise RejectedRequest("invalid request")
    if payload["actor"] != ACTOR or payload["target"] != TARGET:
        raise RejectedRequest("invalid request")
    if type(payload["operation"]) is not str or payload["operation"] not in HOST_OPERATIONS:
        raise RejectedRequest("invalid request")
    if type(payload["parameters"]) is not dict or payload["parameters"]:
        raise RejectedRequest("invalid request")
    job = payload["jobId"]
    if type(job) is not str or type(public_job_id) is not str or job != public_job_id:
        raise RejectedRequest("invalid request")
    try:
        if str(uuid.UUID(job)) != job:
            raise ValueError("not canonical")
    except (ValueError, AttributeError) as exc:
        raise RejectedRequest("invalid request") from exc
    if type(payload["nonce"]) is not str or re.fullmatch(r"[0-9a-f]{32}", payload["nonce"]) is None:
        raise RejectedRequest("invalid request")
    issued, expires = payload["issuedAt"], payload["expiresAt"]
    instant = int(time.time()) if now is None else now
    if any(type(v) is not int for v in (issued, expires, instant)):
        raise RejectedRequest("invalid request")
    if not (issued <= instant + 15 and issued <= instant < expires
            and 0 < expires - issued <= 180):
        raise RejectedRequest("invalid request")
    cert = payload["answerCertificate"]
    if (type(cert) is not str or len(cert) > MAX_CERT_CHARS or
            re.fullmatch(r"-----BEGIN CERTIFICATE-----\n[A-Za-z0-9+/=\n]{32,4600}\n-----END CERTIFICATE-----\n?", cert) is None):
        raise RejectedRequest("invalid request")
    # PEM shape alone is not a valid X.509 identity or a crypto verification.
    return payload


def root_filesystem_usage(statvfs=os.statvfs):
    """Fixed root-filesystem summary; no user-controlled path or command."""
    try:
        stats = statvfs("/")
        block = stats.f_frsize
        total = stats.f_blocks * block
        used = (stats.f_blocks - stats.f_bfree) * block
        free = stats.f_bavail * block
        if not (type(total) is int and type(used) is int and type(free) is int
                and total > 0 and 0 <= used <= total and 0 <= free <= total):
            raise ValueError("invalid filesystem counters")
        return {
            "totalBytes": total,
            "usedBytes": used,
            "freeBytes": free,
            "usagePercent": round(100.0 * used / total, 2),
        }
    except (OSError, ValueError, AttributeError, TypeError, ZeroDivisionError) as exc:
        raise RejectedRequest("metric unavailable") from exc


def project_health_liveness(http_status, response_body):
    """Map a *trusted fixed-source* HTTP result to non-sensitive fields.

    Does not fetch URLs and never returns raw response content. HTTP 200 alone
    is insufficient. Readiness remains unknown even when liveness is reachable.
    """
    result = {"liveness": "unknown", "readiness": "unknown"}
    if type(http_status) is not int:
        return result
    if http_status != 200:
        # A 4xx HTTP response means the endpoint replied but may require auth,
        # use another route, or be rate-limited. It cannot prove host liveness
        # is down. Classify conservatively without exposing status or body.
        if 500 <= http_status < 600:
            result["liveness"] = "unreachable"
        return result
    if type(response_body) is not bytes or len(response_body) > 2048:
        return result
    try:
        parsed = json.loads(response_body.decode("utf-8", errors="strict"),
                            object_pairs_hook=_unique_object,
                            parse_constant=_bad_number)
        if (type(parsed) is dict and parsed.get("code") == "SUCCESS" and
                type(parsed.get("data")) is dict and
                parsed["data"].get("status") == "UP" and
                parsed["data"].get("service") == "matrix-prp-backend"):
            result["liveness"] = "reachable"
    except (UnicodeError, ValueError, TypeError, RecursionError, RejectedRequest):
        pass
    return result
