"""Build the conditions test corpus: the look-alike files with dates and download sources.

    .venv/bin/python eval/conditions/make_corpus.py <out_dir> [--from <look-alike corpus>]

Copies the look-alike corpus (eval/lookalike, built with its make_corpus.py when --from is not
given), adds eight files that differ mostly by where they came from, then sets every file's
modification date and, for downloaded or received files, the source macOS would record
(com.apple.quarantine with the app, kMDItemWhereFroms with the page). The search date is
pinned to NOW (run with SEMSEARCH_NOW=2026-06-18). Writes manifest.json: date and source per
file. Seeded, everything made up.
"""
import argparse
import json
import os
import plistlib
import random
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
NOW = datetime(2026, 6, 18, 12, 0)  # a Thursday
R = random.Random(20261027)

# Sources: (quarantine agent, page it came from)
LINE = ("LINE", None)
AIRDROP = ("sharingd", None)
GMAIL = ("Chrome", "https://mail.google.com/mail/u/0/")
SLACK = ("Slack", None)
TELEGRAM = ("Telegram", None)
SAFARI = ("Safari", "https://www.example-insurer.com.tw/download")
DRIVE = ("Chrome", "https://drive.google.com/drive/my-drive")
CHATGPT = ("Chrome", "https://chatgpt.com/")
MESSAGES = ("Messages", None)

# Fixed dates for files whose look-alikes differ by age; the rest follow dates in their names
# or get a seeded date between FIRST and NOW
FIRST = datetime(2024, 9, 1)
DATES = {
    "Home/Document (5).txt": "2024-10-03", "Home/Document (3).txt": "2026-02-20",
    "Home/Lease_storage_unit.pdf": "2025-08-14", "Home/車位租約.docx": "2026-06-16",
    "Finance/scan_0017.pdf": "2025-03-11", "Finance/scan_0042.pdf": "2026-05-28",
    "Health/健檢報告_2025.pdf": "2025-11-20", "Health/健檢報告_2026.pdf": "2026-06-10",
    "Travel/Tokyo_2025.md": "2025-03-02", "Travel/Kansai_2026.md": "2026-06-16",
    "Travel/Hotel_Tokyo_booking.pdf": "2025-09-30", "Travel/Hotel_Kyoto_booking.pdf": "2026-02-12",
    "Travel/flight_confirmation (1).txt": "2025-09-28", "Travel/flight_confirmation.txt": "2026-02-10",
    "Travel/eticket_SIN.pdf": "2026-06-17", "Travel/IMG_6012.png": "2026-01-20",
    "Travel/IMG_6020.png": "2026-02-13",
    "Work/Q1_roadmap.md": "2026-01-05", "Work/Q2_roadmap.md": "2026-03-30",
    "Work/Q3_roadmap.md": "2026-06-11", "Work/Q4_roadmap_draft.md": "2026-06-17",
    "Work/meeting_notes_0612.md": "2026-06-12", "Work/meeting_notes_0619.md": "2026-06-18",
    "Work/Pricing_review.pptx": "2026-06-09", "Work/headcount_plan.xlsx": "2026-05-12",
    "Work/年終檢討.docx": "2025-12-29", "Work/OKR_2026H1.md": "2026-01-08",
    "Finance/IMG_5203.png": "2026-05-17", "Finance/IMG_5310.png": "2026-06-03",
    "Finance/2025 報稅整理.xlsx": "2025-05-30", "Finance/budget_2026.md": "2026-01-02",
    "Home/IMG_4471.png": "2026-03-15", "Health/IMG_7002.png": "2026-06-15",
    "Study/ML_midterm_review.pdf": "2026-04-20", "Study/rag_paper_notes.md": "2026-06-08",
    "Home/Scan_20260211.pdf": "2026-04-28", "Finance/機車強制險.pdf": "2026-06-04",
    "Finance/旅平險.pdf": "2025-02-26",
    # added below
    "Downloads/報價單.pdf": "2026-06-15", "Downloads/報價單 (1).pdf": "2026-06-10",
    "Downloads/報價單 (2).pdf": "2026-05-21", "Downloads/IMG_8841.png": "2026-06-16",
    "Downloads/IMG_8850.png": "2026-06-16", "Downloads/document.pdf": "2026-06-12",
    "Downloads/document (1).pdf": "2025-12-03", "Downloads/receipt.pdf": "2026-06-17",
}
SOURCES = {
    "Downloads/報價單.pdf": LINE, "Downloads/報價單 (1).pdf": GMAIL, "Downloads/報價單 (2).pdf": SLACK,
    "Downloads/IMG_8841.png": LINE, "Downloads/IMG_8850.png": AIRDROP,
    "Downloads/document.pdf": GMAIL, "Downloads/document (1).pdf": DRIVE, "Downloads/receipt.pdf": SAFARI,
    "Home/車位租約.docx": LINE, "Finance/IMG_5203.png": LINE, "Finance/IMG_5310.png": LINE,
    "Travel/IMG_6012.png": AIRDROP, "Travel/IMG_6020.png": LINE, "Home/IMG_4471.png": LINE,
    "Health/IMG_7002.png": MESSAGES, "Travel/eticket_SIN.pdf": GMAIL,
    "Travel/Hotel_Kyoto_booking.pdf": GMAIL, "Travel/Hotel_Tokyo_booking.pdf": GMAIL,
    "Finance/health_insurance_summary.docx": GMAIL, "Work/Pricing_review.pptx": SLACK,
    "Work/headcount_plan.xlsx": SLACK, "Study/ML_midterm_review.pdf": TELEGRAM,
    "Finance/機車強制險.pdf": SAFARI, "Finance/旅平險.pdf": SAFARI, "Work/OKR_2026H1.md": DRIVE,
    "Work/年終檢討.docx": DRIVE, "Study/rag_paper_notes.md": CHATGPT, "Health/健檢報告_2026.pdf": GMAIL,
}

NEW = {  # files that differ mostly by source; written as text PDFs and screenshots
    "Downloads/報價單.pdf": "報價單\n客戶：王先生\n項目：浴室整修（防水、磁磚、衛浴設備）\n總價：NT$ 286,000\n有效期限：30 天\n林師傅工作室",
    "Downloads/報價單 (1).pdf": "報價單\n搬家服務：3.5 噸車兩台、人員四名\n樓層：5 樓有電梯 → 3 樓無電梯\n總價：NT$ 12,800\n安心搬家",
    "Downloads/報價單 (2).pdf": "Quotation\nWebsite redesign, 8 pages, CMS setup, 2 rounds of revisions\nTotal: NT$ 95,000\nValid for 14 days\nPixelwork Studio",
    "Downloads/document.pdf": "Offer letter\nPosition: Data Analyst\nStart date: 1 August 2026\nAnnual salary: NT$ 980,000\nPlease reply by 25 June 2026.",
    "Downloads/document (1).pdf": "Club meeting minutes\nAttendees: 12\nBudget for the spring trip approved: NT$ 18,000\nNext meeting in January.",
    "Downloads/receipt.pdf": "Payment receipt\nCompulsory motor insurance renewal\nAmount paid: NT$ 1,227\nPaid by card ****4417",
}
NEW_SHOTS = {
    "Downloads/IMG_8841.png": "聚餐分帳\n燒肉店 6 人\n總額 NT$ 4,860\n每人 NT$ 810\n轉帳給 Kevin",
    "Downloads/IMG_8850.png": "Menu\nSeasonal lunch set NT$ 420\nMatcha latte NT$ 160\nBasque cheesecake NT$ 180",
}


def date_for(rel):
    if rel in DATES:
        d = datetime.fromisoformat(DATES[rel])
    elif m := re.search(r"(20\d\d)-(\d\d)(?:-(\d\d))?", rel):  # 2026-03 bill, 2026-01-10 journal
        y, mo, dd = int(m[1]), int(m[2]), int(m[3] or 0)
        d = datetime(y, mo, dd) if dd else datetime(y, mo, 1) + timedelta(days=9)  # bills come on the 10th
    elif m := re.search(r"_(20\d\d)(\d\d)\.txt$", rel):  # 電信帳單_202503
        d = datetime(int(m[1]), int(m[2]), 1) + timedelta(days=11)
    elif m := re.search(r"meeting_notes_(\d\d)(\d\d)", rel):
        d = datetime(2026, int(m[1]), int(m[2]))
    elif m := re.search(r"INV-2026(\d+)", rel):  # INV-20260103 … INV-20260166: weekly from 3 Jan
        d = datetime(2026, 1, 3) + timedelta(days=7 * ((int(m[1]) - 103) // 7))
    else:
        d = FIRST + timedelta(days=R.randrange((NOW - FIRST).days))
    d = d.replace(hour=R.randrange(8, 23), minute=R.randrange(60))
    return min(d, NOW - timedelta(hours=1))


def set_source(path, agent, page):
    flags = "0083"  # downloaded, not yet opened
    q = f"{flags};{int(datetime.fromtimestamp(os.stat(path).st_mtime).timestamp()):08x};{agent};{uuid.UUID(int=R.getrandbits(128))}"
    subprocess.run(["xattr", "-w", "com.apple.quarantine", q, path], check=True)
    if page:
        file_url = page.rstrip("/") + "/attachment/" + os.path.basename(path)
        data = plistlib.dumps([file_url, page], fmt=plistlib.FMT_BINARY)
        subprocess.run(["xattr", "-wx", "com.apple.metadata:kMDItemWhereFroms", data.hex(), path], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--from", dest="src", help="an existing look-alike corpus to copy")
    a = ap.parse_args()
    out = os.path.abspath(os.path.expanduser(a.out))
    shutil.rmtree(out, ignore_errors=True)
    if a.src:
        shutil.copytree(os.path.expanduser(a.src), out)
    else:
        subprocess.run([sys.executable, os.path.join(REPO, "eval/lookalike/make_corpus.py"), out], check=True)
    sys.path.insert(0, os.path.join(REPO, "eval/lookalike"))
    import make_corpus as lk  # its pdf() and screenshot() writers
    lk.OUT = out
    for rel, text in NEW.items():
        lk.pdf(rel, text)
    for rel, text in NEW_SHOTS.items():
        lk.screenshot(rel, text)
    # Statements dated after NOW would be from the future
    for rel in ("Finance/Statements/Statement_2026-07.pdf", "Finance/Statements/Statement_2026-08.pdf"):
        os.remove(os.path.join(out, rel))
    for i in range(1, 7):
        SOURCES[f"Finance/Statements/Statement_2026-0{i}.pdf"] = GMAIL
    manifest = []
    for root, dirs, files in os.walk(out):
        dirs.sort()
        for f in sorted(files):
            if f.startswith("."):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, out)
            d = date_for(rel)
            os.utime(p, (d.timestamp(), d.timestamp()))
            src = SOURCES.get(rel)
            if src:
                set_source(p, *src)
            manifest.append({"path": rel, "modified": d.strftime("%Y-%m-%d %H:%M"),
                             "source_app": {"sharingd": "AirDrop"}.get(src[0], src[0]) if src else None,
                             "source_page": src[1] if src else None})
    json.dump({"now": NOW.strftime("%Y-%m-%d (%A)"), "files": manifest}, open(os.path.join(out, "..", os.path.basename(out) + ".manifest.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"wrote {len(manifest)} files to {out}")


if __name__ == "__main__":
    main()
