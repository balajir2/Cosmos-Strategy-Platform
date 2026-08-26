from cases_data import CASES_DATA
from chat_sessions import add_message, create_session, get_level_messages, get_session, update_session
from llm_providers import get_provider_adapter
import settings as platform_settings


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


def _ask_question(rag, session_id: int, case_id: str, level_index: int) -> dict:
    questions = _get_case_questions(case_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        system_prompt = (
            "You are Cosmos AI, a strategy facilitator guiding a live interview through the Cosmos "
            "methodology. Ask ONE question conversationally and warmly, in your own words, based on the "
            "framework question given below. Do not just restate it verbatim - make it feel like a "
            "natural facilitator prompt. Keep it to 2-4 sentences."
        )
        user_prompt = f"Framework context:\n{context}\n\nFramework question to pose: {question['question']}"
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(system_prompt, [{"role": "user", "content": user_prompt}])
    except Exception as e:
        print(f"Error generating interview question for level {level_index}: {e}")
        content = question["question"]
    return add_message(session_id, "assistant", content, "question", level_index)


def _generate_benchmarks(rag, session_id: int, case_id: str, level_index: int) -> list:
    questions = _get_case_questions(case_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        system_prompt = (
            f"You are Cosmos AI. Framework context:\n{context}\n\n"
            "The conversation so far is the question you asked and the user's answer to it. Given that, "
            "write three example answers at increasing depth, labeled exactly:\n"
            "Level 1 (superficial, fact-based)\nLevel 2 (needs-based)\nLevel 3 (insight-driven)\n"
            "Do not evaluate or grade the user's answer directly - just provide the three benchmark "
            "answers for comparison."
        )
        messages = get_level_messages(session_id, level_index)
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(system_prompt, messages)
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
    question_msg = _ask_question(rag, session["id"], case_id, 0)
    update_session(session["id"], 0, "awaiting_answer")
    return {"session_id": session["id"], "phase": "awaiting_answer", "current_level_index": 0, "messages": [question_msg]}


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
        if level_index < len(questions) - 1:
            next_level = level_index + 1
            question_msg = _ask_question(rag, session_id, case_id, next_level)
            update_session(session_id, next_level, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": next_level, "messages": [question_msg]}
        update_session(session_id, level_index, "complete")
        return {"phase": "complete", "current_level_index": level_index, "messages": []}

    raise ValueError(f"Session {session_id} is not awaiting input (phase={phase})")
