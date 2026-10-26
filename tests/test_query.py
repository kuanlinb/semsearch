from semsearch.search import is_lookup, match_places, parse_types


def test_codes_and_numbers_are_lookups():
    for q in ["58210377", "NT$18,600", "1,718", "Q7XK2P", "MXV-2291", "B2-17", "INV-20260124"]:
        assert is_lookup(q), q
    for q in ["Q3 roadmap", "seat 32A", "2025 年 8 月電費", "HARUKA", "Q3", "豆瓣醬", "how much is my rent"]:
        assert not is_lookup(q), q


def test_type_words_become_preferences():
    assert parse_types("汽車保險的保單 pdf") == ("汽車保險的保單", {".pdf"})
    assert parse_types("報告pdf")[1] == {".pdf"}        # glued to Chinese text
    assert parse_types("wordle game") == ("wordle game", None)  # not the word "word"
    assert ".app" in parse_types("photo editing app")[1]


def test_places_match_only_on_intent():
    assert [r["path"].endswith("/.Trash") for r in match_places("垃圾桶")] == [True]
    assert match_places("open trash")
    assert match_places("files in the trash")           # strong place: substring is enough
    assert not match_places("財務文件")                   # "文件" inside a longer query
    assert match_places("downloads")


def test_english_place_words_need_word_boundaries():
    assert not match_places("binary search notes")      # contains "bin"
    assert not match_places("kitchen cabinet invoice")
    assert match_places("empty the bin")
