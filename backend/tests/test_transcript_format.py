from app.utils.pdf_helper import format_transcript, transcript_to_pdf_bytes


def test_formatting_adds_paragraphs_without_rewriting_words():
    source = ' '.join(['This is a complete lecture sentence.'] * 60)
    formatted = format_transcript(source)
    assert '\n\n' in formatted
    assert formatted.split() == source.split()
    assert format_transcript(formatted) == formatted


def test_named_transcript_pdf_handles_long_titles_and_multiple_pages():
    content = 'A discussion of concurrency, isolation, and durable transactions. ' * 300
    pdf = transcript_to_pdf_bytes(content, title='Database Systems - Transactions and Concurrency', duration_ms=30000)
    assert pdf.startswith(b'%PDF')
    assert len(pdf) > 2000
