"""Why a result matched: the query words in its snippet, its sentences, and the snippet window."""
from semsearch import search


def test_hit_words_english_and_endings():
    text = "Renewal notice: the contract renews on 1 May."
    assert set(search._hit_words(text, "contracts renewal date")) == {"contract", "renewal"}


def test_hit_words_cjk_takes_the_longest_pieces():
    # no spaces in the query: the longest pieces found in the text count, filler words do not
    assert search._hit_words("冷氣保固卡：主機保固 7 年", "我的冷氣保固幾年") == ["冷氣保固"]


def test_sentences_are_exact_slices():
    text = "加水淹過，小火燉 90 分鐘。麵條另外煮。\n# Notes\nThe lease runs from July 2025 to June\n2027 and renews."
    out = search._sentences(text)
    assert out[0] == "加水淹過，小火燉 90 分鐘。"
    assert all(p in text for p in out)
    assert any(p.startswith("Notes") for p in out)  # a heading goes with the line after it


def test_pdf_line_break_inside_a_sentence_is_not_a_cut():
    out = search._sentences("payable before 25 April to keep the no-\nclaims discount. Next one here.")
    assert out[0] == "payable before 25 April to keep the no-\nclaims discount."


def test_snippet_starts_at_the_sentence():
    text = "x" * 300 + " Term: 1 July 2025 to 30 June 2027. " + "y" * 300
    s = search._snippet(text, "租約到期", around="Term: 1 July 2025 to 30 June 2027.")
    assert s.startswith("…Term: 1 July")


def _write_pdf(path, pages):
    """A bare PDF with one line of text per page (no PDF library needed)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages))), len(pages)),
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, text in enumerate(pages):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i} 0 R "
                    "/Resources << /Font << /F1 3 0 R >> >> >>")
        stream = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    out, offsets = "%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    path.write_bytes(out.encode("latin-1"))


def test_pdf_page_finds_a_later_page(tmp_path):
    pdf = tmp_path / "policy.pdf"
    _write_pdf(pdf, ["Cover page of the motor policy schedule",
                     "Section 2 lists the drivers named on this policy",
                     "The excess for each claim is NT$ 5,000 under this policy"])
    assert search._pdf_page(str(pdf), 1, ["…The excess for each claim is NT$ 5,000 under…"]) == 3
    assert search._pdf_page(str(pdf), 1, ["drivers named on this policy"]) == 2
    assert search._pdf_page(str(pdf), 1, ["nothing like this appears anywhere"]) is None
