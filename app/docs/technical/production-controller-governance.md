# PRP production controller governance

## Security and provenance

The production root-owned deploy controller is /usr/local/sbin/prp-release. A successful October 13, 2026 deployment (r38390443099-1) used a production-enhanced controller with online backup, online rehearsal, immutable row fingerprints, staged deployment and recovery checks. The repository's app/deploy/server-release.py is NOT currently an audited byte-identical copy of that enhanced controller. NEVER overwrite the production controller with the repository copy.

The controller approved in `app/deploy/controller-manifest.json` as of 2026-10-14 has SHA256 **`d3e5113cd8d37daabc179a2503dc36d42d1596db822239839b535525e3da75c6`**. The previous trusted controller digest was `d3fbc61f76a3bd06d8192a44226cbef5698a8ef87b555493e9995e672811e687`. The administrator prepared an isolated V17 candidate from that verified previous controller, passed `python3 -m py_compile`, reviewed an exact one-line diff adding `prp_wellness_dish_templates` to the **empty new business table allowlist**, and installed it with an atomic replacement while preserving `root:root 0755`. The administrator then reported a matching installed SHA256 and a healthy `matrix-prp` service. This does not replace independent attestation: every publish reads the installed controller via the restricted SSH command and refuses deployment if the hash differs from the reviewed manifest.

## Production controller approval and installation sequence

1. With normal authorized server administration access, check the installed production controller's hash with sha256sum /usr/local/sbin/prp-release. Verify that it matches controller-manifest.json exactly; investigate any mismatch, do not change the manifest to silence a warning.
2. Locate the *currently installed* root-owned SSH forced-command gateway. Preserve a root-only backup and its owner/group/mode. Review the actual gateway rather than overwriting it with the repository's earlier reference copy.
3. Add only a fixed, read-only case: controller-sha256) exec /usr/bin/sha256sum /usr/local/sbin/prp-release ;;. This command takes NO path argument, opens NO shell, and does NOT run sudo or grant root. Ensure the root-owned 0755 controller is readable by the deployment identity.
4. Validate sh -n on the candidate gateway, diff against the installed gateway, test command routing, then replace atomically under authorized administrative credentials, preserving original permissions and sudoers constraints. Do not expand other SSH command allowlists.
5. From a client using the existing deployment SSH identity and pinned host key, test ssh -T prp-deploy@HOST controller-sha256. The response MUST be one canonical sha256sum line, lowercase 64-digit hex, two spaces and the exact controller path. Verify existing status/check and emergency rollback paths remain available. Confirm shell, port-forwarding and SFTP are still denied.
6. For any controller version change, install and verify the reviewed root-owned candidate **before** merging the matching manifest PR. Otherwise, publish fails closed. For V17, the existing gateway already supports this command and the administrator reported successful replacement; the next publish must still verify the digest independently.

## Runtime enforcement

After the artifact SHA has been validated, the publish job checks out the exact commit SHA and reads its reviewed controller-manifest.json. It obtains the controller digest from the read-only SSH command and runs app/deploy/verify_controller.py. A missing command, mismatch, login banner, malformed output, bad manifest or connection failure aborts deployment BEFORE invoking the controller. The existing deploy/status/check/rollback behaviors are retained; controller attestation is required for deploy/promote, not for emergency check/rollback.

The controller hash is deliberately separate from the application release SHA: application updates may proceed against a recognized production controller, while production controller changes require separate review of root-owned source and a manifest PR. Approved changes to the production controller must be installed by an administrator (backup, tests, verified SHA, atomic replace), not by GitHub Actions. No GitHub token, SSH identity or app artifact may update root-owned controller binaries.

## Completing source-of-truth convergence

Because the existing repository script differs from the deployed enhanced controller, a separate controlled reconciliation remains necessary. From the administrator-reviewed production snapshot, compare, redact secrets, import the genuine production controller implementation onto an isolated branch, run the full 43 production controller regression tests and migration rehearsal, and review the resulting PR. Retain the prior installed SHA256 and root-only backup before any further controller changes. Until that review completes, server-controller version governance covers immutable checksum drift detection, NOT source-code equality with app/deploy/server-release.py.

## Tests

Run python3 -m unittest discover -s app/deploy -p 'test_*.py' -v. New cases verify approved checksum, wrong checksum, missing or tampered output, extra lines, bad path, invalid manifest and gateway read-only command boundary. The publish job enforces the same checks using the installed server's actual bytes.

## Roll-forward and recovery

If governance fails, stop: confirm remote gateway and actual controller hash, audit unexpected drift, and submit a separately reviewed manifest update only after verifying the intended installed controller. Do NOT disable the check to force a deployment. Keep check and rollback operations available for incidents under their preexisting authorization and schema safety rules.
