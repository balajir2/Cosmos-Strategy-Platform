import contextlib

import psycopg2

from database import get_db_connection


def _project_dict(row: tuple) -> dict:
    return {
        "id": row[0], "name": row[1], "customer_name": row[2], "description": row[3],
        "industry_context": row[4], "status": row[5], "process_id": row[6],
        "created_by": row[7], "created_at": row[8].isoformat(),
    }


def create_project(
    name: str,
    customer_name: str,
    description,
    industry_context,
    process_id: int,
    created_by: int,
    consultant_user_id: int,
) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO projects (name, customer_name, description, industry_context, process_id, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, name, customer_name, description, industry_context, status, process_id, created_by, created_at;
                    """,
                    (name, customer_name, description, industry_context, process_id, created_by),
                )
                project_row = cursor.fetchone()
                cursor.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES (%s, %s, 'Consultant');
                    """,
                    (project_row[0], consultant_user_id),
                )
            except psycopg2.errors.ForeignKeyViolation as e:
                conn.rollback()
                raise ValueError(f"Invalid process_id or consultant_user_id: {e}")
        conn.commit()
    return _project_dict(project_row)


def get_project_by_id(project_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, customer_name, description, industry_context, status, process_id, created_by, created_at
                FROM projects WHERE id = %s;
                """,
                (project_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return _project_dict(row)


def list_projects_for_user(user_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.name, p.customer_name, p.description, p.industry_context,
                       p.status, p.process_id, p.created_by, p.created_at
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.id
                WHERE pm.user_id = %s
                ORDER BY p.created_at DESC;
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
    return [_project_dict(row) for row in rows]


def update_project(project_id: int, name=None, customer_name=None, description=None, industry_context=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE projects
                SET name = COALESCE(%s, name),
                    customer_name = COALESCE(%s, customer_name),
                    description = COALESCE(%s, description),
                    industry_context = COALESCE(%s, industry_context)
                WHERE id = %s
                RETURNING id, name, customer_name, description, industry_context, status, process_id, created_by, created_at;
                """,
                (name, customer_name, description, industry_context, project_id),
            )
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return _project_dict(row)


def activate_project(project_id: int) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE projects SET status = 'Active'
                WHERE id = %s AND status = 'Draft'
                RETURNING id, name, customer_name, description, industry_context, status, process_id, created_by, created_at;
                """,
                (project_id,),
            )
            row = cursor.fetchone()
            if row is None:
                conn.rollback()
                raise ValueError(f"Project {project_id} cannot be activated (not found or not in Draft status).")
        conn.commit()
    return _project_dict(row)


def get_project_member(project_id: int, user_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, project_id, user_id, role, org_title, assigned_at
                FROM project_members WHERE project_id = %s AND user_id = %s;
                """,
                (project_id, user_id),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "project_id": row[1], "user_id": row[2], "role": row[3],
        "org_title": row[4], "assigned_at": row[5].isoformat(),
    }
