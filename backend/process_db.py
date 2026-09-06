import contextlib

from database import get_db_connection


def get_process_detail(process_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, description, created_at FROM processes WHERE id = %s;",
                (process_id,),
            )
            process_row = cursor.fetchone()
            if not process_row:
                return None

            cursor.execute(
                """
                SELECT id, name, sequence_order FROM stages
                WHERE process_id = %s ORDER BY sequence_order ASC;
                """,
                (process_id,),
            )
            stage_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT q.id, q.stage_id, q.level, q.text, q.search_query, q.owner_role, q.reviewer_role, q.ai_generated
                FROM questions q
                JOIN stages s ON s.id = q.stage_id
                WHERE s.process_id = %s
                ORDER BY q.sequence_order ASC, q.id ASC;
                """,
                (process_id,),
            )
            question_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT g.id, g.question_id, g.type, g.content
                FROM guidance g
                JOIN questions q ON q.id = g.question_id
                JOIN stages s ON s.id = q.stage_id
                WHERE s.process_id = %s
                ORDER BY g.id ASC;
                """,
                (process_id,),
            )
            guidance_rows = cursor.fetchall()

    guidance_by_question = {}
    for g_id, q_id, g_type, content in guidance_rows:
        guidance_by_question.setdefault(q_id, []).append({"id": g_id, "type": g_type, "content": content})

    questions_by_stage = {}
    for q_id, stage_id, level, text, search_query, owner_role, reviewer_role, ai_generated in question_rows:
        questions_by_stage.setdefault(stage_id, []).append({
            "id": q_id, "level": level, "text": text, "search_query": search_query,
            "owner_role": owner_role, "reviewer_role": reviewer_role, "ai_generated": ai_generated,
            "guidance": guidance_by_question.get(q_id, []),
        })

    stages = [
        {"id": s_id, "name": name, "sequence_order": seq, "questions": questions_by_stage.get(s_id, [])}
        for s_id, name, seq in stage_rows
    ]

    return {
        "id": process_row[0], "name": process_row[1], "description": process_row[2],
        "created_at": process_row[3].isoformat(), "stages": stages,
    }


def get_question_by_id(question_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT q.id, q.stage_id, q.level, q.text, q.search_query, q.owner_role, q.reviewer_role, s.process_id
                FROM questions q
                JOIN stages s ON s.id = q.stage_id
                WHERE q.id = %s;
                """,
                (question_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "stage_id": row[1], "level": row[2], "text": row[3],
        "search_query": row[4], "owner_role": row[5], "reviewer_role": row[6], "process_id": row[7],
    }
