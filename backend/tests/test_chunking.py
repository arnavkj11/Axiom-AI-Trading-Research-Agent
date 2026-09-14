from app.filings.chunking import chunk_text


def test_single_short_text_produces_one_chunk():
    chunks = chunk_text("hello world", chunk_size=100, overlap=10)

    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].chunk_index == 0


def _unique_text(length: int) -> str:
    # Non-repeating content (unlike "a" * n) so an off-by-one in the overlap
    # arithmetic can't hide behind coincidentally-equal characters.
    return "".join(f"{i:04d}" for i in range(length))[:length]


def test_long_text_splits_into_multiple_overlapping_chunks():
    text = _unique_text(250)
    chunks = chunk_text(text, chunk_size=100, overlap=20)

    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert chunks[0].text == text[0:100]
    assert chunks[1].text == text[80:180]
    assert chunks[2].text == text[160:250]
    # consecutive chunks overlap by exactly `overlap` characters
    assert chunks[0].text[-20:] == chunks[1].text[:20] == text[80:100]


def test_chunks_cover_the_entire_text_without_gaps():
    text = _unique_text(100)
    chunks = chunk_text(text, chunk_size=30, overlap=5)

    assert [c.text for c in chunks] == [
        text[0:30],
        text[25:55],
        text[50:80],
        text[75:100],
    ]


def test_empty_text_produces_no_chunks():
    assert not chunk_text("", chunk_size=100, overlap=10)


def test_assigns_section_from_item_headers():
    text = (
        "Item 1. Business\n"
        + ("x" * 50)
        + "\nItem 1A. Risk Factors\n"
        + ("y" * 50)
        + "\nItem 7. Management's Discussion\n"
        + ("z" * 50)
    )

    chunks = chunk_text(text, chunk_size=40, overlap=5)

    sections_seen = {c.section for c in chunks}
    assert "Item 1. Business" in sections_seen
    assert "Item 1A. Risk Factors" in sections_seen
    assert "Item 7. Management's Discussion" in sections_seen


def test_text_before_first_header_has_no_section():
    text = "no header yet " + ("a" * 50) + "\nItem 1A. Risk Factors\n" + ("b" * 50)

    chunks = chunk_text(text, chunk_size=30, overlap=0)

    assert chunks[0].section is None
