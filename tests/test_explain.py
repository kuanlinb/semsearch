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
