"""Verifies the Supabase-issued JWT the frontend sends on every request.
The backend never issues its own tokens or handles login - Supabase auth
happens entirely client-side (magic link) in the Next.js app.

Supabase projects created since the asymmetric-keys rollout sign session
JWTs with ES256 by default (visible in the dashboard as "JWT Signing
Keys" - a Key ID, not a secret string) - those are verified against the
project's public JWKS endpoint, no secret required. Older projects (or
not-yet-expired tokens issued before a project migrated) may still be
HS256-signed with a static secret (the dashboard's "Legacy JWT Secret"
tab) - supabase_jwt_secret is that fallback. Branching on the token's own
`alg` header (not a config flag) means both cases work without the
caller needing to know which one applies.
"""
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException

from app.config import settings


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    # Cached: PyJWKClient itself caches fetched keys internally (keyed by
    # kid), so this just avoids rebuilding the client object per-request.
    jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(jwks_url, cache_keys=True)


def get_current_user_id(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()

    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "")

        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise HTTPException(status_code=401, detail="Received an HS256 token but SUPABASE_JWT_SECRET isn't configured")
            payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience=settings.supabase_jwt_audience)
        else:
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
            payload = jwt.decode(token, signing_key, algorithms=[alg], audience=settings.supabase_jwt_audience)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    return user_id
