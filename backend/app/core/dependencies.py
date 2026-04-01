from starlette.requests import HTTPConnection

from app.clients.caption_model_client import ModelClient


def get_model_client(connection: HTTPConnection) -> ModelClient:
    return connection.app.state.model_client
