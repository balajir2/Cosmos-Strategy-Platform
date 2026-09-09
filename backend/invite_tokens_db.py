import contextlib
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from database import get_db_connection

TOKEN_TTL_DAYS = 7


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_token(user_id: int) -> dict:
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO password_setup_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s);",
                (user_id, _hash_token(raw_token), expires_at),
            )
        conn.commit()
    return {"token": raw_token, "expires_at": expires_at}


def get_token_status(raw_token: str):
    """Returns None only if the token was never issued at all - the
    caller uses this to distinguish a 404 (unknown token) from a 400
    (expired or already-consumed) response."""
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, consumed_at, expires_at FROM password_setup_tokens WHERE token_hash = %s;",
                (_hash_token(raw_token),),
            )
            row = cursor.fetchone()
    if not row:
        return None
    user_id, consumed_at, expires_at = row
    return {
        "user_id": user_id,
        "consumed": consumed_at is not None,
        "expired": expires_at <= datetime.now(timezone.utc),
    }


def consume_token(raw_token: str) -> None:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE password_setup_tokens SET consumed_at = now() WHERE token_hash = %s;",
                (_hash_token(raw_token),),
            )
        conn.commit()
