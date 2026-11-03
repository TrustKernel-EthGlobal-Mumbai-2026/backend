# Maintain mode

## Goal

Keep the repository trustworthy, recoverable, and usable without turning maintenance into constant taxonomy churn.

## Audit dimensions

- required folder and system-file presence;
- source-note schema and controlled values;
- missing originals, content-hash mismatches, and ledger inconsistencies;
- duplicate hashes and likely versions;
- broken links, orphaned notes, and unreferenced originals;
- inbox age and processing backlog;
- curated claims without `derived_from` evidence;
- sensitive items exposed to broad indexes or sync;
- rebuildability of full-text/semantic indexes;
- backup freshness and restore-test evidence;
- behavior with community plugins disabled.

Use `scripts/organise.py validate --vault <vault>` for structural checks and add `--verify-hashes` for the slower integrity pass.

Report severity, affected paths, evidence, and the smallest safe repair. Audits are read-only by default. Repairs, merges, migrations, and cleanup require a proposed change set and the appropriate approval boundary.

