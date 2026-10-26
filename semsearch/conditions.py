"""Conditions written in plain words: when a file was saved and where it came from.

"上個月的電費單", "the PDF Amy sent on LINE last week", "AirDrop 傳來的截圖", "昨天下載的":
parse() takes the time and source phrases out of the query and returns them as conditions,
so the rest is searched as before and the results are limited to the files that match.

Time words refer to the file's modification date on this Mac (what Finder shows), not to dates
written inside the file. Sources come from what macOS records on every downloaded or received
file: the app that saved it (com.apple.quarantine: Chrome, Safari, LINE, AirDrop = sharingd,
Mail, Slack, Telegram...) and, for browser downloads, the page it came from
(kMDItemWhereFroms: mail.google.com for a Gmail attachment).
"""
import ctypes
import ctypes.util
import os
import plistlib
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

DAY = 86400

# ---- where a file came from -------------------------------------------------------------

# (label, words in any language, quarantine agents, hosts the file was downloaded from)
SOURCES = [
    ("LINE", ["line"], {"LINE"}, ["line.me", "line-apps.com"]),
    ("AirDrop", ["airdrop", "隔空投送", "air drop"], {"sharingd"}, []),
    ("Telegram", ["telegram", "tg"], {"Telegram"}, ["t.me", "telegram.org"]),
    ("WhatsApp", ["whatsapp"], {"WhatsApp"}, ["whatsapp.com", "whatsapp.net"]),
    ("WeChat", ["wechat", "微信"], {"WeChat"}, ["weixin.qq.com"]),
    ("Messenger", ["messenger"], {"Messenger"}, ["messenger.com"]),
    ("Messages", ["imessage", "messages", "訊息", "簡訊"], {"Messages"}, []),
    ("Slack", ["slack"], {"Slack"}, ["slack.com", "slack-edge.com", "slack-files.com"]),
    ("Teams", ["teams"], {"Microsoft Teams", "Teams"}, ["teams.microsoft.com"]),
    ("Discord", ["discord"], {"Discord"}, ["discord.com", "discordapp.com", "discordapp.net"]),
    ("Gmail", ["gmail"], set(), ["mail.google.com", "mail-attachment.googleusercontent.com"]),
    ("Mail", ["mail", "email", "e-mail", "郵件", "信件", "電子郵件", "メール", "이메일", "메일"],
     {"Mail"}, ["mail.google.com", "mail-attachment.googleusercontent.com", "outlook.live.com",
                "outlook.office.com", "outlook.office365.com", "mail.yahoo.com"]),
    ("Google Drive", ["google drive", "drive", "雲端硬碟", "google 雲端"], set(),
     ["drive.google.com", "docs.google.com", "drive.usercontent.google.com"]),
    ("Google Docs", ["google docs", "google 文件"], set(), ["docs.google.com"]),
    ("Notion", ["notion"], set(), ["notion.so", "notion.site"]),
    ("ChatGPT", ["chatgpt", "gpt"], {"ChatGPT"}, ["chatgpt.com", "openai.com", "oaiusercontent.com"]),
    ("Dropbox", ["dropbox"], {"Dropbox"}, ["dropbox.com", "dropboxusercontent.com"]),
    ("OneDrive", ["onedrive"], set(), ["onedrive.live.com", "sharepoint.com", "1drv.ms"]),
    ("Safari", ["safari"], {"Safari"}, []),
    ("Chrome", ["chrome"], {"Chrome", "Google Chrome"}, []),
    ("Firefox", ["firefox"], {"Firefox"}, []),
    ("Edge", ["edge"], {"Microsoft Edge"}, []),
]
# A source word counts only next to words like these ("LINE Pay 帳單" is not a condition,
# "LINE 傳來的帳單" is): before it ...
_SRC_BEFORE = r"(?:從|由|用|透過|經由|在|于|於|from|via|through|on|over|by|で|から|에서|로|으로)"
# ... or after it
_SRC_AFTER = (r"(?:傳來|傳給我|傳的|傳過來|收到|下載|下载|載的|抓的|存的|存下來|上的|附件|寄來|寄的|來的|"
              r"分享|attachments?|downloads?|downloaded|sent|received|shared|files?|で送|から|で受け|"
              r"에서|로 받은|으로 받은)")


def _source_pattern(word):
    w = re.escape(word)
    w = rf"(?<![a-z0-9]){w}(?![a-z0-9])" if word.isascii() else w
    return re.compile(rf"(?:{_SRC_BEFORE}\s*{w}\s*{_SRC_AFTER}?|{w}\s*{_SRC_AFTER})", re.I)


_SOURCE_RES = [(label, [_source_pattern(w) for w in words], agents, hosts)
               for label, words, agents, hosts in SOURCES]
# Words that always mean "this source", without a verb next to them
_BARE = {"AirDrop", "Gmail"}


def source_matches(src, cond):
    """src: the file's stored source "agent|host" (indexer); cond: one SOURCES entry."""
    if not src:
        return False
    agent, _, host = src.partition("|")
    _, _, agents, hosts = cond
    return agent in agents or any(host == h or host.endswith("." + h) for h in hosts)


_libc = None


def _getxattr(path, name):
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        _libc.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.c_uint32, ctypes.c_int]
        _libc.getxattr.restype = ctypes.c_ssize_t
    buf = ctypes.create_string_buffer(8192)
    n = _libc.getxattr(os.fsencode(path), name.encode(), buf, 8192, 0, 0x0001)  # XATTR_NOFOLLOW
    return buf.raw[:n] if n > 0 else None


def read_source(path):
    """"agent|host" for a downloaded or received file ("LINE|", "Chrome|mail.google.com"), or ""."""
    agent = host = ""
    q = _getxattr(path, "com.apple.quarantine")
    if q:
        parts = q.decode("utf-8", "ignore").split(";")
        agent = parts[2] if len(parts) > 2 else ""
    w = _getxattr(path, "com.apple.metadata:kMDItemWhereFroms")
    if w:
        try:
            urls = [u for u in plistlib.loads(w) if isinstance(u, str)]
        except Exception:
            urls = []
        # [file URL, page it was on]: the page says more (a Gmail attachment's file URL is on
        # googleusercontent.com, the page is mail.google.com)
        for u in reversed(urls):
            h = urlparse(u).hostname
            if h:
                host = h.lower()
                break
    return f"{agent}|{host}" if agent or host else ""


# ---- when ------------------------------------------------------------------------------------

def now():
    """The current time; SEMSEARCH_NOW=2026-06-18 pins it (tests and evals)."""
    pinned = os.environ.get("SEMSEARCH_NOW")
    if pinned:
        return datetime.fromisoformat(pinned).timestamp() + 12 * 3600
    return time.time()


def _day(ts):
    d = datetime.fromtimestamp(ts)
    return datetime(d.year, d.month, d.day)


def _month_start(d, back=0):
    y, m = d.year, d.month - back
    while m <= 0:
        y, m = y - 1, m + 12
    return datetime(y, m, 1)


def _range(kind, n, t):
    """(start, end) timestamps for a relative period."""
    today = _day(t)
    week = today - timedelta(days=today.weekday())  # Monday
    if kind == "today":
        return today, today + timedelta(days=1)
    if kind == "yesterday":
        return today - timedelta(days=1), today
    if kind == "daybefore":
        return today - timedelta(days=2), today - timedelta(days=1)
    if kind == "thisweek":
        return week, today + timedelta(days=1)
    if kind == "lastweek":
        return week - timedelta(days=7), week
    if kind == "thismonth":
        return _month_start(today), today + timedelta(days=1)
    if kind == "lastmonth":
        return _month_start(today, 1), _month_start(today)
    if kind == "thisyear":
        return datetime(today.year, 1, 1), today + timedelta(days=1)
    if kind == "lastyear":
        return datetime(today.year - 1, 1, 1), datetime(today.year, 1, 1)
    if kind == "recent":
        return today - timedelta(days=30), today + timedelta(days=1)
    if kind == "pastdays":
        return today - timedelta(days=n), today + timedelta(days=1)
    if kind == "daysago":  # "3 天前": that day, give or take one
        return today - timedelta(days=n + 1), today - timedelta(days=n - 2)
    if kind == "weeksago":
        return week - timedelta(days=7 * n), week - timedelta(days=7 * (n - 1))
    if kind == "monthsago":
        return _month_start(today, n), _month_start(today, n - 1)
    raise ValueError(kind)


_NUM = r"(\d+|[一二兩三四五六七八九十]+)"
_CN = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _num(s):
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + _CN.get(s[1:], 0)
    if s.endswith("十"):
        return _CN.get(s[0], 1) * 10
    return _CN.get(s, 1)


# Longest phrases first, so "上個月" is not read as "月"
TIME_WORDS = [
    # Traditional / Simplified Chinese
    (r"前天", "daybefore"), (r"昨天|昨日|昨晚", "yesterday"), (r"今天|今日|今早|今晚", "today"),
    (r"這(?:個)?(?:禮拜|星期|週|周)|本(?:週|周)|这(?:个)?(?:礼拜|星期|周)", "thisweek"),
    (r"上(?:個|个)?(?:禮拜|礼拜|星期|週|周)", "lastweek"),
    (r"這(?:個)?月|本月|这(?:个)?月", "thismonth"), (r"上(?:個|个)?月", "lastmonth"),
    (r"今年", "thisyear"), (r"去年", "lastyear"),
    (r"最近|近期|最新", "recent"),
    (rf"(?:過去|过去|最近|近)\s*{_NUM}\s*(?:天|日)(?:內|内|以?來|来)?", "pastdays"),
    (rf"(?:過去|过去|最近|近)\s*{_NUM}\s*(?:個|个)?(?:禮拜|礼拜|星期|週|周)(?:內|内|以?來|来)?", "pastweeks"),
    (rf"(?:過去|过去|最近|近)\s*{_NUM}\s*(?:個|个)?月(?:內|内|以?來|来)?", "pastmonths"),
    (rf"{_NUM}\s*天前", "daysago"), (rf"{_NUM}\s*(?:個|个)?(?:禮拜|礼拜|星期|週|周)前", "weeksago"),
    (rf"{_NUM}\s*(?:個|个)月前", "monthsago"),
    # English
    (r"\bthe day before yesterday\b", "daybefore"), (r"\byesterday\b", "yesterday"),
    (r"\btoday\b|\bthis morning\b|\btonight\b", "today"), (r"\bthis week\b", "thisweek"),
    (r"\blast week\b", "lastweek"), (r"\b(?:in the |over the )?past week\b", "pastweek1"), (r"\bthis month\b", "thismonth"),
    (r"\blast month\b", "lastmonth"), (r"\bthis year\b", "thisyear"), (r"\blast year\b", "lastyear"),
    (r"\b(?:recent|recently|lately|latest|newest)\b", "recent"),
    (r"\b(?:in the |over the )?(?:past|last) (\d+) days\b", "pastdays"),
    (r"\b(?:in the |over the )?(?:past|last) (\d+) weeks\b", "pastweeks"),
    (r"\b(?:in the |over the )?(?:past|last) (\d+) months\b", "pastmonths"),
    (r"\b(\d+) days ago\b", "daysago"), (r"\b(\d+) weeks ago\b", "weeksago"),
    (r"\b(\d+) months ago\b", "monthsago"), (r"\ba week ago\b", "weekago1"),
    (r"\ba month ago\b", "monthago1"),
    # Japanese, Korean
    (r"一昨日|おととい", "daybefore"), (r"きのう", "yesterday"), (r"今週", "thisweek"), (r"先週", "lastweek"),
    (r"今月", "thismonth"), (r"先月", "lastmonth"), (r"昨年", "lastyear"),
    (r"그저께|그제", "daybefore"), (r"어제", "yesterday"), (r"오늘", "today"), (r"이번\s*주", "thisweek"),
    (r"지난\s*주", "lastweek"), (r"이번\s*달", "thismonth"), (r"지난\s*달", "lastmonth"),
    (r"올해", "thisyear"), (r"작년", "lastyear"), (r"최근", "recent"),
]
_TIME_RES = [(re.compile(p, re.I), k) for p, k in sorted(TIME_WORDS, key=lambda x: -len(x[0]))]

# Words that only glue a condition to the rest ("的", "那個", "that I", "files") are dropped
# with it when nothing else is left
_GLUE = re.compile(r"^(?:的|那個|那份|那張|那一個|那|个|個|檔案|档案|文件|files?|documents?|stuff|"
                   r"something|anything|things?|that|which|i|me|my|got|saved|edited|modified|"
                   r"opened|made|created|added|changed|downloaded|received|got|改過|改的|編輯|存|新增|開過|的東西|東西|"
                   r"下載|下载|載|收到|存下來|拿到|"
                   r"給我|传来|に|の|を|한|받은|파일|\s|[,，、。.?？!！])+$", re.I)


def parse(q, t=None):
    """Return (query without the condition phrases, conditions or None).

    conditions: {"after": ts, "before": ts, "time": label, "source": SOURCES entry or None}
    """
    t = now() if t is None else t
    rest, cond = q, {}
    for rx, kind in _TIME_RES:
        m = rx.search(rest)
        if not m:
            continue
        n = _num(m.group(1)) if m.groups() and m.group(1) else 1
        k = {"pastweeks": ("pastdays", 7 * n), "pastmonths": ("pastdays", 30 * n),
             "weekago1": ("weeksago", 1), "monthago1": ("monthsago", 1), "pastweek1": ("pastdays", 7)}.get(kind, (kind, n))
        start, end = _range(*k, t)
        cond.update(after=start.timestamp(), before=end.timestamp(), time=m.group(0).strip())
        rest = rest[:m.start()] + " " + rest[m.end():]
        break
    low = rest.lower()
    for entry in _SOURCE_RES:
        label, pats, _, _ = entry
        m = next((m for p in pats for m in [p.search(low)] if m), None)
        if m is None and label in _BARE:
            m = re.search(rf"(?<![a-z0-9]){re.escape(label.lower())}(?![a-z0-9])", low)
        if m:
            cond["source"] = (label, None, entry[2], entry[3])
            rest = rest[:m.start()] + " " + rest[m.end():]
            break
    if not cond:
        return q, None
    rest = re.sub(r"\s+", " ", rest).strip(" 的,，")
    edge = r"(?:(?:from|on|in|at|via|by|of|sent|got)\b|の|的|에서|から|で)"
    rest = re.sub(rf"^(?:{edge}\s*)+|(?:(?<![a-z]){edge})+$", "", rest.strip(), flags=re.I).strip()
    if _GLUE.match(rest or " "):
        rest = ""
    return rest, cond


def keep(cond, mtime, src):
    """Whether a file with this modification time and source meets the conditions."""
    if "after" in cond and not (cond["after"] <= (mtime or 0) < cond["before"]):
        return False
    if cond.get("source") and not source_matches(src, cond["source"]):
        return False
    return True
