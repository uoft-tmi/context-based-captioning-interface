from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.exceptions import ProviderRequestError
from app.ports.captioning import ProviderCapabilities
from app.providers.guarded import BudgetedTranscriptionProvider
from tests.helpers import wav_audio


def guarded(name='groq', **settings):
    provider = AsyncMock()
    provider.capabilities = ProviderCapabilities(name, supports_pdf_notes=name == 'custom')
    budget = AsyncMock()
    wrapper = BudgetedTranscriptionProvider(provider, budget, Settings(_env_file=None, **settings))
    return wrapper, provider, budget


async def test_denied_reservation_never_calls_the_provider():
    wrapper, provider, budget = guarded()
    budget.reserve.side_effect = ProviderRequestError('Daily allowance used up')
    with pytest.raises(ProviderRequestError, match='allowance'):
        await wrapper.transcribe(uuid4(), wav_audio(1), 0, 'baseline')
    provider.transcribe.assert_not_awaited()


async def test_reserves_actual_audio_before_network_and_does_not_refund_failures():
    wrapper, provider, budget = guarded()
    session_id = uuid4()
    provider.transcribe.side_effect = ProviderRequestError('Network unavailable')
    with pytest.raises(ProviderRequestError):
        await wrapper.transcribe(session_id, wav_audio(1), 0, 'baseline')
    budget.reserve.assert_awaited_once_with(session_id, 'transcribe', 1000)
    provider.transcribe.assert_awaited_once()


async def test_custom_setup_notes_and_finalization_also_need_reservations():
    wrapper, provider, budget = guarded('custom')
    session_id = uuid4()
    await wrapper.start_session(session_id, 'context')
    await wrapper.process_notes(session_id, b'pdf')
    await wrapper.finalize(session_id, ['captions'])
    assert [call.args[1] for call in budget.reserve.await_args_list] == ['start', 'notes', 'finalize']


async def test_groq_start_and_finalize_do_not_spend_request_budget():
    wrapper, provider, budget = guarded()
    await wrapper.start_session(uuid4(), 'baseline')
    await wrapper.finalize(uuid4(), ['captions'])
    budget.reserve.assert_not_awaited()


async def test_kill_switch_prevents_setup_and_does_not_call_provider():
    wrapper, provider, budget = guarded('custom', TRANSCRIPTION_ENABLED=False)
    with pytest.raises(ProviderRequestError, match='disabled'):
        await wrapper.start_session(uuid4(), 'baseline')
    provider.start_session.assert_not_awaited()


def test_advertised_pacing_includes_network_jitter_margin():
    wrapper, _, _ = guarded(PROVIDER_MIN_CHUNK_INTERVAL_MS=3500)
    assert wrapper.capabilities.min_request_interval_ms >= 3700
    assert wrapper.capabilities.recommended_chunk_ms >= 3700
