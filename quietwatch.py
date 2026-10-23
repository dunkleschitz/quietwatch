#!/usr/bin/env python3
"""quietwatch — change alerts without the noise.

Poll a JSON source (URL, file, or command output), canonicalize each
record, hash its content, and report only real changes:

  - a record appears            -> NEW
  - a record's content changes  -> MODIFIED
  - a record disappears         -> REMOVED   (disable with --no-removed)

Timestamp-only edits, key reordering, duplicates, and replayed snapshots
are silent. State persists in a JSON file, so each alert fires exactly
once per change, even across restarts.

Stdlib only. Python 3.9+.

`--select PATH` narrows the watch to one JSON subtree before record
extraction (dot-path with optional [N] indices, e.g.
'payload.releases' or 'envs[0].items'); changes outside the selection
stay silent. A selection miss is an error (exit 2), never an empty
watch. Tip: use a separate --state file per --select value, since
record identities come from the selected subtree.

Exit codes: 0 = no changes, 10 = changes detected, 2 = error.
(The distinct "changes" code makes cron/agent use trivial:
`quietwatch ... || [ $? -eq 10 ] && notify`.)
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request

VERSION = "1.1.0"

DEFAULT_VOLATILE = ("last_seen", "fetched_at", "timestamp", "_ts")


def canonical(rec, volatile):
    """Stable string identity for a record: sorted keys, volatile fields
    excluded, nested structures serialized deterministically."""
    keep = {k: v for k, v in rec.items() if k not in volatile}
    return json.dumps(keep, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def rec_hash(rec, volatile):
    return hashlib.sha256(canonical(rec, volatile).encode("utf-8")).hexdigest()[:16]


class Watcher:
    """Diff engine. `state` maps record id -> content hash and round-trips
    through JSON so it can persist between runs."""

    def __init__(self, volatile=DEFAULT_VOLATILE, id_field="id",
                 alert_removed=True, state=None):
        self.volatile = set(volatile)
        self.id_field = id_field
        self.alert_removed = alert_removed
        self.hashes = dict(state or {})

    def check(self, snapshot):
        """Return a list of (kind, id) change events for this snapshot."""
        events = []
        seen = set()
        for rec in snapshot:
            if not isinstance(rec, dict) or self.id_field not in rec:
                continue
            rid = str(rec[self.id_field])
            if rid in seen:            # duplicate inside one snapshot
                continue
            seen.add(rid)
            h = rec_hash(rec, self.volatile)
            old = self.hashes.get(rid)
            if old is None:
                self.hashes[rid] = h
                events.append(("NEW", rid))
            elif h != old:
                self.hashes[rid] = h
                events.append(("MODIFIED", rid))
        if self.alert_removed:
            for rid in list(self.hashes):
                if rid not in seen:
                    del self.hashes[rid]
                    events.append(("REMOVED", rid))
        return events


# ---------- sources ----------

def resolve_select(data, path):
    """Walk a dot-path with optional [N] list indices into parsed JSON.

    Grammar: SEG(.SEG)* where each segment is KEY, KEY[IDX], or [IDX].
    Example: 'payload.releases' or 'envs[0].items'.
    Raises ValueError on any miss (missing key, index out of range,
    malformed segment) so the caller fails loudly (exit 2) instead of
    silently watching an empty subtree.
    """
    cur = data
    for seg in path.split("."):
        m = re.fullmatch(r"([^\[\]]+)?\[(\d+)\]", seg)
        if m:
            key, idx = m.group(1), int(m.group(2))
        elif "[" in seg or "]" in seg or not seg:
            raise ValueError(f"bad --select path {path!r}: "
                             f"malformed segment {seg!r}")
        else:
            key, idx = seg, None
        if key:
            if not isinstance(cur, dict) or key not in cur:
                raise ValueError(f"--select path {path!r}: "
                                 f"key {key!r} not found")
            cur = cur[key]
        if idx is not None:
            if not isinstance(cur, list) or idx >= len(cur):
                raise ValueError(f"--select path {path!r}: "
                                 f"index [{idx}] out of range")
            cur = cur[idx]
    return cur


def load_source(source, select=None):
    """Load a snapshot (list of records) from a URL, file path, or
    'cmd:...' shell command. Accepts a JSON array, a single JSON object,
    or an object with a list under a common key (items/results/data).
    If `select` is given, a dot-path (see resolve_select) is resolved
    against the parsed JSON first, so only that subtree is watched."""
    if source.startswith("cmd:"):
        out = subprocess.run(source[4:], shell=True, capture_output=True,
                             text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(f"command failed ({out.returncode}): {out.stderr[:200]}")
        raw = out.stdout
    elif source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": "quietwatch/1.1"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
    else:
        with open(source, "r", encoding="utf-8") as f:
            raw = f.read()
    data = json.loads(raw)
    if select:
        data = resolve_select(data, select)
    if isinstance(data, dict):
        for key in ("items", "results", "data", "records"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError("source JSON must be an array or object")


# ---------- state ----------

def load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = json.load(f)
        return s.get("hashes", {}), s.get("initialized", False)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, False


def save_state(path, hashes):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"initialized": True, "hashes": hashes}, f,
                  indent=1, sort_keys=True)


# ---------- CLI ----------

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="quietwatch",
        description="Alert only on real changes in a JSON source.")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("source", help="URL, file path, or 'cmd:<shell command>'")
    p.add_argument("--state", default="quietwatch-state.json",
                   help="state file path (default: quietwatch-state.json)")
    p.add_argument("--id-field", default="id",
                   help="record field that holds the unique id (default: id)")
    p.add_argument("--volatile", default=",".join(DEFAULT_VOLATILE),
                   help="comma-separated fields excluded from a record's "
                        "identity (default: %(default)s); use '' for none")
    p.add_argument("--no-removed", action="store_true",
                   help="don't report records that disappear")
    p.add_argument("--alert-on-first-run", action="store_true",
                   help="report every record as NEW on the first run "
                        "(default: first run silently establishes baseline)")
    p.add_argument("--webhook", metavar="URL",
                   help="POST the JSON events array to this URL on change")
    p.add_argument("--select", metavar="PATH",
                   help="dot-path into the JSON before record extraction, "
                        "e.g. 'payload.releases' or 'envs[0].items' "
                        "(default: whole document); a miss is an error")
    args = p.parse_args(argv)

    volatile = tuple(v for v in args.volatile.split(",") if v)
    hashes, initialized = load_state(args.state)
    w = Watcher(volatile=volatile, id_field=args.id_field,
                alert_removed=not args.no_removed, state=hashes)
    try:
        snapshot = load_source(args.source, select=args.select)
    except Exception as e:                       # noqa: BLE001 - CLI surface
        print(f"quietwatch: error: {e}", file=sys.stderr)
        return 2
    events = w.check(snapshot)
    save_state(args.state, w.hashes)

    if not initialized and not args.alert_on_first_run:
        return 0                                 # baseline only, stay quiet
    if not events:
        return 0
    payload = [{"kind": k, "id": rid} for k, rid in events]
    print(json.dumps(payload))
    if args.webhook:
        try:
            req = urllib.request.Request(
                args.webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=30).read()
        except Exception as e:                   # noqa: BLE001
            print(f"quietwatch: webhook failed: {e}", file=sys.stderr)
    return 10


if __name__ == "__main__":
    sys.exit(main())
