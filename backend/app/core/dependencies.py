from fastapi import Request

from app.clients.caption_model_client import ModelClient


def get_model_client(request: Request) -> ModelClient:
    return request.app.state.model_client
