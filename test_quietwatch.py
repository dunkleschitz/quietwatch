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


if __name__ == "__main__":
    test_diff_semantics()
    test_removed()
    test_custom_volatile_and_id()
    test_cli_baseline_then_change()
    print("PASS: all quietwatch tests")
