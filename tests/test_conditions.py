import json
import os
import plistlib
import subprocess
from datetime import datetime

from semsearch import conditions, config, indexer
from semsearch.search import Searcher

NOW = datetime(2026, 6, 18, 12).timestamp()  # a Thursday


def day(s):
    return datetime.fromisoformat(s).timestamp()


def test_time_words_become_date_ranges():
    rest, c = conditions.parse("上個月的電費單", NOW)
    assert rest == "電費單" and (c["after"], c["before"]) == (day("2026-05-01"), day("2026-06-01"))
    rest, c = conditions.parse("roadmap from last week", NOW)
    assert rest == "roadmap" and (c["after"], c["before"]) == (day("2026-06-08"), day("2026-06-15"))
    assert conditions.parse("去年的報稅", NOW)[1]["after"] == day("2025-01-01")
    assert conditions.parse("先月の請求書", NOW)[0] == "請求書"
    assert conditions.parse("지난달 영수증", NOW)[0] == "영수증"
    assert conditions.parse("昨天下載的", NOW)[0] == ""


def test_look_alike_words_are_not_conditions():
    for q in ["rent at my old Xinyi flat", "舊房子的押金退了沒", "LINE Pay 帳單", "2025 報稅整理",
              "line 3 of the poem", "email from the landlord", "online banking statement", "who owns the SSO migration"]:
        assert conditions.parse(q, NOW)[1] is None, q


def test_sources_need_a_verb_or_preposition():
    assert conditions.parse("LINE 傳來的報價單", NOW)[1]["source"][0] == "LINE"
    assert conditions.parse("the quote from Slack", NOW)[1]["source"][0] == "Slack"
    assert conditions.parse("AirDrop 的截圖", NOW)[1]["source"][0] == "AirDrop"   # always a source
    gm = conditions.parse("Gmail 附件的報價單", NOW)[1]["source"]
    assert conditions.source_matches("Chrome|mail.google.com", gm)
    assert not conditions.source_matches("Chrome|drive.google.com", gm)
    assert conditions.source_matches("sharingd|", conditions.parse("airdrop photo", NOW)[1]["source"])


def _tag(path, agent, page=None):
    subprocess.run(["xattr", "-w", "com.apple.quarantine", f"0083;6a28c8e0;{agent};00000000-0000-0000-0000-000000000000",
                    str(path)], check=True)
    if page:
        data = plistlib.dumps([page + "/file", page], fmt=plistlib.FMT_BINARY)
        subprocess.run(["xattr", "-wx", "com.apple.metadata:kMDItemWhereFroms", data.hex(), str(path)], check=True)


def test_search_keeps_only_files_that_meet_the_conditions(index_env, monkeypatch):
    monkeypatch.setenv("SEMSEARCH_NOW", "2026-06-18")
    quotes = index_env / "quotes"
    quotes.mkdir()
    for name, when, src in [("quote_bathroom.txt", "2026-06-15", ("LINE",)),
                            ("quote_movers.txt", "2026-06-10", ("Chrome", "https://mail.google.com")),
                            ("quote_website.txt", "2026-05-21", ("Slack",))]:
        p = quotes / name
        p.write_text(f"Quotation for {name[6:-4]}: total NT$ 10,000. " * 3)
        os.utime(p, (day(when), day(when)))
        _tag(p, *src)
    cfg = json.loads((config.DATA_DIR / "config.json").read_text())
    (config.DATA_DIR / "config.json").write_text(json.dumps({**cfg, "conditions": True}))
    indexer.run(workers=1)
    assert conditions.read_source(str(quotes / "quote_movers.txt")) == "Chrome|mail.google.com"
    s = Searcher()

    def top(q):
        r = s.search(q, n=5, group=False)
        return [x["name"] for x in r["results"]], r.get("conditions")

    names, info = top("quotation I got on LINE")
    assert names == ["quote_bathroom.txt"] and info["source"] == "LINE"
    assert top("Gmail attachment quotation")[0] == ["quote_movers.txt"]
    assert top("quotation from last month")[0] == ["quote_website.txt"]
    assert top("上週 Gmail 寄來的")[0] == ["quote_movers.txt"]   # nothing but conditions: newest first
    names, info = top("quotation from Telegram")           # nothing meets it: searched without it
    assert info["matched"] == 0 and {n for n in names[:3]} == {"quote_bathroom.txt", "quote_movers.txt", "quote_website.txt"}
