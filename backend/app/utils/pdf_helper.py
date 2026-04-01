from fpdf import FPDF


def transcript_to_pdf_bytes(transcript: str, *, title: str | None = None) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)

    if title:
        safe_title = title.encode("latin-1", "replace").decode("latin-1")
        pdf.set_font("Helvetica", style="B", size=14)
        pdf.multi_cell(0, 8, safe_title)
        pdf.ln(2)
        pdf.set_font("Helvetica", size=12)

    content = transcript.strip()
    if not content:
        content = "(No transcript available)"

    safe_content = content.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(0, 6, safe_content)
    output = pdf.output()
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    return output.encode("latin-1")
