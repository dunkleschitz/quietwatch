# Changelog — quietwatch

All notable changes to this project are recorded here. Dates in EDT.
License: MIT (maintainer-approved, Oct 2026).

## [Unreleased]

- First public release preparation: MIT LICENSE added; internal
  pre-publish checklist removed from the README.

## [1.2.0] — 2026-10-23

- `--kind {auto,json,rss}` (default `auto`): RSS 2.0 / Atom 1.0 feeds are
  now watchable sources. `auto` sniffs the body — XML-looking content is
  parsed as a feed, everything else as JSON. Feed entries become records
  `{id, title, link, description, published}` and flow through the same
  canonical-hash diff engine, so new posts alert, reordered/replayed
  snapshots stay silent. Identity: RSS `<guid>` (else `<link>`, else
  `<title>`); Atom `<id>` (else link href, else `<title>`). `--select`
  is refused for feeds (exit 2). Safety: documents with `<!ENTITY`
  declarations are refused outright (billion-laughs vector under stdlib
  ElementTree) and feeds are capped at 5 MiB. 8 new tests (19 total).

## [1.1.0] — 2026-10-22

- `--select PATH`: watch one JSON subtree (dot-path with optional `[N]`
  indices, e.g. `payload.releases`, `envs[0].items`). Resolves before
  the `items`/`results`/`data`/`records` wrapper logic; a miss or
  malformed path is an error (exit 2), never a silent empty watch.
  Changes outside the selection stay silent. 6 new tests.

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
