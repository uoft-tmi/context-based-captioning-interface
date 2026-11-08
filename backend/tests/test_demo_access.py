from uuid import uuid4

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.core import auth
from app.core.config import Settings
from app.core.exceptions import DemoAccessDenied


@pytest.fixture
def demo_auth(monkeypatch):
    config = Settings(_env_file=None, DEMO_MODE=True,
        DEMO_ALLOWED_USER_ID="73abb4e6-38fc-4e6f-a706-aad1e8ad4bc9")
    monkeypatch.setattr(auth, 'settings', config)
    return config


@pytest.mark.parametrize('claims', [{}, {'email': 'changed@example.com'}])
def test_approved_signed_subject_is_accepted_regardless_of_email(demo_auth, monkeypatch, claims):
    user = demo_auth.DEMO_ALLOWED_USER_ID
    monkeypatch.setattr(auth, 'get_payload', lambda token: {'sub': str(user), **claims})
    assert auth.verify_jwt('signed-token') == user


@pytest.mark.parametrize('claims', [
    {'email': 'psjlee42@gmail.com'}, {},
    {'user_metadata': {'sub': '73abb4e6-38fc-4e6f-a706-aad1e8ad4bc9'}},
])
def test_other_subjects_are_denied_even_with_matching_email_or_metadata(demo_auth, monkeypatch, claims):
    monkeypatch.setattr(auth, 'get_payload', lambda token: {'sub': str(uuid4()), **claims})
    with pytest.raises(DemoAccessDenied):
        auth.verify_jwt('signed-token')


def test_rest_requests_from_unapproved_accounts_receive_403(demo_auth, monkeypatch):
    monkeypatch.setattr(auth, 'get_payload', lambda token: {'sub': str(uuid4()), 'email': 'someone@example.com'})
    app = FastAPI()
    @app.get('/private')
    def private(user=Depends(auth.get_user_id)):
        return {'user': str(user)}
    with TestClient(app) as client:
        response = client.get('/private', headers={'Authorization': 'Bearer signed-token'})
    assert response.status_code == 403
    assert 'approved account' in response.json()['detail']


@pytest.mark.parametrize('user_id', ['', 'invalid-uuid', None])
def test_invalid_demo_user_id_is_a_configuration_error(user_id):
    with pytest.raises(ValueError, match='DEMO_ALLOWED_USER_ID'):
        Settings(_env_file=None, DEMO_MODE=True, DEMO_ALLOWED_USER_ID=user_id)


@pytest.mark.parametrize('claims', [{}, {'sub': ''}, {'sub': 'invalid-uuid'}])
def test_missing_or_invalid_subject_is_rejected(demo_auth, monkeypatch, claims):
    monkeypatch.setattr(auth, 'get_payload', lambda token: claims)
    with pytest.raises(ValueError):
        auth.verify_jwt('signed-token')


def test_configured_user_id_controls_access(demo_auth, monkeypatch):
    demo_auth.DEMO_ALLOWED_USER_ID = uuid4()
    monkeypatch.setattr(auth, 'get_payload', lambda token: {'sub': str(demo_auth.DEMO_ALLOWED_USER_ID)})
    assert auth.verify_jwt('signed-token') == demo_auth.DEMO_ALLOWED_USER_ID
    monkeypatch.setattr(auth, 'get_payload', lambda token: {'sub': '73abb4e6-38fc-4e6f-a706-aad1e8ad4bc9'})
    with pytest.raises(DemoAccessDenied):
        auth.verify_jwt('signed-token')


def test_disabling_demo_allows_other_authenticated_users(demo_auth, monkeypatch):
    demo_auth.DEMO_MODE = False
    user = uuid4()
    monkeypatch.setattr(auth, 'get_payload', lambda token: {'sub': str(user)})
    assert auth.verify_jwt('signed-token') == user
