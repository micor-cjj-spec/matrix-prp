# CI stability #316 — isolated dev reconciliation

Base: 2d27388bd921032027953f170bd20c17de6e1f2e. Reuse #319 test source f156250f200c4397fe47c7538efadfd515feee1f (strengthen plain/consented/replay exactly-once checks), #313 retry semantics, and #325 official Apache 3.9.16 pinned SHA-512 bootstrap. Preserve newer dev test inventory including StagingReleaseDecisionJournalIT and all P3.6 tests. No business source, Dockerfile, SQL, runtime configuration, production workflow, approval registration or hold changes.

The original AI test failure occurs after HTTP 200 but before an observed model call. These stronger assertions expose terminal SSE success/error and independent call counts; they are diagnostic, not proof of the cause or correction of a context leak. If failure persists, investigate without weakening tenant isolation or changing runtime without review.

Maven distribution download and Maven Central POM resolution are separate. Official binary bootstrap is copied byte-for-byte from #325 in the four existing disposable test jobs. Retry wrapper/E2E and backend OCI/disposable Compose builds only before assertions, up to three attempts with 8s/20s delays. Explicit transport markers required for dependency retry; known hard failures take precedence. Private logs removed; only fixed classifications emitted. No alternate repositories, version changes, cache trust expansion, or tolerated failures. This does not guarantee upstream availability. All original downstream inspections and tests run unchanged and must pass.

Acceptance: synthetic process-level retry tests, existing deployment workflow contracts, AI context/replay tests, complete dev-target CI and exact-head independent review. Do not merge or deploy; #316 remains open if runtime failure cause is unresolved.
