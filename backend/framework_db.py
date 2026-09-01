import contextlib

from database import get_db_connection


def get_template_process():
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, description, created_at FROM processes "
                "WHERE is_template = true ORDER BY id ASC LIMIT 1;",
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "name": row[1], "description": row[2],
        "created_at": row[3].isoformat(),
    }


def clone_process(source_process_id: int, new_name: str, new_description) -> int:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO processes (name, description) VALUES (%s, %s) RETURNING id;",
                (new_name, new_description),
            )
            new_process_id = cursor.fetchone()[0]

            cursor.execute(
                "SELECT id, name, sequence_order FROM stages "
                "WHERE process_id = %s ORDER BY sequence_order ASC;",
                (source_process_id,),
            )
            source_stages = cursor.fetchall()

            stage_id_map = {}
            for old_stage_id, name, seq in source_stages:
                cursor.execute(
                    "INSERT INTO stages (process_id, name, sequence_order) VALUES (%s, %s, %s) RETURNING id;",
                    (new_process_id, name, seq),
                )
                stage_id_map[old_stage_id] = cursor.fetchone()[0]

            for old_stage_id, _, _ in source_stages:
                cursor.execute(
                    "SELECT id, level, text, search_query, owner_role, reviewer_role, sequence_order "
                    "FROM questions WHERE stage_id = %s ORDER BY sequence_order ASC;",
                    (old_stage_id,),
                )
                for q in cursor.fetchall():
                    old_q_id = q[0]
                    cursor.execute(
                        "INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role, sequence_order) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;",
                        (stage_id_map[old_stage_id], q[1], q[2], q[3], q[4], q[5], q[6]),
                    )
                    new_q_id = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT type, content FROM guidance WHERE question_id = %s;",
                        (old_q_id,),
                    )
                    for g_type, g_content in cursor.fetchall():
                        cursor.execute(
                            "INSERT INTO guidance (question_id, type, content) VALUES (%s, %s, %s);",
                            (new_q_id, g_type, g_content),
                        )
        conn.commit()
    return new_process_id


def migrate_existing_projects() -> int:
    template = get_template_process()
    if template is None:
        return 0

    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name FROM projects WHERE process_id = %s ORDER BY id ASC;",
                (template["id"],),
            )
            rows = cursor.fetchall()

    count = 0
    for project_id, project_name in rows:
        new_process_id = clone_process(
            template["id"], f"{project_name} Framework", template["description"],
        )
        with contextlib.closing(get_db_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE projects SET process_id = %s WHERE id = %s;",
                    (new_process_id, project_id),
                )
            conn.commit()
        count += 1
    return count
