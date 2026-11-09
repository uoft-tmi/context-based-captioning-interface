import io
from collections import Counter

import pytest

from app.utils.note_context import MAX_PROMPT_BYTES, pdf_vocabulary, vocabulary_prompt
from tests.helpers import pdf_notes


def test_extracts_spelling_hints_from_real_pdf_text():
    vocabulary = pdf_vocabulary(pdf_notes("PostgreSQL PostgreSQL B-trees MVCC and the lecture slides"))
    assert vocabulary == Counter({"PostgreSQL": 2, "B-trees": 1, "MVCC": 1})
    assert vocabulary_prompt(vocabulary) == "PostgreSQL, B-trees, MVCC"


def test_prompt_is_bounded_for_multilingual_notes_and_keeps_whole_terms():
    vocabulary = Counter({"数据库": 10, "PostgreSQL": 9,
                          **{f"terminology{index}": 1 for index in range(100)}})
    prompt = vocabulary_prompt(vocabulary)
    assert len(prompt.encode("utf-8")) <= MAX_PROMPT_BYTES
    assert prompt.startswith("数据库, PostgreSQL")
    assert set(prompt.split(", ")) <= vocabulary.keys()


@pytest.mark.parametrize('pdf, message', [
    pytest.param(b'not a pdf', 'could not be read', id='invalid-pdf'),
    pytest.param(pdf_notes(''), 'Scanned PDFs need OCR', id='no-selectable-text'),
    pytest.param(b'x' * (10 * 1024 * 1024 + 1), 'up to 10 MB', id='oversized'),
])
def test_unusable_pdfs_have_clear_errors(pdf, message):
    with pytest.raises(ValueError, match=message):
        pdf_vocabulary(pdf)


def test_encrypted_notes_are_rejected():
    from pypdf import PdfWriter

    writer = PdfWriter(clone_from=io.BytesIO(pdf_notes("Database terminology")))
    writer.encrypt("password")
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError, match='Password-protected'):
        pdf_vocabulary(output.getvalue())


def test_only_first_twenty_pages_are_used():
    from pypdf import PdfReader, PdfWriter

    page = PdfReader(io.BytesIO(pdf_notes("PostgreSQL"))).pages[0]
    excluded_page = PdfReader(io.BytesIO(pdf_notes("ExcludedTerm"))).pages[0]
    writer = PdfWriter()
    for _ in range(20):
        writer.add_page(page)
    writer.add_page(excluded_page)
    output = io.BytesIO()
    writer.write(output)
    vocabulary = pdf_vocabulary(output.getvalue())
    assert vocabulary['PostgreSQL'] == 20
    assert 'ExcludedTerm' not in vocabulary
