import io
import wave
import pytest
from app.utils.audio_helper import bounded_wav
from tests.helpers import wav_audio


def test_only_remaining_pcm_duration_is_accepted():
    data, ms = bounded_wav(wav_audio(3), 1250)
    with wave.open(io.BytesIO(data)) as audio:
        assert audio.getnframes() == 20000
    assert ms == 1250
    assert bounded_wav(wav_audio(), 0) == (b'', 0)


@pytest.mark.parametrize('audio', [b'not WAV', wav_audio()[:-2]])
def test_malformed_or_truncated_audio_cannot_bypass_accounting(audio):
    with pytest.raises(ValueError):
        bounded_wav(audio, 30000)
