"""Validate actual PCM frames before accounting for recording limits."""
import io
import math
import wave


def bounded_wav(audio: bytes, remaining_ms: int) -> tuple[bytes, int]:
    try:
        with wave.open(io.BytesIO(audio), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise ValueError('Audio must be 16 kHz mono PCM16 WAV')
            declared = source.getnframes()
            frames = source.readframes(declared)
            if not declared or len(frames) != declared * 2:
                raise ValueError('Audio WAV payload is incomplete or empty')
    except (wave.Error, EOFError) as exc:
        raise ValueError('Audio must be a valid WAV file') from exc
    accepted = min(declared, max(0, remaining_ms) * 16)
    if accepted <= 0:
        return b'', 0
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(frames[:accepted * 2])
    return output.getvalue(), math.ceil(accepted / 16)
