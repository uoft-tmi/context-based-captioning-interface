from uuid import uuid4

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.core import auth
from app.core.config import Settings
from app.core.exceptions import DemoAccessDenied


@pytest.fixture
def demo_auth(monkeypatch):
    config = Settings(_env_file=None, DEMO_MODE=True)
    monkeypatch.setattr(auth, 'settings', config)
    return config


def test_only_the_approved_signed_email_is_accepted(demo_auth, monkeypatch):
    user = uuid4()
    monkeypatch.setattr(auth, 'get_payload', lambda token: {'sub': str(user), 'email': 'PSJLEE42@gmail.com'})
    assert auth.verify_jwt('signed-token') == user


@pytest.mark.parametrize('claims', [
    {'email': 'someone@example.com'}, {},
    {'email': 'someone@example.com', 'user_metadata': {'email': 'psjlee42@gmail.com'}},
])
def test_other_missing_and_editable_metadata_emails_are_denied(demo_auth, monkeypatch, claims):
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


def test_empty_demo_allowlist_is_a_configuration_error():
    with pytest.raises(ValueError, match='DEMO_ALLOWED_EMAIL'):
        Settings(_env_file=None, DEMO_MODE=True, DEMO_ALLOWED_EMAIL='')
