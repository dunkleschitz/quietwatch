# Changelog — quietwatch

All notable changes to this project are recorded here. Dates in EDT.
License TBD (awaiting the maintainer's per-project publication approval).

## [Unreleased]
- Added `--version` flag (bench-wide CLI convention: `<tool> <VERSION>`; module-level `VERSION` constant as single source of truth).

### Added
- `CHANGELOG.md`
- 7 new edge-case tests (11 total): source variants (single object,
  `items`/`data` wrapper keys, `cmd:` source), malformed JSON -> exit 2,
  `--alert-on-first-run`, non-dict records skipped, empty `--volatile`,
  corrupt state file forgiven as fresh baseline, REMOVED ids re-NEW on
  return.

## [1.0.0] — 2026-10-21

Initial local v1.
- Single-file stdlib CLI: poll URL / local file / `cmd:` shell command.
- Canonical-hash diffing: sorted keys, volatile fields excluded; alerts on
  NEW / MODIFIED / REMOVED, silent on timestamp-only edits, key reorder,
  in-snapshot duplicates, and replayed snapshots.
- Persistent JSON state: each change alerts exactly once, across restarts.
- Exit codes: 0 = no changes, 10 = changes, 2 = error.
- Optional `--webhook` POST of the events payload; `--no-removed`,
  `--id-field`, `--volatile`, `--alert-on-first-run` flags.
- 4 tests passing.
