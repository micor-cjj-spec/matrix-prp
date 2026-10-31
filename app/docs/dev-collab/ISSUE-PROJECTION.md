# Requirement Issue status projection

The authoritative status is the `prp-collab-state` commit, not an Issue comment.

After the state ref has an approved protection policy and the implementation is reviewed/merged, the repository owner can manually dispatch `PRP Collaboration Issue Projection` for `REQ-20261031-001`.

This action reads the latest Git state, verifies the exact parent Issue title and expected number, then creates or updates one `github-actions[bot]` comment containing a sanitized task table and commit SHA. It does not rewrite the Issue body or task Issues. It is idempotent when that comment already matches.

Ref changes between fetch and publication are detected before write, and a newer projected version cannot be overwritten with an older one. A narrow race remains between the final ref check and the comment API call. Therefore projection is **eventually consistent** and must never be treated as an authoritative task lock or acceptance signal.

A missing state branch protection policy causes the workflow to fail closed. The workflow has a distinct Issue-write scope and never receives repository contents-write permission. Its review and activation is separate from task coordinator enablement.

This is manual-only; there is no automatic cross-chat refresh or webhook push in MVP v1.
