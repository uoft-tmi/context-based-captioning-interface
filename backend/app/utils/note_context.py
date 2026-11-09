"""Build a small spelling glossary from text PDFs without another model call."""
import io
import re
from collections import Counter

MAX_NOTE_PAGES = 20
MAX_NOTE_CHARACTERS = 50_000
MAX_VOCABULARY_TERMS = 256
# Whisper uses byte-level BPE. A UTF-8 byte cap is a conservative token bound
# without downloading a tokenizer or model at application startup.
MAX_PROMPT_BYTES = 224
_COMMON_WORDS = frozenset("""
a an and are as at be been being but by can could did do does doing for from
had has have having he her here hers him his how i if in into is it its itself
just may me more most my no nor not of on once only or other our out over own
same she should so some such than that the their theirs them themselves then
there these they this those through to too under until up us very was we were
what when where which while who why will with would you your yours also each
example examples figure figures following lecture lectures page pages slide slides
""".split())


def pdf_vocabulary(pdf_bytes: bytes) -> Counter[str]:
    if len(pdf_bytes) > 10 * 1024 * 1024:
        raise ValueError("Lecture notes must be PDFs of up to 10 MB.")
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise ValueError("This PDF could not be read. Export your notes as a text-based PDF and try again.") from exc
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs cannot be used as lecture notes. Upload an unencrypted PDF.")
    excerpts: list[str] = []
    remaining = MAX_NOTE_CHARACTERS
    try:
        for page in reader.pages[:MAX_NOTE_PAGES]:
            text = (page.extract_text() or "")[:remaining]
            excerpts.append(text)
            remaining -= len(text)
            if remaining <= 0:
                break
    except Exception as exc:
        raise ValueError("Text could not be extracted from this PDF. Export a text-based PDF and try again.") from exc
    words = re.findall(r"[^\W\d_][\w]*(?:[-'][\w]+)*", " ".join(excerpts), flags=re.UNICODE)
    # Keep the source spellings, including acronyms, rather than rewriting notes.
    vocabulary = Counter(word for word in words
                         if 2 <= len(word) <= 64 and word.casefold() not in _COMMON_WORDS)
    if not vocabulary:
        raise ValueError("No usable text was found in the first 20 pages. Scanned PDFs need OCR before they can be used as lecture notes.")
    return Counter(dict(vocabulary.most_common(MAX_VOCABULARY_TERMS)))


def vocabulary_prompt(vocabulary: Counter[str]) -> str:
    selected: list[str] = []
    for word, _ in vocabulary.most_common():
        candidate = ", ".join([*selected, word])
        if len(candidate.encode("utf-8")) <= MAX_PROMPT_BYTES:
            selected.append(word)
    return ", ".join(selected)
