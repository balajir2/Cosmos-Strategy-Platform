import os

from fastapi import Header, HTTPException


def require_admin_token(x_admin_token: str = Header(...)) -> None:
    """Stopgap admin gate: a single shared token, until Phase A's real per-user
    require_admin dependency exists (see roadmap.md Phase A). Do not extend this
    with per-user logic - replace it wholesale when Phase A ships."""
    expected = os.environ.get("ADMIN_API_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token.")
