import contextlib

import psycopg2

from database import get_db_connection


def _project_dict(row: tuple) -> dict:
    return {
        "id": row[0], "name": row[1], "customer_name": row[2], "description": row[3],
        "industry_context": row[4], "delivery_mode": row[5], "status": row[6],
        "process_id": row[7], "created_by": row[8], "created_at": row[9].isoformat(),
    }


_SELECT_COLUMNS = (
    "id, name, customer_name, description, industry_context, delivery_mode, "
    "status, process_id, created_by, created_at"
)
_SELECT_COLUMNS_QUALIFIED = (
    "p.id, p.name, p.customer_name, p.description, p.industry_context, p.delivery_mode, "
    "p.status, p.process_id, p.created_by, p.created_at"
)


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
                    f"""
                    INSERT INTO projects (name, customer_name, description, industry_context, process_id, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING {_SELECT_COLUMNS};
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
                f"SELECT {_SELECT_COLUMNS} FROM projects WHERE id = %s;",
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
                f"""
                SELECT {_SELECT_COLUMNS_QUALIFIED}, pm.role
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.id
                WHERE pm.user_id = %s
                ORDER BY p.created_at DESC;
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
    return [{**_project_dict(row), "role": row[10]} for row in rows]


def list_all_projects() -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT {_SELECT_COLUMNS} FROM projects ORDER BY created_at DESC;")
            rows = cursor.fetchall()
    return [_project_dict(row) for row in rows]


def set_project_status(project_id: int, status: str):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE projects SET status = %s
                WHERE id = %s
                RETURNING {_SELECT_COLUMNS};
                """,
                (status, project_id),
            )
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return _project_dict(row)


def delete_project(project_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM projects WHERE id = %s;", (project_id,))
        conn.commit()
        return cursor.rowcount > 0


def update_project(project_id: int, name=None, customer_name=None, description=None, industry_context=None, delivery_mode=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    UPDATE projects
                    SET name = COALESCE(%s, name),
                        customer_name = COALESCE(%s, customer_name),
                        description = COALESCE(%s, description),
                        industry_context = COALESCE(%s, industry_context),
                        delivery_mode = COALESCE(%s, delivery_mode)
                    WHERE id = %s
                    RETURNING {_SELECT_COLUMNS};
                    """,
                    (name, customer_name, description, industry_context, delivery_mode, project_id),
                )
            except psycopg2.errors.CheckViolation as e:
                conn.rollback()
                raise ValueError(f"Invalid delivery_mode: {e}")
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return _project_dict(row)


def activate_project(project_id: int) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE projects SET status = 'Active'
                WHERE id = %s AND status = 'Draft'
                RETURNING {_SELECT_COLUMNS};
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


def add_project_member(project_id: int, user_id: int, role: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES (%s, %s, %s)
                    RETURNING id, project_id, user_id, role, org_title, assigned_at;
                    """,
                    (project_id, user_id, role),
                )
            except psycopg2.errors.UniqueViolation as e:
                conn.rollback()
                raise ValueError(f"User {user_id} is already a member of project {project_id}: {e}")
            except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation) as e:
                conn.rollback()
                raise ValueError(f"Invalid project_id, user_id, or role: {e}")
            row = cursor.fetchone()
        conn.commit()
    return {
        "id": row[0], "project_id": row[1], "user_id": row[2], "role": row[3],
        "org_title": row[4], "assigned_at": row[5].isoformat(),
    }


def list_project_members(project_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT pm.id, pm.project_id, pm.user_id, pm.role, pm.org_title, pm.assigned_at,
                       u.email, u.full_name
                FROM project_members pm
                JOIN users u ON u.id = pm.user_id
                WHERE pm.project_id = %s
                ORDER BY pm.assigned_at ASC;
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
    return [
        {
            "id": row[0], "project_id": row[1], "user_id": row[2], "role": row[3],
            "org_title": row[4], "assigned_at": row[5].isoformat(),
            "email": row[6], "full_name": row[7],
        }
        for row in rows
    ]


def update_project_member_role(project_id: int, user_id: int, role: str):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    UPDATE project_members SET role = %s
                    WHERE project_id = %s AND user_id = %s
                    RETURNING id, project_id, user_id, role, org_title, assigned_at;
                    """,
                    (role, project_id, user_id),
                )
            except psycopg2.errors.CheckViolation as e:
                conn.rollback()
                raise ValueError(f"Invalid role: {e}")
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return {
        "id": row[0], "project_id": row[1], "user_id": row[2], "role": row[3],
        "org_title": row[4], "assigned_at": row[5].isoformat(),
    }


def remove_project_member(project_id: int, user_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM project_members WHERE project_id = %s AND user_id = %s;",
                (project_id, user_id),
            )
        conn.commit()
        return cursor.rowcount > 0
