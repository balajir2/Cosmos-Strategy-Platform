import contextlib

import psycopg2

from database import get_db_connection


def create_user(email: str, password_hash: str, full_name: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, full_name, is_active, is_admin, created_at;
                    """,
                    (email, password_hash, full_name),
                )
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                raise ValueError(f"Email '{email}' is already registered.")
            row = cursor.fetchone()
        conn.commit()
    return {
        "id": row[0], "email": row[1], "full_name": row[2],
        "is_active": row[3], "is_admin": row[4], "created_at": row[5].isoformat(),
    }


def get_user_by_email(email: str):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, password_hash, full_name, is_active, is_admin, created_at
                FROM users WHERE email = %s;
                """,
                (email,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "email": row[1], "password_hash": row[2], "full_name": row[3],
        "is_active": row[4], "is_admin": row[5], "created_at": row[6].isoformat(),
    }


def get_user_by_id(user_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, full_name, is_active, is_admin, created_at
                FROM users WHERE id = %s;
                """,
                (user_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "email": row[1], "full_name": row[2],
        "is_active": row[3], "is_admin": row[4], "created_at": row[5].isoformat(),
    }
