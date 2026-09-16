import contextlib

import psycopg2

from database import get_db_connection


def _response_dict(row: tuple) -> dict:
    return {
        "id": row[0], "question_id": row[1], "project_id": row[2], "submitted_text": row[3],
        "self_evaluation_notes": row[4], "self_evaluation_status": row[5], "status": row[6],
        "updated_at": row[7].isoformat(),
        "benchmark_level_1": row[8], "benchmark_level_2": row[9], "benchmark_level_3": row[10],
    }


def save_response(
    project_id: int,
    question_id: int,
    submitted_text: str = None,
    self_evaluation_notes: str = None,
    self_evaluation_status: str = None,
    benchmark_level_1: str = None,
    benchmark_level_2: str = None,
    benchmark_level_3: str = None,
) -> dict:
    status = "Draft"
    if self_evaluation_status is not None:
        status = "Self-Evaluated"
    elif submitted_text is not None:
        status = "Submitted"

    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO responses (question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status, benchmark_level_1, benchmark_level_2, benchmark_level_3)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (question_id, project_id) DO UPDATE SET
                        submitted_text = COALESCE(EXCLUDED.submitted_text, responses.submitted_text),
                        self_evaluation_notes = COALESCE(EXCLUDED.self_evaluation_notes, responses.self_evaluation_notes),
                        self_evaluation_status = COALESCE(EXCLUDED.self_evaluation_status, responses.self_evaluation_status),
                        benchmark_level_1 = COALESCE(EXCLUDED.benchmark_level_1, responses.benchmark_level_1),
                        benchmark_level_2 = COALESCE(EXCLUDED.benchmark_level_2, responses.benchmark_level_2),
                        benchmark_level_3 = COALESCE(EXCLUDED.benchmark_level_3, responses.benchmark_level_3),
                        status = CASE
                            WHEN COALESCE(EXCLUDED.self_evaluation_status, responses.self_evaluation_status) IS NOT NULL THEN 'Self-Evaluated'
                            WHEN COALESCE(EXCLUDED.submitted_text, responses.submitted_text) IS NOT NULL THEN 'Submitted'
                            ELSE 'Draft'
                        END,
                        updated_at = now()
                    RETURNING id, question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status, updated_at, benchmark_level_1, benchmark_level_2, benchmark_level_3;
                    """,
                    (question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status, benchmark_level_1, benchmark_level_2, benchmark_level_3),
                )
            except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation) as e:
                conn.rollback()
                raise ValueError(f"Invalid project_id, question_id, or self_evaluation_status: {e}")
            row = cursor.fetchone()
        conn.commit()
    return _response_dict(row)


def get_responses_for_project(project_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.question_id, r.project_id, r.submitted_text, r.self_evaluation_notes,
                       r.self_evaluation_status, r.status, r.updated_at,
                       r.benchmark_level_1, r.benchmark_level_2, r.benchmark_level_3,
                       q.text, q.level, s.name, s.sequence_order
                FROM responses r
                JOIN questions q ON q.id = r.question_id
                JOIN stages s ON s.id = q.stage_id
                WHERE r.project_id = %s
                ORDER BY s.sequence_order ASC, q.id ASC;
                """,
                (project_id,),
            )
            rows = cursor.fetchall()

    results = []
    for row in rows:
        entry = _response_dict(row[:11])
        entry.update({
            "question_text": row[11], "level": row[12], "stage_name": row[13], "sequence_order": row[14],
        })
        results.append(entry)
    return results
