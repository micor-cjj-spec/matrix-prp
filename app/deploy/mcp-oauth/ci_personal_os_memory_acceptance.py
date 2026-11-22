#!/usr/bin/env python3
"""T-007 synthetic browser/API acceptance against the disposable MySQL + PRP stack.

No real owner data, model provider or OAuth production permissions are used.
Only the current test browser's ephemeral owner session may access these APIs.
The test never prints JWTs, response bodies, fact values, or source messages.
"""
import os


def _call(page, method, path, payload=None, *, authenticated=True):
    if not path.startswith("/api/") or "?" in path or "#" in path:
        raise RuntimeError("T007_INVALID_TEST_API_PATH")
    response = page.evaluate("""async ({method, path, payload, authenticated}) => {
      const token = localStorage.getItem('matrix-prp-token');
      if (authenticated && !token) throw new Error('MISSING_CI_BROWSER_SESSION');
      const headers = {'Accept': 'application/json'};
      if (authenticated) headers['Authorization'] = 'Bearer ' + token;
      if (payload !== null) headers['Content-Type'] = 'application/json';
      const result = await fetch(path, {
        method, headers, cache: 'no-store', credentials: 'omit',
        body: payload === null ? undefined : JSON.stringify(payload)
      });
      let body = null;
      try { body = await result.json(); } catch (_) {}
      return {status: result.status, data: body?.data ?? null};
    }""", {"method": method, "path": path,
            "payload": payload, "authenticated": authenticated})
    if not isinstance(response, dict) or not isinstance(response.get("status"), int):
        raise RuntimeError("T007_MALFORMED_API_TEST_RESPONSE")
    return response


def _ok(page, method, path, payload=None):
    answer = _call(page, method, path, payload)
    if answer["status"] != 200:
        # Status and fixed step only. Never print body, JWT or submitted facts.
        raise RuntimeError("T007_API_UNEXPECTED_STATUS_" + str(answer["status"]))
    return answer["data"]


def _fact_matches(items, fact_id):
    return isinstance(items, list) and any(
        isinstance(item, dict) and item.get("id") == fact_id for item in items)


def run(page):
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("MCP_E2E_CHROMIUM") != "true"
            or os.environ.get("MCP_E2E_PERSONAL_OS") != "true"
            or page.url.split("/", 3)[:3] != ["https:", "", "prp-e2e.localhost"]):
        raise RuntimeError("T007_DISPOSABLE_CI_ONLY")

    # U01: operator default is off; invalid preview is rejected rather than
    # issuing a model request. This is not proof of enabled live provider flow.
    disabled = _call(page, "POST", "/api/ai/personal-os/extract/preview",
                     {"conversationId": "ci-not-an-owned-conversation", "messageId": 1})
    if disabled["status"] != 404:
        raise RuntimeError("T007_DEFAULT_OFF_EXTRACT_ENDPOINT_NOT_DENIED")

    original = "Synthetic T007 knowledge review fact"
    candidate = {"predicate": "DECLARES_SKILL", "value": original,
                 "validFrom": None, "validTo": None,
                 "requestKey": "ci-t007-memory-first-001"}
    fact_id = None
    try:
        inspection = _ok(page, "POST", "/api/memory/ai-candidates/inspect",
                         [candidate])
        if (not isinstance(inspection, list) or len(inspection) != 1
                or inspection[0] != {"requestKey": candidate["requestKey"],
                                      "disposition": "NEW"}):
            raise RuntimeError("T007_PREFLIGHT_NEW_NOT_MINIMAL")

        submitted = _ok(page, "POST", "/api/memory/ai-candidates", [candidate])
        if not isinstance(submitted, list) or len(submitted) != 1:
            raise RuntimeError("T007_EXPECTED_SINGLE_PENDING_CANDIDATE")
        fact = submitted[0]
        if (not isinstance(fact, dict)
                or not isinstance(fact.get("id"), int) or fact["id"] <= 0
                or fact.get("origin") != "AI_CANDIDATE"
                or fact.get("status") != "PENDING"
                or fact.get("sensitivity") != "RESTRICTED"
                or fact.get("sourceType") != "USER_INPUT"):
            raise RuntimeError("T007_AI_CANDIDATE_AUTO_CONFIRMED_OR_UNRESTRICTED")
        fact_id = fact["id"]

        if _fact_matches(_ok(page, "GET", "/api/memory"), fact_id):
            raise RuntimeError("T007_PENDING_FACT_IN_DEFAULT_CONTEXT")
        if _fact_matches(_ok(page, "GET", "/api/memory/private"), fact_id):
            raise RuntimeError("T007_PENDING_FACT_IN_PRIVATE_CONFIRMED_CONTEXT")
        if not _fact_matches(_ok(page, "GET", "/api/memory/candidates"), fact_id):
            raise RuntimeError("T007_PENDING_FACT_MISSING_FROM_REVIEW_QUEUE")

        # U05: normalized Unicode/case duplicate and only a RELATED hint,
        # not fabricated semantic contradiction or private previous value.
        duplicate = dict(candidate, value="ＳＹＮＴＨＥＴＩＣ T007 KNOWLEDGE REVIEW FACT",
                         requestKey="ci-t007-memory-duplicate-002")
        duplicate_info = _ok(page, "POST",
                             "/api/memory/ai-candidates/inspect", [duplicate])
        if (len(duplicate_info) != 1
                or duplicate_info[0] != {"requestKey": duplicate["requestKey"],
                                          "disposition": "DUPLICATE"}):
            raise RuntimeError("T007_NORMALIZED_DUPLICATE_NOT_IDENTIFIED")
        if _call(page, "POST", "/api/memory/ai-candidates",
                 [duplicate])["status"] != 409:
            raise RuntimeError("T007_SERVER_DID_NOT_BLOCK_DUPLICATE_WRITE")
        related = dict(candidate, value="T007 knowledge review fact",
                       requestKey="ci-t007-memory-related-003")
        related_info = _ok(page, "POST",
                           "/api/memory/ai-candidates/inspect", [related])
        if (len(related_info) != 1
                or related_info[0]["disposition"] != "POSSIBLY_RELATED"):
            raise RuntimeError("T007_RELATED_FACT_NOT_REVIEW_ONLY")

        # An invented CHAT_MESSAGE reference can never be saved as verified.
        invented = dict(candidate, value="Synthetic unrelated proposed assertion",
                        requestKey="ci-t007-memory-fake-source-004",
                        sourceMessageId=987654321, evidenceQuote="invented evidence")
        if _call(page, "POST", "/api/memory/ai-candidates",
                 [invented])["status"] != 404:
            raise RuntimeError("T007_INVENTED_CHAT_SOURCE_ACCEPTED")

        # U04: only a separate explicit owner action confirms the candidate.
        confirmed = _ok(page, "POST", "/api/memory/" + str(fact_id) + "/confirm")
        if not isinstance(confirmed, dict) or confirmed.get("status") != "CONFIRMED":
            raise RuntimeError("T007_OWNER_CONFIRMATION_NOT_APPLIED")
        if _fact_matches(_ok(page, "GET", "/api/memory"), fact_id):
            raise RuntimeError("T007_RESTRICTED_FACT_LEAKED_TO_DEFAULT_CONTEXT")
        if not _fact_matches(_ok(page, "GET", "/api/memory/private"), fact_id):
            raise RuntimeError("T007_CONFIRMED_RESTRICTED_FACT_NOT_OWNER_MANAGEABLE")
        if _fact_matches(_ok(page, "GET", "/api/memory/history/normal"), fact_id):
            raise RuntimeError("T007_RESTRICTED_FACT_LEAKED_TO_NORMAL_HISTORY")
        if _call(page, "GET", "/api/memory/" + str(fact_id),
                 authenticated=False)["status"] not in (401, 403):
            raise RuntimeError("T007_UNAUTHENTICATED_MEMORY_LOOKUP_ALLOWED")

        # Confirmation does not change duplicate enforcement.
        if _call(page, "POST", "/api/memory/ai-candidates",
                 [duplicate])["status"] != 409:
            raise RuntimeError("T007_CONFIRMED_DUPLICATE_WRITE_ACCEPTED")
        if _call(page, "GET", "/api/memory/" + str(fact_id)
                 + "/source-preview")["status"] != 404:
            raise RuntimeError("T007_UNSOURCED_MEMORY_PREVIEW_LEAK")

        # U07: permanent deletion removes this synthetic owner's memory
        # from all management and default retrieval. No chat source is created.
        _ok(page, "DELETE", "/api/memory/" + str(fact_id))
        fact_id = None
        for endpoint in ("/api/memory", "/api/memory/private",
                         "/api/memory/candidates", "/api/memory/history/normal"):
            if any(isinstance(item, dict) and item.get("objectValue") == original
                   for item in (_ok(page, "GET", endpoint) or [])):
                raise RuntimeError("T007_DELETED_FACT_STILL_RETRIEVABLE")
        reused = dict(candidate, requestKey="ci-t007-memory-after-delete-005")
        restated = _ok(page, "POST", "/api/memory/ai-candidates/inspect", [reused])
        if not isinstance(restated, list) or restated[0]["disposition"] != "NEW":
            raise RuntimeError("T007_DELETED_FACT_BLOCKS_FRESH_CANDIDATE")
    finally:
        # Only test-owned synthetic record. Never touch unrelated memories.
        if fact_id is not None:
            _call(page, "DELETE", "/api/memory/" + str(fact_id))

    print("CI_PERSONAL_OS_T007_REAL_MYSQL_AI_CANDIDATE_REVIEW_DEDUP_PRIVACY=PASS")
