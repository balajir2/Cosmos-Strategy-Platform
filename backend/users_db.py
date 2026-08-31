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


def list_users() -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, full_name, is_active, is_admin, created_at
                FROM users ORDER BY created_at ASC;
                """
            )
            rows = cursor.fetchall()
    return [
        {
            "id": row[0], "email": row[1], "full_name": row[2],
            "is_active": row[3], "is_admin": row[4], "created_at": row[5].isoformat(),
        }
        for row in rows
    ]


def update_user(user_id: int, full_name=None, is_admin=None, is_active=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE users
                SET full_name = COALESCE(%s, full_name),
                    is_admin = COALESCE(%s, is_admin),
                    is_active = COALESCE(%s, is_active)
                WHERE id = %s
                RETURNING id, email, full_name, is_active, is_admin, created_at;
                """,
                (full_name, is_admin, is_active, user_id),
            )
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return {
        "id": row[0], "email": row[1], "full_name": row[2],
        "is_active": row[3], "is_admin": row[4], "created_at": row[5].isoformat(),
    }


def set_password(user_id: int, password_hash: str) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s;",
                (password_hash, user_id),
            )
        conn.commit()
        return cursor.rowcount > 0
