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


# (full runner at end of file)


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


# ---------- --select ----------

def test_select_nested_wrapper():
    from quietwatch import load_source
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.json")
        with open(p, "w") as f:
            json.dump({"payload": {"releases": BASE}, "meta": {"n": 3}}, f)
        assert load_source(p, select="payload.releases") == BASE


def test_select_index_segments():
    from quietwatch import load_source
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.json")
        with open(p, "w") as f:
            json.dump({"envs": [{"items": BASE}, {"items": []}]}, f)
        assert load_source(p, select="envs[0].items") == BASE
        assert load_source(p, select="envs[1].items") == []


def test_select_single_object_becomes_record():
    from quietwatch import load_source
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.json")
        with open(p, "w") as f:
            json.dump({"app": {"id": "X", "v": 1}}, f)
        assert load_source(p, select="app") == [{"id": "X", "v": 1}]


def test_select_miss_and_malformed_raise():
    from quietwatch import resolve_select
    doc = {"a": {"b": [1, 2]}}
    for bad in ("a.missing", "a.b[9]", "a.b.c", "a[0]", "[0]",
                "a[]", "a[", ".a", "a..b", "a[-1]"):
        try:
            resolve_select(doc, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for %r" % bad)


def test_select_cli_watches_only_subtree():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src.json")
        state = os.path.join(d, "state.json")
        doc = {"unwatched": [{"id": "Z", "v": 1}], "watched": {"items": BASE}}
        with open(src, "w") as f:
            json.dump(doc, f)
        argv = [src, "--state", state, "--select", "watched"]
        assert main(argv) == 0                            # baseline
        doc["unwatched"][0]["v"] = 2                      # outside selection
        with open(src, "w") as f:
            json.dump(doc, f)
        assert main(argv) == 0, "change outside --select must stay silent"
        doc["watched"]["items"][0]["title"] = "alpha2"    # inside selection
        with open(src, "w") as f:
            json.dump(doc, f)
        assert main(argv) == 10


def test_select_miss_exits_2():
    assert _run_cli(json.dumps({"a": 1}), ("--select", "nope")) == 2


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


RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Releases</title>
<item><guid>https://x.example/r/1</guid><title>v1.0</title>
<link>https://x.example/r/1</link><description>first</description>
<pubDate>Mon, 20 Oct 2026 00:00:00 GMT</pubDate></item>
<item><title>v1.1 (no guid)</title>
<link>https://x.example/r/2</link><description>second</description>
<pubDate>Tue, 21 Oct 2026 00:00:00 GMT</pubDate></item>
</channel>
</rss>"""

ATOM_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Blog</title>
<entry><id>urn:post:1</id><title>Hello</title>
<link href="https://x.example/p/1"/>
<updated>2026-10-20T00:00:00Z</updated><summary>intro</summary></entry>
<entry><id>urn:post:2</id><title>World</title>
<link rel="alternate" href="https://x.example/p/2"/>
<published>2026-10-21T00:00:00Z</published><content>body</content></entry>
</feed>"""


def test_rss_parse_identity():
    from quietwatch import parse_feed
    recs = parse_feed(RSS_FEED)
    assert len(recs) == 2
    assert recs[0]["id"] == "https://x.example/r/1"   # guid wins
    assert recs[1]["id"] == "https://x.example/r/2"   # link fallback
    assert recs[1]["published"].startswith("Tue, 21 Oct")


def test_atom_parse_identity():
    from quietwatch import parse_feed
    recs = parse_feed(ATOM_FEED)
    assert len(recs) == 2
    assert recs[0]["id"] == "urn:post:1"
    assert recs[0]["link"] == "https://x.example/p/1"
    assert recs[1]["description"] == "body"           # content fallback
    assert recs[1]["published"] == "2026-10-21T00:00:00Z"


def test_feed_diff_quiet_on_reorder_and_replay():
    w = Watcher()
    from quietwatch import parse_feed
    recs = parse_feed(RSS_FEED)
    assert w.check(recs) == [("NEW", "https://x.example/r/1"),
                             ("NEW", "https://x.example/r/2")]
    assert w.check(list(reversed(recs))) == []        # reorder silent
    assert w.check(recs) == []                        # replay silent


def test_feed_content_change_is_modified():
    w = Watcher()
    from quietwatch import parse_feed
    w.check(parse_feed(RSS_FEED))
    changed = RSS_FEED.replace("second", "second (hotfix)")
    assert w.check(parse_feed(changed)) == [("MODIFIED", "https://x.example/r/2")]


def test_feed_refuses_entities():
    from quietwatch import parse_feed
    evil = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "AAAAAAAAAA">]>'
            '<rss version="2.0"><channel></channel></rss>')
    try:
        parse_feed(evil)
    except ValueError as e:
        assert "ENTITY" in str(e)
    else:
        raise AssertionError("entity-laden feed must be refused")


def test_feed_malformed_exits_2():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "bad.xml")
        state = os.path.join(d, "state.json")
        with open(src, "w") as f:
            f.write("<rss><channel><item>unterminated")
        rc = main(["--state", state, "--kind", "rss", src])
        assert rc == 2


def test_kind_auto_sniffs_feed_and_json():
    with tempfile.TemporaryDirectory() as d:
        feed = os.path.join(d, "feed.xml")
        data = os.path.join(d, "data.json")
        st1 = os.path.join(d, "s1.json")
        st2 = os.path.join(d, "s2.json")
        with open(feed, "w") as f:
            f.write(RSS_FEED)
        with open(data, "w") as f:
            json.dump([{"id": "x", "n": 1}], f)
        from quietwatch import load_source
        assert len(load_source(feed)) == 2            # auto -> feed
        assert load_source(data) == [{"id": "x", "n": 1}]   # auto -> json
        try:
            load_source(feed, kind="json")
        except Exception:
            pass                                     # json on XML errors
        else:
            raise AssertionError("kind=json on a feed must fail")


def test_select_refused_for_feeds():
    with tempfile.TemporaryDirectory() as d:
        feed = os.path.join(d, "feed.xml")
        state = os.path.join(d, "state.json")
        with open(feed, "w") as f:
            f.write(RSS_FEED)
        rc = main(["--state", state, "--kind", "rss", "--select", "channel", feed])
        assert rc == 2


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
    test_rss_parse_identity()
    test_atom_parse_identity()
    test_feed_diff_quiet_on_reorder_and_replay()
    test_feed_content_change_is_modified()
    test_feed_refuses_entities()
    test_feed_malformed_exits_2()
    test_kind_auto_sniffs_feed_and_json()
    test_select_refused_for_feeds()
    print("PASS: all quietwatch tests")
