# quietwatch

**Change alerts without the noise.**

Every agent operator eventually reinvents "watch this thing and tell me
when it changes" — and most implementations spam. They diff raw output,
so a bumped timestamp, a reordered JSON key, or a replayed snapshot all
look like "changes," and the human (or agent) on the other end learns to
ignore the alerts entirely.

quietwatch diffs *meaning*, not bytes:

- Records are **canonicalized** (keys sorted, volatile fields like
  `last_seen` excluded) and identified by content hash.
- A record appears → `NEW`. Its content changes → `MODIFIED`. It
  disappears → `REMOVED`.
- Timestamp-only edits, key reordering, duplicates, and replayed
  snapshots are **silent**.
- State persists in a JSON file, so each change alerts **exactly once**,
  even across restarts.

Born as the diff engine inside a working agent's own watchers (model
deprecation alerts, vulnerability-feed monitoring), where false alarms
were costing real attention.

## Install

One file, Python 3.9+, standard library only. Copy it anywhere:

```bash
curl -O https://raw.githubusercontent.com/<owner>/quietwatch/main/quietwatch.py
chmod +x quietwatch.py
```

## Usage

```bash
# Watch a JSON API (first run silently establishes a baseline)
./quietwatch.py https://example.com/api/items --state items-state.json

# Watch a local file
./quietwatch.py ./feed.json --state feed-state.json

# Watch a command's JSON output
./quietwatch.py 'cmd:curl -s https://example.com/api/items' --state s.json

# Alert on everything the first time you run it
./quietwatch.py ./feed.json --state s.json --alert-on-first-run

# Also POST the events to a webhook when something changes
./quietwatch.py ./feed.json --state s.json --webhook https://hooks.example.com/x

# Watch only the 'releases' subtree of a big status document
./quietwatch.py ./status.json --state s.json --select payload.releases
```

Output on change (stdout, one JSON array) and exit code **10**:

```json
[{"kind": "MODIFIED", "id": "CVE-2026-0003"}, {"kind": "NEW", "id": "CVE-2026-0004"}]
```

Exit codes: `0` = no changes, `10` = changes detected, `2` = error —
so cron and agent loops can branch without parsing output.

### Options

| Flag | Default | Meaning |
|---|---|---|
| `--state PATH` | `quietwatch-state.json` | Where the content hashes persist |
| `--id-field NAME` | `id` | Field holding each record's unique id |
| `--volatile a,b,c` | `last_seen,fetched_at,timestamp,_ts` | Fields excluded from a record's identity |
| `--no-removed` | off | Don't report records that disappear |
| `--alert-on-first-run` | off | Report all records as NEW on first run |
| `--webhook URL` | — | POST the events array to this URL on change |
| `--select PATH` | — | Dot-path into the JSON before record extraction (`payload.releases`, `envs[0].items`); a miss is an error (exit 2) |
| `--version` | — | Print version and exit |

Sources may be a JSON array of objects, a single object, or an object
wrapping a list under `items` / `results` / `data` / `records`.
`--select` resolves first, then the wrapper logic applies to the selected
subtree — so `--select payload` on `{"payload": {"items": [...]}}` finds
the list. Tip: use a separate `--state` file per `--select` value, since
record identities are computed from the selected subtree.

## Tests

```bash
python3 test_quietwatch.py   # or pytest
```

Covers: diff semantics, removal alerts, custom volatile/id fields,
baseline-then-change CLI flow, replay silence.

## Known limitations

- Whole-snapshot model: sources that paginate need the caller to fetch
  all pages (or use `cmd:` with a fetch script).
- Records must be JSON objects with an id field; scalar streams aren't
  supported yet.
- State file is plain JSON — fine for one watcher per source; not a
  concurrent-writer database.

## Pre-publish checklist

Per the project charter, nothing ships publicly until the maintainer
approves the publishing account/org and the license. Before
first publication:

1. **Secrets hygiene** — run a secrets scan over the repo and its history
   (`gitleaks detect --source .` or `trufflehog git file://.`), resolve
   every hit, and grep once more for obvious keys/tokens by hand.
2. **History review** — read `git log` and the full diff end-to-end; no
   credentials, private paths, or personal data may be committed.
3. **License** — replace the TBD notice with the maintainer-approved
   LICENSE file.
4. **Approval** — get the maintainer's go-ahead for this project's first
   public publication.

## License

TBD (pending maintainer approval).
