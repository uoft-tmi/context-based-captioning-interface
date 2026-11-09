import io
import wave


def wav_audio(seconds: float = 0.01) -> bytes:
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * round(seconds * 16000))
    return output.getvalue()


def pdf_notes(text: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    if text:
        pdf.multi_cell(0, 6, text)
    return bytes(pdf.output())


def multipart_fields(request, body: bytes) -> dict[str, str]:
    from email import policy
    from email.parser import BytesParser

    message = BytesParser(policy=policy.default).parsebytes(
        f'Content-Type: {request.headers["content-type"]}\r\nMIME-Version: 1.0\r\n\r\n'.encode() + body)
    return {part.get_param('name', header='content-disposition'): part.get_payload(decode=True).decode()
            for part in message.iter_parts() if part.get_filename() is None}
