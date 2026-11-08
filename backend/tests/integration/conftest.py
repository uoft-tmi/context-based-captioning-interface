import asyncio
import json
import os
import socket
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI, Header

from app.clients.caption_model_client import ModelClient
from app.clients.pool import get_pool
from app.clients.supabase_client import get_supabase_client
from app.core.auth import get_token_verifier, get_user_id
from app.routers import audio_router, capabilities_router, sessions_router, workspace_router
from app.providers.custom import CustomModelProvider


class MemoryStorage:
    def __init__(self):
        self.files = {}
        self.fail_upload = False
        self.storage = self

    def from_(self, bucket):
        storage = self
        class Bucket:
            async def upload(self, path, data, options):
                if storage.fail_upload:
                    raise RuntimeError('storage unavailable')
                storage.files[bucket, path] = data
            async def download(self, path):
                return storage.files[bucket, path]
            async def remove(self, paths):
                for path in paths:
                    storage.files.pop((bucket, path), None)
        return Bucket()

    async def get_bucket(self, bucket):
        return {}


@pytest_asyncio.fixture(params=["supabase", "postgres"])
async def database(request):
    dsn = os.environ.get('TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set TEST_DATABASE_URL to a local PostgreSQL admin DSN (creates a disposable database)')
    database_name = 'caption_test_' + uuid4().hex
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    test_dsn = urlsplit(dsn)._replace(path='/' + database_name).geturl()
    pool = None
    try:
        pool = await asyncpg.create_pool(test_dsn, min_size=1, max_size=2, statement_cache_size=0, command_timeout=5)
        async with pool.acquire() as conn:
            migrations = Path(__file__).parents[2] / 'app/migrations'
            if request.param == "postgres":
                # This must succeed before creating any Supabase auth objects.
                await conn.execute((migrations / 'postgres/001_create_tables.sql').read_text())
                await conn.execute((migrations / '006_dashboard_library.sql').read_text())
                await conn.execute((migrations / '007_provider_usage.sql').read_text())
            # Test users are seeded here even for the independent database layout.
            await conn.execute("CREATE SCHEMA auth; CREATE TABLE auth.users (id uuid PRIMARY KEY); CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS 'SELECT NULL::uuid';")
            if request.param == "supabase":
                for path in sorted(migrations.glob('*.sql')):
                    await conn.execute(path.read_text())
        yield pool
    finally:
        if pool:
            await pool.close()
        await admin.execute(f'DROP DATABASE "{database_name}" WITH (FORCE)')
        await admin.close()


@pytest_asyncio.fixture
async def streaming_app(database, monkeypatch):
    storage = MemoryStorage()
    model_chunks = {}
    model = SimpleNamespace(delay_ms=float(os.getenv('LATENCY_MODEL_DELAY_MS', '20')), fail_chunk=None, fail_finalize=False, fail_init=False, notes=[])

    async def model_request(request):
        if request.url.path == '/v1/process-notes':
            model.notes.append(request.content)
            return httpx.Response(200, json={'status': 'processed'})
        body = json.loads(request.content)
        session_id = body['session_id']
        if request.url.path == '/v1/init':
            if model.fail_init:
                return httpx.Response(401)
            model_chunks[session_id] = []
            return httpx.Response(200, json={'status': 'ready'})
        if request.url.path == '/v1/transcribe-chunk':
            await asyncio.sleep(model.delay_ms / 1000)
            if body['chunk_index'] == model.fail_chunk:
                return httpx.Response(503)
            text = f"chunk {body['chunk_index']}"
            model_chunks[session_id].append(text)
            return httpx.Response(200, json={'partial_text': text})
        if model.fail_finalize:
            return httpx.Response(503)
        return httpx.Response(200, json={'final_transcript': ' '.join(model_chunks[session_id])})

    client = httpx.AsyncClient(base_url='http://model.test', transport=httpx.MockTransport(model_request))
    app = FastAPI()
    app.state.transcription_provider = CustomModelProvider(ModelClient(client))
    app.include_router(sessions_router.router)
    app.include_router(workspace_router.router)
    app.include_router(audio_router.router)
    app.include_router(capabilities_router.router)
    app.dependency_overrides[get_pool] = lambda: database
    app.dependency_overrides[get_supabase_client] = lambda: storage
    def user_id(authorization: str = Header()):
        return UUID(authorization.removeprefix('Bearer '))
    app.dependency_overrides[get_user_id] = user_id
    class TestVerifier:
        def verify(self, token):
            return UUID(token)
    app.dependency_overrides[get_token_verifier] = lambda: TestVerifier()
    yield SimpleNamespace(app=app, db=database, storage=storage, model=model, model_chunks=model_chunks)
    await client.aclose()


@pytest_asyncio.fixture
async def server(streaming_app):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(streaming_app.app, log_level='warning', access_log=False, lifespan='off', ws='websockets-sansio'))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()
