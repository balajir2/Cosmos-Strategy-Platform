import contextlib

import psycopg2

from database import get_db_connection


def _artifact_dict(row: tuple) -> dict:
    return {
        "id": row[0], "project_id": row[1], "filename": row[2], "artifact_type": row[3],
        "source_format": row[4], "purpose": row[5], "status": row[6], "transcript_text": row[7],
        "uploaded_by": row[8], "uploaded_at": row[9].isoformat(),
    }


def create_artifact(
    project_id: int,
    filename: str,
    artifact_type: str,
    source_format: str,
    purpose: str,
    uploaded_by: int,
) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO project_artifacts (project_id, filename, artifact_type, source_format, purpose, uploaded_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at;
                    """,
                    (project_id, filename, artifact_type, source_format, purpose, uploaded_by),
                )
            except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation) as e:
                conn.rollback()
                raise ValueError(f"Invalid project_id, uploaded_by, artifact_type, source_format, or purpose: {e}")
            row = cursor.fetchone()
        conn.commit()
    return _artifact_dict(row)


def get_artifact_by_id(artifact_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at
                FROM project_artifacts WHERE id = %s;
                """,
                (artifact_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return _artifact_dict(row)


def list_artifacts_for_project(project_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at
                FROM project_artifacts WHERE project_id = %s ORDER BY uploaded_at DESC;
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
    return [_artifact_dict(row) for row in rows]


def update_artifact_status(artifact_id: int, status: str, transcript_text: str = None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE project_artifacts
                SET status = %s,
                    transcript_text = COALESCE(%s, transcript_text)
                WHERE id = %s
                RETURNING id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at;
                """,
                (status, transcript_text, artifact_id),
            )
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return _artifact_dict(row)


def delete_artifact(project_id: int, artifact_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM project_artifacts WHERE id = %s AND project_id = %s;",
                (artifact_id, project_id),
            )
            deleted = cursor.rowcount > 0
        conn.commit()
    return deleted
