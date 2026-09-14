import re
from dataclasses import dataclass

# Matches 10-K/10-Q "Item N." style section headers, e.g. "Item 1A. Risk
# Factors" or "Item 7. Management's Discussion". Best-effort: filings vary
# in formatting, so some chunks may end up with no section (None).
SECTION_HEADER_RE = re.compile(r"Item\s+\d+[A-Za-z]?\.\s*[A-Z][^\n]{0,80}")


@dataclass
class TextChunk:
    chunk_index: int
    text: str
    section: str | None


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[TextChunk]:
    if not text:
        return []

    headers = [(m.start(), m.group().strip()) for m in SECTION_HEADER_RE.finditer(text)]
    step = chunk_size - overlap

    chunks = []
    start = 0
    index = 0
    while True:
        end = min(start + chunk_size, len(text))
        chunks.append(
            TextChunk(chunk_index=index, text=text[start:end], section=_section_at(headers, start))
        )
        if end == len(text):
            break
        start += step
        index += 1
    return chunks


def _section_at(headers: list[tuple[int, str]], offset: int) -> str | None:
    current = None
    for position, header in headers:
        if position <= offset:
            current = header
        else:
            break
    return current
