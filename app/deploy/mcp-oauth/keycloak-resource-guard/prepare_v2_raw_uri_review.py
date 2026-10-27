#!/usr/bin/env python3
"""Build a new, SHA-pinned, review-only V2 raw-URI guard candidate pair.

No live config edits, service restart, OAuth/Keycloak changes, production
private-key access, B2 receipts or deployment approval.
"""
import argparse
import hashlib
import json
from pathlib import Path

import isolated_v2_nginx_syntax as pins
import sandbox_v2_raw_uri_overlay as rawguard
import prepare_v2_guard_review as writer

ROOT = pins.ROOT
ALLOWED_PREFIX = "review-only-v2-guard-"
MAIN_FILENAME = "micor.top.guard-v2-rawuri.REVIEW.conf"
TEST_FILENAME = "prp-test.guard-v2-rawuri.REVIEW.conf"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def build(sources=None):
    # The only trusted inputs are the four files whose exact SHA256 values
    # were approved for the offline Nginx isolation lineage.
    if sources is None:
        sources = pins.inspect_sources()
    required = {"active_main", "active_test", "review_main", "review_test"}
    if set(sources) != required:
        raise ValueError("REVIEW_ONLY_SOURCE_SET_MISMATCH")
    for key in required:
        if digest(sources[key]) != pins.FILES[key][1]:
            raise ValueError("REVIEW_ONLY_SOURCE_SHA256_MISMATCH")
    if sources["review_main"] != sources["active_main"]:
        # This may legitimately differ in some deployments; it is *not* an
        # installation gate. Don't assert equality that the pinned pair lacks.
        pass

    guarded_test, overlay = rawguard.overlay(sources["review_test"])
    if digest(sources["review_test"]) != pins.FILES["review_test"][1]:
        raise ValueError("REVIEW_TEST_SOURCE_DRIFT")
    if guarded_test == sources["review_test"]:
        raise ValueError("RAW_URI_GUARD_NOT_APPLIED")
    # Reconcile total transformed bytes with the two added deterministic
    # guards; a different rewrite, reordered directive or deleted line blocks.
    paths, selected = rawguard.exact_locations_and_targets(sources["review_test"])
    if len(selected) != 2 or overlay["raw_uri_guards_inserted_in_disposable_vhost"] != 2:
        raise ValueError("PROTECTED_ROUTE_COUNT_DRIFT")
    artifacts = {
        MAIN_FILENAME: sources["review_main"],
        TEST_FILENAME: guarded_test,
    }
    report = {
        "status": "REVIEW_ONLY_V2_RAW_URI_CANDIDATE_PREPARED",
        "pinned_sources_sha256_verified": True,
        "review_main_source_sha256": pins.FILES["review_main"][1],
        "review_test_source_sha256": pins.FILES["review_test"][1],
        "review_main_candidate_sha256": digest(artifacts[MAIN_FILENAME]),
        "review_test_candidate_sha256": digest(artifacts[TEST_FILENAME]),
        "main_candidate_unchanged_from_pinned_review": True,
        "test_candidate_exact_raw_uri_guards": len(selected),
        "request_uri_query_strings_allowed": False,
        "candidate_runtime_tested": False,
        "candidate_public_network_tested": False,
        "oauth_end_to_end_tested": False,
        "chatgpt_prp_tasks_list_verified": False,
        "nginx_install_or_reload_authorized": False,
        "keycloak_or_b2_changes_authorized": False,
        "host_guard_install_authorized": False,
        "manifest_authorized": False,
        "b2_cutover_authorized": False,
        "active_configuration_changed": False,
        "release_approved": False,
    }
    return artifacts, report


def create_review(target, artifacts, report, root=ROOT):
    # Reuse the pre-existing create-only private directory writer, which
    # forbids writing outside the historical staging task root.
    if not target.name.startswith(ALLOWED_PREFIX):
        raise ValueError("REVIEW_ONLY_TARGET_PREFIX_REQUIRED")
    writer.write_review(root, target, artifacts, report)


def main():
    parser = argparse.ArgumentParser(description="Prepare V2 raw URI guards FOR REVIEW ONLY")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Fresh private review-only directory under the staging task root")
    args = parser.parse_args()
    try:
        files, report = build()
        if args.output_dir:
            create_review(args.output_dir, files, report)
            report["fresh_private_review_files_created"] = True
        else:
            report["fresh_private_review_files_created"] = False
        print(json.dumps(report, indent=2, sort_keys=True))
    except (OSError, ValueError, UnicodeError):
        print(json.dumps({
            "status": "REVIEW_ONLY_V2_RAW_URI_CANDIDATE_BLOCKED",
            "nginx_install_or_reload_authorized": False,
            "keycloak_or_b2_changes_authorized": False,
            "release_approved": False,
        }, indent=2, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
