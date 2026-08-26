from cases_data import CASES_DATA
from chat_sessions import add_message, create_session, get_level_messages, get_messages, get_session, update_session
from llm_providers import get_provider_adapter
import settings as platform_settings

QUESTION_CAP_PER_LEVEL = 3


def _get_case_questions(case_id: str) -> list:
    case = CASES_DATA.get(case_id)
    if not case:
        raise ValueError(f"Unknown case_id '{case_id}'")
    return case["questions"]


def _context_str(rag, search_query: str) -> str:
    hits = rag.search(search_query, top_k=3)
    return "\n\n".join(
        f"Source: {h['source_file']} (Slide {h['slide_number']})\nContext: {h['text']}" for h in hits
    )


def _ask_question(session_id: int, case_id: str, level_index: int) -> dict:
    """Posts the level's master question verbatim. This is fixed, human-authored
    Consultant IP and must never be reworded by the AI - see the 2026-08-26 review
    meeting notes in documentation/product/roadmap.md's Guided Learning Flow checklist."""
    questions = _get_case_questions(case_id)
    question = questions[level_index]
    return add_message(session_id, "assistant", question["question"], "question", level_index)


def _question_count_for_level(session_id: int, level_index: int) -> int:
    all_messages = get_messages(session_id)
    return sum(1 for m in all_messages if m["level_index"] == level_index and m["message_type"] == "question")


def _has_sufficient_depth(rag, session_id: int, case_id: str, level_index: int) -> bool:
    questions = _get_case_questions(case_id)
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


def _generate_followup_question(rag, session_id: int, case_id: str, level_index: int) -> dict:
    questions = _get_case_questions(case_id)
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


def _generate_benchmarks(rag, session_id: int, case_id: str, level_index: int) -> list:
    questions = _get_case_questions(case_id)
    question = questions[level_index]
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


def start_session(rag, case_id: str) -> dict:
    _get_case_questions(case_id)  # raises ValueError early if case_id is unknown
    session = create_session(case_id)
    question_msg = _ask_question(session["id"], case_id, 0)
    update_session(session["id"], 0, "awaiting_answer")
    return {"id": session["id"], "phase": "awaiting_answer", "current_level_index": 0, "messages": [question_msg]}


def advance_session(rag, session_id: int, user_content: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Unknown session_id '{session_id}'")

    phase = session["phase"]
    level_index = session["current_level_index"]
    case_id = session["case_id"]
    questions = _get_case_questions(case_id)

    if phase == "awaiting_answer":
        add_message(session_id, "user", user_content, "chat", level_index)
        new_messages = _generate_benchmarks(rag, session_id, case_id, level_index)
        update_session(session_id, level_index, "awaiting_self_rating")
        return {"phase": "awaiting_self_rating", "current_level_index": level_index, "messages": new_messages}

    if phase == "awaiting_self_rating":
        add_message(session_id, "user", user_content, "chat", level_index)

        question_count = _question_count_for_level(session_id, level_index)
        sufficient = question_count >= QUESTION_CAP_PER_LEVEL or _has_sufficient_depth(
            rag, session_id, case_id, level_index
        )

        if not sufficient:
            followup_msg = _generate_followup_question(rag, session_id, case_id, level_index)
            update_session(session_id, level_index, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": level_index, "messages": [followup_msg]}

        if level_index < len(questions) - 1:
            next_level = level_index + 1
            question_msg = _ask_question(session_id, case_id, next_level)
            update_session(session_id, next_level, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": next_level, "messages": [question_msg]}
        update_session(session_id, level_index, "complete")
        return {"phase": "complete", "current_level_index": level_index, "messages": []}

    raise ValueError(f"Session {session_id} is not awaiting input (phase={phase})")
