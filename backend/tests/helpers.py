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
