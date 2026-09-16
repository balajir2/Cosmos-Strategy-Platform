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
        "benchmark_level_1": "superficial benchmark text", "benchmark_level_2": "needs-based benchmark text",
        "benchmark_level_3": "insight-driven benchmark text",
    },
    {
        "id": 2, "question_id": 101, "project_id": 1, "submitted_text": None,
        "self_evaluation_notes": None, "self_evaluation_status": None,
        "status": "Draft", "updated_at": "2026-08-28T09:00:00",
        "question_text": "Which adjacent category opportunities...?", "level": "Level 6: Market Opportunities",
        "stage_name": "Opportunity Expansion", "sequence_order": 2,
        "benchmark_level_1": None, "benchmark_level_2": None, "benchmark_level_3": None,
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


def test_compile_brief_html_includes_project_header():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "<h1>Strategic Brief: Blazar India Entry</h1>" in result
    assert "<strong>Customer:</strong> Blazar" in result
    assert "<strong>Industry Context:</strong> B2C, personal care" in result


def test_compile_brief_html_groups_by_stage():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "<h2>Aim &amp; SWOT</h2>" in result
    assert "<h2>Opportunity Expansion</h2>" in result
    assert result.index("Aim &amp; SWOT") < result.index("Opportunity Expansion")


def test_compile_brief_html_includes_benchmark_comparison():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "Level 1 - Superficial" in result
    assert "superficial benchmark text" in result
    assert "Level 2 - Needs-Based" in result
    assert "needs-based benchmark text" in result
    assert "Level 3 - Insight-Driven" in result
    assert "insight-driven benchmark text" in result


def test_compile_brief_html_handles_missing_benchmark():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "Benchmark comparison not available for this response." in result


def test_compile_brief_html_handles_unanswered_question():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "No answer submitted." in result
    assert "Not self-evaluated." in result


def test_compile_brief_html_handles_no_responses_at_all():
    result = brief.compile_brief_html(_PROJECT, [])
    assert "No responses have been submitted for this project yet." in result


def test_compile_brief_html_escapes_user_supplied_text():
    malicious = [{**_RESPONSES[0], "submitted_text": "<script>alert('x')</script>"}]
    result = brief.compile_brief_html(_PROJECT, malicious)
    assert "<script>alert" not in result
    assert "&lt;script&gt;" in result
