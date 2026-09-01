import contextlib

from database import get_db_connection
from framework_db import _move_sibling


def list_concepts(process_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, concept_name, org_definition, sequence_order FROM calibration_concepts "
                "WHERE process_id = %s ORDER BY sequence_order ASC;",
                (process_id,),
            )
            rows = cursor.fetchall()
    return [
        {"id": r[0], "concept_name": r[1], "org_definition": r[2], "sequence_order": r[3]}
        for r in rows
    ]


def add_concept(process_id: int, concept_name: str, org_definition: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(sequence_order), 0) FROM calibration_concepts WHERE process_id = %s;",
                (process_id,),
            )
            next_seq = cursor.fetchone()[0] + 1
            cursor.execute(
                "INSERT INTO calibration_concepts (process_id, concept_name, org_definition, sequence_order) "
                "VALUES (%s, %s, %s, %s) RETURNING id, concept_name, org_definition, sequence_order;",
                (process_id, concept_name, org_definition, next_seq),
            )
            row = cursor.fetchone()
        conn.commit()
    return {"id": row[0], "concept_name": row[1], "org_definition": row[2], "sequence_order": row[3]}


def update_concept(concept_id: int, process_id: int, concept_name=None, org_definition=None, action=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, concept_name, org_definition, sequence_order FROM calibration_concepts "
                "WHERE id = %s AND process_id = %s;",
                (concept_id, process_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            new_name = concept_name if concept_name is not None else row[1]
            new_def = org_definition if org_definition is not None else row[2]
            new_seq = row[3]
            if action in ("move_up", "move_down"):
                new_seq = _move_sibling(cursor, "calibration_concepts", "id", "process_id", process_id, concept_id, row[3], action)
            cursor.execute(
                "UPDATE calibration_concepts SET concept_name = %s, org_definition = %s, sequence_order = %s WHERE id = %s;",
                (new_name, new_def, new_seq, concept_id),
            )
        conn.commit()
    return {"id": concept_id, "concept_name": new_name, "org_definition": new_def, "sequence_order": new_seq}


def delete_concept(concept_id: int, process_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM calibration_concepts WHERE id = %s AND process_id = %s;",
                (concept_id, process_id),
            )
        conn.commit()
        return cursor.rowcount > 0
