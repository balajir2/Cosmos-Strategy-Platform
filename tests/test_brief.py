import brief

_PROJECT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar",
    "industry_context": "B2C, personal care",
}
_RESPONSES = [
    {
        "id": 1, "question_id": 100, "project_id": 1, "submitted_text": "my answer",
        "self_evaluation_notes": "solid reasoning", "self_evaluation_status": "Strong",
        "status": "Self-Evaluated", "updated_at": "2026-08-28T09:00:00",
        "question_text": "What core attributes...?", "level": "Level 7: Business Model",
        "stage_name": "Aim & SWOT", "sequence_order": 1,
    },
    {
        "id": 2, "question_id": 101, "project_id": 1, "submitted_text": None,
        "self_evaluation_notes": None, "self_evaluation_status": None,
        "status": "Draft", "updated_at": "2026-08-28T09:00:00",
        "question_text": "Which adjacent category opportunities...?", "level": "Level 6: Market Opportunities",
        "stage_name": "Opportunity Expansion", "sequence_order": 2,
    },
]


def test_compile_brief_markdown_includes_project_header():
    markdown = brief.compile_brief_markdown(_PROJECT, _RESPONSES)
    assert "# Strategic Brief: Blazar India Entry" in markdown
    assert "**Customer:** Blazar" in markdown
    assert "**Industry Context:** B2C, personal care" in markdown


def test_compile_brief_markdown_groups_by_stage():
    markdown = brief.compile_brief_markdown(_PROJECT, _RESPONSES)
    assert "## Aim & SWOT" in markdown
    assert "## Opportunity Expansion" in markdown
    assert markdown.index("## Aim & SWOT") < markdown.index("## Opportunity Expansion")


def test_compile_brief_markdown_includes_answer_and_self_evaluation():
    markdown = brief.compile_brief_markdown(_PROJECT, _RESPONSES)
    assert "### Level 7: Business Model: What core attributes...?" in markdown
    assert "**Submitted Answer:** my answer" in markdown
    assert "**Self-Evaluation:** Strong" in markdown
    assert "**Notes:** solid reasoning" in markdown


def test_compile_brief_markdown_handles_unanswered_question():
    markdown = brief.compile_brief_markdown(_PROJECT, _RESPONSES)
    assert "_No answer submitted._" in markdown
    assert "_Not self-evaluated._" in markdown


def test_compile_brief_markdown_handles_no_responses_at_all():
    markdown = brief.compile_brief_markdown(_PROJECT, [])
    assert "_No responses have been submitted for this project yet._" in markdown
