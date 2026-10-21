#!/usr/bin/env python3
"""Tests for quietwatch. Run: python3 test_quietwatch.py (or pytest)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from quietwatch import Watcher, main  # noqa: E402

BASE = [
    {"id": "A", "title": "alpha", "sev": "high", "last_seen": "2026-10-01"},
    {"id": "B", "title": "beta", "sev": "med", "last_seen": "2026-10-01"},
    {"id": "C", "title": "gamma", "sev": "crit", "last_seen": "2026-10-01"},
]

NEXT = [
    # timestamp-only change -> silent
    {"id": "A", "title": "alpha", "sev": "high", "last_seen": "2026-10-09"},
    # key reorder -> silent
    {"sev": "med", "id": "B", "title": "beta", "last_seen": "2026-10-01"},
    # in-snapshot duplicate -> silent
    {"id": "B", "title": "beta", "sev": "med", "last_seen": "2026-10-01"},
    # content change -> MODIFIED
    {"id": "C", "title": "gamma (updated)", "sev": "crit", "last_seen": "2026-10-09"},
    # new record -> NEW
    {"id": "D", "title": "delta", "sev": "high", "last_seen": "2026-10-09"},
]


def test_diff_semantics():
    w = Watcher()
    assert w.check(BASE) == [("NEW", "A"), ("NEW", "B"), ("NEW", "C")]
    assert w.check(NEXT) == [("MODIFIED", "C"), ("NEW", "D")]
    assert w.check(NEXT) == [], "replay must be silent"


def test_removed():
    w = Watcher()
    w.check(BASE)
    assert w.check(BASE[:2]) == [("REMOVED", "C")]
    w2 = Watcher(alert_removed=False)
    w2.check(BASE)
    assert w2.check(BASE[:2]) == []


def test_custom_volatile_and_id():
    w = Watcher(volatile=("v",), id_field="key")
    assert w.check([{"key": "x", "n": 1, "v": 1}]) == [("NEW", "x")]
    assert w.check([{"key": "x", "n": 1, "v": 2}]) == []       # volatile only
    assert w.check([{"key": "x", "n": 2, "v": 2}]) == [("MODIFIED", "x")]


def test_cli_baseline_then_change(capsys=None):
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.json")
        state = os.path.join(d, "state.json")
        with open(src, "w") as f:
            json.dump(BASE, f)
        # first run: baseline, quiet, exit 0
        assert main([src, "--state", state]) == 0
        # unchanged: still quiet
        assert main([src, "--state", state]) == 0
        # changed: events printed, exit 10
        with open(src, "w") as f:
            json.dump(NEXT, f)
        assert main([src, "--state", state]) == 10


if __name__ == "__main__":  # original runner kept; full suite below
    test_diff_semantics()
    test_removed()
    test_custom_volatile_and_id()
    test_cli_baseline_then_change()
    print("PASS: core quietwatch tests")


# ---------- edge cases ----------

def _run_cli(src_text, argv_extra=()):
    from quietwatch import main
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.json")
        state = os.path.join(d, "state.json")
        with open(src, "w") as f:
            f.write(src_text)
        return main([src, "--state", state, *argv_extra])


def test_load_source_variants():
    from quietwatch import load_source
    with tempfile.TemporaryDirectory() as d:
        single = os.path.join(d, "single.json")
        with open(single, "w") as f:
            json.dump({"id": "X", "v": 1}, f)
        assert load_source(single) == [{"id": "X", "v": 1}]
        wrapped = os.path.join(d, "wrapped.json")
        with open(wrapped, "w") as f:
            json.dump({"items": BASE}, f)
        assert load_source(wrapped) == BASE
        data_key = os.path.join(d, "data.json")
        with open(data_key, "w") as f:
            json.dump({"data": BASE[:2]}, f)
        assert load_source(data_key) == BASE[:2]
        assert load_source("cmd:echo " + json.dumps(BASE).replace('"', '\\"')) == BASE


def test_malformed_source_exits_2():
    assert _run_cli("{not valid json") == 2


def test_alert_on_first_run():
    # default: first run is a silent baseline
    assert _run_cli(json.dumps(BASE)) == 0
    # with the flag: first run reports everything
    assert _run_cli(json.dumps(BASE), ("--alert-on-first-run",)) == 10


def test_non_dict_records_skipped():
    w = Watcher()
    mixed = [{"id": "A", "v": 1}, "junk", 42, {"noid": True}, {"id": "B", "v": 2}]
    assert w.check(mixed) == [("NEW", "A"), ("NEW", "B")]
    assert w.check(mixed) == []  # replay stays silent


def test_volatile_empty_means_none():
    w = Watcher(volatile=())
    assert w.check([{"id": "x", "ts": "old"}]) == [("NEW", "x")]
    assert w.check([{"id": "x", "ts": "new"}]) == [("MODIFIED", "x")]


def test_corrupt_state_file_is_forgiving():
    from quietwatch import main
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.json")
        state = os.path.join(d, "state.json")
        with open(src, "w") as f:
            json.dump(BASE, f)
        with open(state, "w") as f:
            f.write("garbage{{{")
        # treated as a fresh baseline, not a crash
        assert main([src, "--state", state]) == 0


def test_removed_state_cleanup():
    # after a REMOVED alert, the id is forgotten: if it returns, it's NEW
    w = Watcher()
    w.check(BASE)
    assert w.check(BASE[:2]) == [("REMOVED", "C")]
    assert w.check(BASE) == [("NEW", "C")]


if __name__ == "__main__":
    test_diff_semantics()
    test_removed()
    test_custom_volatile_and_id()
    test_cli_baseline_then_change()
    test_load_source_variants()
    test_malformed_source_exits_2()
    test_alert_on_first_run()
    test_non_dict_records_skipped()
    test_volatile_empty_means_none()
    test_corrupt_state_file_is_forgiving()
    test_removed_state_cleanup()
    print("PASS: all quietwatch tests")
