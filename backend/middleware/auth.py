from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Verify Supabase JWT and extract user_id from the `sub` claim.

    Currently returns a stub user_id. Will be replaced with real
    JWKS-based JWT verification.
    """
    token = credentials.credentials
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    # TODO: Verify JWT against Supabase JWKS and extract sub claim.
    # For now, return a stub user_id so routes are callable during development.
    stub_user_id = "00000000-0000-0000-0000-000000000000"
    return stub_user_id
