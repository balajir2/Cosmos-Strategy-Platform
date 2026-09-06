import contextlib

import psycopg2

from database import get_db_connection


def _source_dict(row: tuple) -> dict:
    return {
        "id": row[0], "filename": row[1], "source_format": row[2], "status": row[3],
        "uploaded_by": row[4], "uploaded_at": row[5].isoformat(),
    }


_SELECT_COLUMNS = "id, filename, source_format, status, uploaded_by, uploaded_at"


def create_source(filename: str, source_format: str, uploaded_by: int) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO framework_kb_sources (filename, source_format, uploaded_by)
                    VALUES (%s, %s, %s)
                    RETURNING {_SELECT_COLUMNS};
                    """,
                    (filename, source_format, uploaded_by),
                )
            except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation) as e:
                conn.rollback()
                raise ValueError(f"Invalid uploaded_by or source_format: {e}")
            row = cursor.fetchone()
        conn.commit()
    return _source_dict(row)


def get_source_by_id(source_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT {_SELECT_COLUMNS} FROM framework_kb_sources WHERE id = %s;", (source_id,))
            row = cursor.fetchone()
    if not row:
        return None
    return _source_dict(row)


def list_sources() -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT {_SELECT_COLUMNS} FROM framework_kb_sources ORDER BY uploaded_at DESC;")
            rows = cursor.fetchall()
    return [_source_dict(row) for row in rows]


def update_source_status(source_id: int, status: str):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE framework_kb_sources SET status = %s WHERE id = %s RETURNING {_SELECT_COLUMNS};",
                (status, source_id),
            )
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return _source_dict(row)


def delete_source(source_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM framework_kb_sources WHERE id = %s;", (source_id,))
            deleted = cursor.rowcount > 0
        conn.commit()
    return deleted
