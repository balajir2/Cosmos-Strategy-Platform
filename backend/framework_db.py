import contextlib

import process_db
import settings as platform_settings
from database import get_db_connection
from llm_providers import get_provider_adapter
from llm_providers.base import parse_evaluation_json


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


def _move_sibling(cursor, table, id_col, parent_col, parent_value, row_id, current_seq, action):
    """Swap sequence_order with the adjacent sibling; return the new seq for row_id.

    `table`/`id_col`/`parent_col` are hardcoded internal identifiers (never user
    input), so the f-string SQL is safe.
    """
    delta = -1 if action == "move_up" else 1
    cursor.execute(
        f"SELECT {id_col}, sequence_order FROM {table} WHERE {parent_col} = %s ORDER BY sequence_order ASC;",
        (parent_value,),
    )
    ordered = cursor.fetchall()
    ids = [r[0] for r in ordered]
    idx = ids.index(row_id)
    target = idx + delta
    if target < 0 or target >= len(ids):
        return current_seq  # boundary no-op
    neighbor_id = ids[target]
    neighbor_seq = ordered[target][1]
    cursor.execute(f"UPDATE {table} SET sequence_order = %s WHERE {id_col} = %s;", (neighbor_seq, row_id))
    cursor.execute(f"UPDATE {table} SET sequence_order = %s WHERE {id_col} = %s;", (current_seq, neighbor_id))
    return neighbor_seq


def add_stage(process_id: int, name: str):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(sequence_order), 0) FROM stages WHERE process_id = %s;",
                (process_id,),
            )
            next_seq = cursor.fetchone()[0] + 1
            cursor.execute(
                "INSERT INTO stages (process_id, name, sequence_order) VALUES (%s, %s, %s) "
                "RETURNING id, name, sequence_order;",
                (process_id, name, next_seq),
            )
            row = cursor.fetchone()
        conn.commit()
    return {"id": row[0], "name": row[1], "sequence_order": row[2]}


def update_stage(stage_id: int, process_id: int, name=None, action=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, sequence_order FROM stages WHERE id = %s AND process_id = %s;",
                (stage_id, process_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            new_name = name if name is not None else row[1]
            new_seq = row[2]
            if action in ("move_up", "move_down"):
                new_seq = _move_sibling(cursor, "stages", "id", "process_id", process_id, stage_id, row[2], action)
            cursor.execute(
                "UPDATE stages SET name = %s, sequence_order = %s WHERE id = %s;",
                (new_name, new_seq, stage_id),
            )
        conn.commit()
    return {"id": stage_id, "name": new_name, "sequence_order": new_seq}


def delete_stage(stage_id: int, process_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM stages WHERE id = %s AND process_id = %s;",
                (stage_id, process_id),
            )
        conn.commit()
        return cursor.rowcount > 0


def add_question(stage_id: int, process_id: int, level: str, text: str, search_query, owner_role: str, reviewer_role, ai_generated: bool = False):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM stages WHERE id = %s AND process_id = %s;",
                (stage_id, process_id),
            )
            if cursor.fetchone() is None:
                return None

            cursor.execute(
                "SELECT COALESCE(MAX(sequence_order), 0) FROM questions WHERE stage_id = %s;",
                (stage_id,),
            )
            next_seq = cursor.fetchone()[0] + 1

            cursor.execute(
                "INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role, sequence_order, ai_generated) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;",
                (stage_id, level, text, search_query, owner_role, reviewer_role, next_seq, ai_generated),
            )
            new_q_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO guidance (question_id, type, content) VALUES (%s, 'Framework', %s) RETURNING id;",
                (new_q_id, ""),
            )
            guidance_id = cursor.fetchone()[0]
        conn.commit()
    return {
        "id": new_q_id, "stage_id": stage_id, "level": level, "text": text,
        "search_query": search_query, "owner_role": owner_role, "reviewer_role": reviewer_role,
        "sequence_order": next_seq, "ai_generated": ai_generated,
        "guidance": [{"id": guidance_id, "type": "Framework", "content": ""}],
    }


def update_question(question_id: int, process_id: int, level=None, text=None, search_query=None,
                    owner_role=None, reviewer_role=None, guidance=None, action=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT q.id, q.stage_id, q.level, q.text, q.search_query, q.owner_role, q.reviewer_role, q.sequence_order "
                "FROM questions q JOIN stages s ON s.id = q.stage_id "
                "WHERE q.id = %s AND s.process_id = %s;",
                (question_id, process_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            q_id, stage_id, cur_level, cur_text, cur_search, cur_owner, cur_reviewer, cur_seq = row

            new_level = level if level is not None else cur_level
            new_text = text if text is not None else cur_text
            new_search = search_query if search_query is not None else cur_search
            new_owner = owner_role if owner_role is not None else cur_owner
            new_reviewer = reviewer_role if reviewer_role is not None else cur_reviewer
            new_seq = cur_seq
            if action in ("move_up", "move_down"):
                new_seq = _move_sibling(cursor, "questions", "id", "stage_id", stage_id, q_id, cur_seq, action)

            cursor.execute(
                "UPDATE questions SET level = %s, text = %s, search_query = %s, owner_role = %s, reviewer_role = %s, sequence_order = %s "
                "WHERE id = %s;",
                (new_level, new_text, new_search, new_owner, new_reviewer, new_seq, q_id),
            )

            if guidance is not None:
                cursor.execute(
                    "UPDATE guidance SET content = %s WHERE question_id = %s AND type = 'Framework';",
                    (guidance, q_id),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        "INSERT INTO guidance (question_id, type, content) VALUES (%s, 'Framework', %s);",
                        (q_id, guidance),
                    )

            cursor.execute(
                "SELECT id, type, content FROM guidance WHERE question_id = %s ORDER BY id ASC;",
                (q_id,),
            )
            guidance_rows = cursor.fetchall()
        conn.commit()
    return {
        "id": q_id, "stage_id": stage_id, "level": new_level, "text": new_text,
        "search_query": new_search, "owner_role": new_owner, "reviewer_role": new_reviewer,
        "sequence_order": new_seq,
        "guidance": [{"id": g[0], "type": g[1], "content": g[2]} for g in guidance_rows],
    }


def delete_question(question_id: int, process_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM questions WHERE id = %s AND stage_id IN (SELECT id FROM stages WHERE process_id = %s);",
                (question_id, process_id),
            )
        conn.commit()
        return cursor.rowcount > 0


def generate_framework_from_knowledge(rag, project: dict) -> bool:
    """Best-effort: drafts a full stage/question set for `project` from the
    shared Framework Knowledge Base via the active LLM provider, replacing
    its current (template-cloned) stages/questions. Returns True if the
    draft was applied, False if generation failed for any reason - in which
    case the project's existing framework is left completely untouched, so
    a project is never left without a working framework. Never raises past
    this boundary."""
    try:
        current = process_db.get_process_detail(project["process_id"])
        if current is None:
            return False

        queries = [stage["name"] for stage in current["stages"]]
        if project.get("industry_context"):
            queries.append(project["industry_context"])
        if not queries:
            queries = [project["name"]]

        seen_ids = set()
        hits = []
        for query in queries:
            for hit in rag.search(query, top_k=10):
                if hit["id"] not in seen_ids:
                    seen_ids.add(hit["id"])
                    hits.append(hit)

        context_str = "\n\n".join(
            f"Source: {hit['source_file']}\nContext: {hit['text']}" for hit in hits
        )

        system_prompt = (
            "You are Cosmos AI, a premier management consulting assistant. Draft a full "
            "strategic framework for a self-serve engagement: a set of stages, each with "
            "several restlessness-arousing questions, grounded in the Cosmos methodology "
            "context provided below and tailored to the client's industry context.\n\n"
            "Return ONLY a valid JSON object matching this schema:\n"
            '{"stages": [{"name": "stage name", "questions": [{"level": "e.g. Level 3: Brand Positioning", '
            '"text": "the question text", "owner_role": "e.g. CMO", "reviewer_role": "e.g. CEO", '
            '"guidance": "short framework guidance for whoever answers this"}]}]}'
        )
        user_prompt = (
            f"Cosmos methodology context:\n{context_str}\n\n"
            f"Client industry context: {project.get('industry_context') or 'Not specified.'}\n\n"
            f"Return ONLY the JSON object described above."
        )

        provider_name = platform_settings.get_active_provider()
        provider = get_provider_adapter(provider_name)
        response_text = provider.complete(system_prompt, [{"role": "user", "content": user_prompt}])
        draft = parse_evaluation_json(response_text)

        stages = draft.get("stages")
        if not isinstance(stages, list) or not stages:
            raise ValueError(f"LLM response missing a non-empty 'stages' list: {draft!r}")
        for stage in stages:
            if not isinstance(stage.get("name"), str) or not stage["name"].strip():
                raise ValueError(f"Draft stage missing a name: {stage!r}")
            questions = stage.get("questions")
            if not isinstance(questions, list) or not questions:
                raise ValueError(f"Draft stage '{stage.get('name')}' has no questions: {stage!r}")
            for q in questions:
                for field in ("level", "text", "owner_role"):
                    if not isinstance(q.get(field), str) or not q[field].strip():
                        raise ValueError(f"Draft question missing required field '{field}': {q!r}")

        for stage in stages:
            new_stage = add_stage(project["process_id"], stage["name"])
            for q in stage["questions"]:
                new_question = add_question(
                    new_stage["id"], project["process_id"], q["level"], q["text"],
                    q.get("search_query"), q["owner_role"], q.get("reviewer_role"),
                    ai_generated=True,
                )
                if q.get("guidance"):
                    update_question(new_question["id"], project["process_id"], guidance=q["guidance"])

        for stage in current["stages"]:
            delete_stage(stage["id"], project["process_id"])

        return True
    except Exception as e:
        print(f"AI framework generation failed for project {project.get('id')}: {e}")
        return False
