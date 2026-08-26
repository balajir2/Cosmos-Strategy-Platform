import contextlib

from database import get_db_connection


def create_session(case_id: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_sessions (case_id, current_level_index, phase)
                VALUES (%s, 0, 'asking')
                RETURNING id, case_id, current_level_index, phase;
                """,
                (case_id,),
            )
            row = cursor.fetchone()
        conn.commit()
    return {"id": row[0], "case_id": row[1], "current_level_index": row[2], "phase": row[3]}


def get_session(session_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, case_id, current_level_index, phase FROM chat_sessions WHERE id = %s;",
                (session_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {"id": row[0], "case_id": row[1], "current_level_index": row[2], "phase": row[3]}


def update_session(session_id: int, current_level_index: int, phase: str) -> None:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE chat_sessions
                SET current_level_index = %s, phase = %s, updated_at = now()
                WHERE id = %s;
                """,
                (current_level_index, phase, session_id),
            )
        conn.commit()


def add_message(session_id: int, role: str, content: str, message_type: str, level_index) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, message_type, level_index)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, role, content, message_type, level_index, created_at;
                """,
                (session_id, role, content, message_type, level_index),
            )
            row = cursor.fetchone()
        conn.commit()
    return {
        "id": row[0], "role": row[1], "content": row[2],
        "message_type": row[3], "level_index": row[4], "created_at": row[5].isoformat(),
    }


def get_messages(session_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, role, content, message_type, level_index, created_at
                FROM chat_messages WHERE session_id = %s ORDER BY id ASC;
                """,
                (session_id,),
            )
            rows = cursor.fetchall()
    return [
        {
            "id": r[0], "role": r[1], "content": r[2],
            "message_type": r[3], "level_index": r[4], "created_at": r[5].isoformat(),
        }
        for r in rows
    ]


def get_level_messages(session_id: int, level_index: int) -> list:
    """Messages for just one level, in the exact {"role", "content"} shape
    LLMProvider.complete()'s messages argument expects."""
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT role, content FROM chat_messages
                WHERE session_id = %s AND level_index = %s ORDER BY id ASC;
                """,
                (session_id, level_index),
            )
            rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]
