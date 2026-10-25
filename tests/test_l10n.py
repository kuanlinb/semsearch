"""Translation files: every language covers the same English texts and keeps their placeholders."""
import json
import re
from pathlib import Path

from semsearch import config

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted((ROOT / "l10n").glob("*.json"))


def _used_in_code():
    used = set()
    for f in ("mac/main.swift", "web/index.html"):
        used |= set(re.findall(r"""\b[LT]\(["']((?:[^"'\\]|\\.)*)["']""", (ROOT / f).read_text()))
    return used


def test_every_language_has_every_text():
    assert {f.stem for f in FILES} >= {"zh-Hant", "zh-Hans", "ja", "ko"}
    used = _used_in_code()
    for f in FILES:
        t = json.loads(f.read_text())
        assert used <= set(t), (f.name, used - set(t))
        assert set(t) == set(json.loads(FILES[0].read_text())), f.name


def test_placeholders_kept():
    for f in FILES:
        for en, tr in json.loads(f.read_text()).items():
            assert sorted(re.findall(r"\{\w+\}", en)) == sorted(re.findall(r"\{\w+\}", tr)), (f.name, en)
            assert tr.strip(), (f.name, en)


def test_place_names_translated():
    t = config.translations("ja")
    assert t["Trash"] == "ゴミ箱" and t["Folder"] == "フォルダ"
    assert config.translations("xx") == {}
