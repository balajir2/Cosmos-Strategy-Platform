import json

from cases_data import CASES_DATA
from chat_sessions import add_message, create_session, get_level_messages, get_messages, get_session, update_session
from llm_providers import get_provider_adapter
import calibration_db
import process_db
import projects_db
import responses_db
import settings as platform_settings

QUESTION_CAP_PER_LEVEL = 3


def _get_case_questions(case_id: str) -> list:
    case = CASES_DATA.get(case_id)
    if not case:
        raise ValueError(f"Unknown case_id '{case_id}'")
    return case["questions"]


def _get_project_questions(project_id: int) -> list:
    """Flattens the project's process (stages -> questions, already ordered by
    sequence_order then question id via process_db.get_process_detail) into the
    same {"id", "level", "question", "search_query"} shape _get_case_questions
    returns, so every downstream function in this module stays source-agnostic."""
    project = projects_db.get_project_by_id(project_id)
    if project is None:
        raise ValueError(f"Unknown project_id '{project_id}'")
    process = process_db.get_process_detail(project["process_id"])
    questions = []
    for stage in process["stages"]:
        questions.extend(stage["questions"])
    return [
        {"id": q["id"], "level": q["level"], "question": q["text"], "search_query": q["search_query"]}
        for q in questions
    ]


def _get_questions(case_id, project_id) -> list:
    if project_id is not None:
        return _get_project_questions(project_id)
    return _get_case_questions(case_id)


def _get_calibration_concepts(project_id) -> list:
    if project_id is None:
        return []
    project = projects_db.get_project_by_id(project_id)
    if project is None:
        return []
    return calibration_db.list_concepts(project["process_id"])


def _ask_calibration_prompt(session_id: int, concept: dict, concept_index: int) -> dict:
    """Posts a fixed, templated prompt for one calibration concept - not an LLM
    call, consistent with master questions being fixed content rather than
    AI-generated (see _ask_question)."""
    content = f"What does '{concept['concept_name']}' mean to you?"
    return add_message(session_id, "assistant", content, "calibration_prompt", concept_index)


def _generate_calibration_feedback(concept: dict, submitted_definition: str) -> str:
    try:
        system_prompt = (
            f"You are Cosmos AI. This organization defines '{concept['concept_name']}' as: "
            f"{concept['org_definition']}\n\n"
            "The user just gave their own definition of this term. Compare it constructively to "
            "this organization's definition - this is NOT a right/wrong grading exercise. If their "
            "understanding is close, say so warmly. If it diverges, gently note the gap without "
            "declaring them wrong. Keep it to 2-3 sentences."
        )
        provider = get_provider_adapter(platform_settings.get_active_provider())
        return provider.complete(system_prompt, [{"role": "user", "content": submitted_definition}])
    except Exception as e:
        print(f"Error generating calibration feedback for concept '{concept['concept_name']}': {e}")
        return f"Thanks for sharing your take on '{concept['concept_name']}'. We'll build on this as we go."


def _context_str(rag, search_query: str) -> str:
    hits = rag.search(search_query, top_k=3)
    return "\n\n".join(
        f"Source: {h['source_file']} (Slide {h['slide_number']})\nContext: {h['text']}" for h in hits
    )


def _ask_question(session_id: int, case_id, project_id, level_index: int) -> dict:
    """Posts the level's master question verbatim. This is fixed, human-authored
    Consultant IP and must never be reworded by the AI - see the 2026-08-26 review
    meeting notes in documentation/product/roadmap.md's Guided Learning Flow checklist."""
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]
    return add_message(session_id, "assistant", question["question"], "question", level_index)


def _question_count_for_level(session_id: int, level_index: int) -> int:
    all_messages = get_messages(session_id)
    return sum(1 for m in all_messages if m["level_index"] == level_index and m["message_type"] == "question")


def _has_sufficient_depth(rag, session_id: int, case_id, project_id, level_index: int) -> bool:
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        level_messages = get_level_messages(session_id, level_index)
        conversation_so_far = "\n".join(f"{m['role']}: {m['content']}" for m in level_messages)
        system_prompt = (
            f"You are Cosmos AI. Framework context:\n{context}\n\n"
            f"Conversation so far this level:\n{conversation_so_far}\n\n"
            "Based on the user's self-rating above, has their thinking now reached sufficient depth "
            "(roughly Level 2 or higher on the Cosmos framework) to move on to the next question? "
            "Answer with exactly one word on the first line: YES or NO."
        )
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(
            system_prompt, [{"role": "user", "content": "Has sufficient depth been reached?"}]
        )
        return content.strip().upper().startswith("YES")
    except Exception as e:
        print(f"Error checking depth for level {level_index}: {e}")
        return True


def _generate_followup_question(rag, session_id: int, case_id, project_id, level_index: int) -> dict:
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        level_messages = get_level_messages(session_id, level_index)
        conversation_so_far = "\n".join(f"{m['role']}: {m['content']}" for m in level_messages)
        system_prompt = (
            f"You are Cosmos AI. Framework context:\n{context}\n\n"
            f"Conversation so far this level:\n{conversation_so_far}\n\n"
            "The user's self-rating shows their answer isn't yet sufficiently deep. Ask ONE concrete "
            "follow-up question that pushes them toward a more insight-driven answer, building on what "
            "they've already said. Do not restate the original question."
        )
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(
            system_prompt, [{"role": "user", "content": "Generate the follow-up question."}]
        )
    except Exception as e:
        print(f"Error generating follow-up question for level {level_index}: {e}")
        content = "Can you go a level deeper - what's the underlying tension or trade-off here?"
    return add_message(session_id, "assistant", content, "question", level_index)


def _generate_benchmarks(rag, session_id: int, case_id, project_id, level_index: int) -> list:
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]

    if project_id is not None:
        level_messages = get_level_messages(session_id, level_index)
        question_asked = level_messages[-2]["content"] if len(level_messages) >= 2 else question["question"]
        user_answer = level_messages[-1]["content"] if level_messages else ""
        try:
            hits = rag.search_merged(project_id, question["search_query"], top_k=3)
            benchmarks = rag.generate_comparative_benchmarks(question_asked, user_answer, hits)
            content = json.dumps({
                "level_1": benchmarks.get("level_1", ""),
                "level_2": benchmarks.get("level_2", ""),
                "level_3": benchmarks.get("level_3", ""),
                "source_chunks": hits,
            })
        except Exception as e:
            print(f"Error generating project-scoped benchmarks for level {level_index}: {e}")
            fallback = rag.fallback_local_benchmarks()
            content = json.dumps({**fallback, "source_chunks": []})
    else:
        try:
            context = _context_str(rag, question["search_query"])
            level_messages = get_level_messages(session_id, level_index)
            question_asked = level_messages[-2]["content"] if len(level_messages) >= 2 else question["question"]
            user_answer = level_messages[-1]["content"] if level_messages else ""
            system_prompt = (
                f"You are Cosmos AI. Framework context:\n{context}\n\n"
                f"You asked the user: {question_asked}\n\n"
                "Given the user's answer below, write three example answers at increasing depth, labeled "
                "exactly:\n"
                "Level 1 (superficial, fact-based)\nLevel 2 (needs-based)\nLevel 3 (insight-driven)\n"
                "Do not evaluate or grade the user's answer directly - just provide the three benchmark "
                "answers for comparison."
            )
            provider = get_provider_adapter(platform_settings.get_active_provider())
            content = provider.complete(system_prompt, [{"role": "user", "content": user_answer}])
        except Exception as e:
            print(f"Error generating benchmarks for level {level_index}: {e}")
            content = (
                "Unable to generate benchmark comparisons right now. As a general guide: a Level 1 answer "
                "states obvious facts; a Level 2 answer names a customer need or trade-off; a Level 3 answer "
                "surfaces a deeper anxiety, hidden economic transaction, or cultural tension."
            )

    benchmark_msg = add_message(session_id, "assistant", content, "benchmark", level_index)
    prompt_msg = add_message(
        session_id, "assistant", "Where does your answer fall, and why?", "self_rating_prompt", level_index
    )
    return [benchmark_msg, prompt_msg]


def start_session(rag, case_id: str = None, project_id: int = None) -> dict:
    if (case_id is None) == (project_id is None):
        raise ValueError("Exactly one of case_id or project_id must be provided.")
    _get_questions(case_id, project_id)  # raises ValueError early if case_id/project_id is unknown

    session = create_session(case_id=case_id, project_id=project_id)

    concepts = _get_calibration_concepts(project_id)
    if concepts and not calibration_db.get_responses_for_project(project_id):
        prompt_msg = _ask_calibration_prompt(session["id"], concepts[0], 0)
        update_session(session["id"], 0, "calibration_awaiting_answer")
        return {"id": session["id"], "phase": "calibration_awaiting_answer", "current_level_index": 0, "messages": [prompt_msg]}

    question_msg = _ask_question(session["id"], case_id, project_id, 0)
    update_session(session["id"], 0, "awaiting_answer")
    return {"id": session["id"], "phase": "awaiting_answer", "current_level_index": 0, "messages": [question_msg]}


def advance_session(rag, session_id: int, user_content: str, self_evaluation_status: str = None) -> dict:
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Unknown session_id '{session_id}'")

    phase = session["phase"]
    level_index = session["current_level_index"]
    case_id = session.get("case_id")
    project_id = session.get("project_id")

    if phase == "calibration_awaiting_answer":
        add_message(session_id, "user", user_content, "chat", level_index)
        concepts = _get_calibration_concepts(project_id)
        if level_index >= len(concepts):
            # A Consultant deleted a concept (or all of them) while a ClientUser was
            # mid-calibration - level_index was written on a previous turn and can
            # now be out of range. Calibration is informational only and must never
            # block progression, so fall through to the real question flow exactly
            # like the natural end-of-concepts case below.
            question_msg = _ask_question(session_id, case_id, project_id, 0)
            update_session(session_id, 0, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": 0, "messages": [question_msg]}
        concept = concepts[level_index]
        feedback_text = _generate_calibration_feedback(concept, user_content)
        calibration_db.save_response(project_id, concept["id"], submitted_definition=user_content, feedback_text=feedback_text)
        feedback_msg = add_message(session_id, "assistant", feedback_text, "calibration_feedback", level_index)

        next_index = level_index + 1
        if next_index < len(concepts):
            prompt_msg = _ask_calibration_prompt(session_id, concepts[next_index], next_index)
            update_session(session_id, next_index, "calibration_awaiting_answer")
            return {"phase": "calibration_awaiting_answer", "current_level_index": next_index, "messages": [feedback_msg, prompt_msg]}

        question_msg = _ask_question(session_id, case_id, project_id, 0)
        update_session(session_id, 0, "awaiting_answer")
        return {"phase": "awaiting_answer", "current_level_index": 0, "messages": [feedback_msg, question_msg]}

    questions = _get_questions(case_id, project_id)

    if phase == "awaiting_answer":
        add_message(session_id, "user", user_content, "chat", level_index)
        new_messages = _generate_benchmarks(rag, session_id, case_id, project_id, level_index)
        update_session(session_id, level_index, "awaiting_self_rating")
        return {"phase": "awaiting_self_rating", "current_level_index": level_index, "messages": new_messages}

    if phase == "awaiting_self_rating":
        add_message(session_id, "user", user_content, "chat", level_index)

        if project_id is not None and self_evaluation_status is not None:
            question = questions[level_index]
            level_messages = get_level_messages(session_id, level_index)
            # The message immediately preceding the benchmark message - the same
            # relative position _generate_benchmarks reads as "user_answer" when it
            # runs, now 3 positions further back since the benchmark message, the
            # self-rating prompt, and this self-eval reply have since been appended.
            submitted_text = level_messages[-4]["content"] if len(level_messages) >= 4 else ""
            # An empty note must be passed through as None, not "" - responses_db's
            # upsert uses COALESCE(EXCLUDED.self_evaluation_notes, responses.self_evaluation_notes)
            # to preserve a previously-saved note when the new value is SQL NULL, but
            # an empty string is not NULL and would silently overwrite it. This matters
            # because the adaptive-difficulty follow-up loop can revisit the same
            # question's self-rating more than once (see the "3 positions further
            # back" comment above), so a thoughtful note from an earlier round must
            # survive a later round where the user leaves the now-optional note blank.
            responses_db.save_response(
                project_id, question["id"], submitted_text=submitted_text,
                self_evaluation_notes=(user_content or None), self_evaluation_status=self_evaluation_status,
            )

        question_count = _question_count_for_level(session_id, level_index)
        sufficient = question_count >= QUESTION_CAP_PER_LEVEL or _has_sufficient_depth(
            rag, session_id, case_id, project_id, level_index
        )

        if not sufficient:
            followup_msg = _generate_followup_question(rag, session_id, case_id, project_id, level_index)
            update_session(session_id, level_index, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": level_index, "messages": [followup_msg]}

        if level_index < len(questions) - 1:
            next_level = level_index + 1
            question_msg = _ask_question(session_id, case_id, project_id, next_level)
            update_session(session_id, next_level, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": next_level, "messages": [question_msg]}
        update_session(session_id, level_index, "complete")
        return {"phase": "complete", "current_level_index": level_index, "messages": []}

    raise ValueError(f"Session {session_id} is not awaiting input (phase={phase})")
