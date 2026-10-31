from uuid import UUID
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import get_settings
from app.ports.captioning import TokenVerifier

bearer_scheme = HTTPBearer()
settings = get_settings()


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url)


def get_payload(token: str) -> dict:
    jwks_client = _jwks_client(settings.SUPABASE_JWKS_URL)
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    if not signing_key:
        raise ValueError("Public key not found in JWKS")

    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256"],
        audience=settings.SUPABASE_AUDIENCE or "authenticated",
    )
    return payload


def verify_jwt(token: str) -> UUID:
    """Verify JWT and return user ID. Raise HTTPException if invalid."""
    payload = get_payload(token)
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("User ID not found in token")
    return UUID(user_id)


class SupabaseTokenVerifier:
    def verify(self, token: str) -> UUID:
        return verify_jwt(token)


def get_token_verifier() -> TokenVerifier:
    return SupabaseTokenVerifier()


def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Validate JWT and return decoded payload.
    Raise 401 if token is invalid or expired.
    """
    token = cred.credentials
    try:
        return get_payload(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}"
        )


def get_user_id(
    cred: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> UUID:
    try:
        return verifier.verify(cred.credentials)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
