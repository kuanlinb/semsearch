from semsearch import extract


def test_decodes_common_encodings(tmp_path):
    text = "中文測試，汽車保險。" * 10
    cases = {
        "utf8.txt": text.encode(),
        "truncated.txt": text.encode()[:-1],          # cut inside a multi-byte char
        "big5.txt": b"hello " + text.encode("big5"),
        "bom.txt": text.encode("utf-16"),
    }
    for name, data in cases.items():
        p = tmp_path / name
        p.write_bytes(data)
        assert "汽車保險" in extract._read_text(p), name


def test_binary_is_skipped(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"\x00\x01\x02" * 100)
    assert extract._read_text(p) == ""


def test_garbled_pdf_text_is_detected():
    assert extract.garbled("òðòö@ ðò@ ðôð ðððððððñðôøòôðò ðòøðòóùðøø öðkñðøKðð")
    assert not extract.garbled("Das Mädchen fährt über die Brücke nach München.")
    assert not extract.garbled("汽車保險續約重點整理" * 5)


def test_chunks_overlap_and_respect_limits():
    text = "。".join(f"第{i}句話，內容是關於汽車保險的條款" for i in range(200))
    chunks = extract.chunk(text)
    assert 1 < len(chunks) <= extract.config.MAX_CHUNKS_PER_FILE
    assert all(20 <= len(c) <= extract.config.CHUNK_CHARS for c in chunks)


def test_broken_file_returns_empty(tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.4 not really a pdf")
    assert extract.extract(p, ".pdf", p.stat().st_size) == ""
