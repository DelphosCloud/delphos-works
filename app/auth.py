from fastapi import Header, HTTPException

from app.config import AUTH_KEY


async def require_auth(authorization: str | None = Header(default=None)):
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or authorization[7:] != AUTH_KEY
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
