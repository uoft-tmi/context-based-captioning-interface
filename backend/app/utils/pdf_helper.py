"""Readable transcript exports with stable paragraphs and session metadata."""
import re
from datetime import datetime

from fpdf import FPDF


def format_transcript(transcript: str) -> str:
    paragraphs = []
    for block in re.split(r'\n\s*\n', transcript.strip()):
        block = ' '.join(block.split())
        if not block:
            continue
        sentences = re.split(r'(?<=[.!?])\s+', block)
        current = ''
        for sentence in sentences:
            if current and len(current) + len(sentence) > 650:
                paragraphs.append(current)
                current = ''
            current = f'{current} {sentence}'.strip()
        if current:
            paragraphs.append(current)
    return '\n\n'.join(paragraphs)


def _printable(text: str) -> str:
    # Built-in PDF fonts use WinAnsi. The original UTF-8 transcript stays in SQL.
    return text.replace('\u2013', '-').replace('\u2014', '-').encode('cp1252', 'replace').decode('cp1252')


class TranscriptPDF(FPDF):
    def header(self):
        self.set_fill_color(255, 255, 255)
        self.rect(0, 0, self.w, self.h, 'F')
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(23, 107, 96)
        self.cell(0, 6, 'LECTURE CAPTIONING', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(218, 228, 226)
        self.line(self.l_margin, self.get_y() + 2, self.w - self.r_margin, self.get_y() + 2)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(105, 118, 124)
        self.cell(0, 5, f'Transcript  |  Page {self.page_no()}/{{nb}}', align='R')


def transcript_to_pdf_bytes(transcript: str, *, title: str | None = None, created_at: datetime | None = None, duration_ms: int = 0) -> bytes:
    pdf = TranscriptPDF()
    pdf.core_fonts_encoding = 'cp1252'
    pdf.set_margins(22, 18, 22)
    pdf.set_auto_page_break(auto=True, margin=23)
    pdf.alias_nb_pages()
    pdf.set_title(title or 'Lecture transcript')
    pdf.set_author('Lecture Captioning')
    pdf.add_page()
    pdf.set_text_color(32, 45, 53)
    pdf.set_font('Helvetica', 'B', 24)
    pdf.multi_cell(0, 10, _printable(title or 'Lecture transcript'), align='L', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 113, 120)
    parts = ['Lecture transcript']
    if created_at:
        parts.append(created_at.strftime('%B %d, %Y - %H:%M UTC'))
    if duration_ms:
        seconds = duration_ms // 1000
        parts.append(f'{seconds // 60:02d}:{seconds % 60:02d} recorded')
    pdf.multi_cell(0, 6, '  |  '.join(parts), new_x='LMARGIN', new_y='NEXT')
    pdf.ln(11)
    pdf.set_font('Helvetica', '', 11)
    pdf.set_text_color(45, 57, 65)
    text = format_transcript(transcript) or 'No speech was captured during this session.'
    for paragraph in text.split('\n\n'):
        pdf.multi_cell(0, 6.4, _printable(paragraph), align='L', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)
    return bytes(pdf.output())
