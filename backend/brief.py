import html


def compile_brief_markdown(project: dict, responses: list) -> str:
    """Assembles a project's saved responses into a markdown strategic brief,
    grouped by stage (in the order responses_db.get_responses_for_project
    already returns them - sequence_order then question id), with each
    question's submitted answer and self-evaluation. Deliberately a simple
    template assembly, not a document-generation pipeline - per the
    roadmap's own scope note for this endpoint."""
    lines = [f"# Strategic Brief: {project['name']}", "", f"**Customer:** {project['customer_name']}", ""]
    if project.get("industry_context"):
        lines += [f"**Industry Context:** {project['industry_context']}", ""]

    if not responses:
        lines += ["_No responses have been submitted for this project yet._"]
        return "\n".join(lines)

    current_stage = None
    for r in responses:
        if r["stage_name"] != current_stage:
            current_stage = r["stage_name"]
            lines += [f"## {current_stage}", ""]

        lines += [
            f"### {r['level']}: {r['question_text']}",
            "",
            f"**Submitted Answer:** {r['submitted_text'] or '_No answer submitted._'}",
            "",
            f"**Self-Evaluation:** {r['self_evaluation_status'] or '_Not self-evaluated._'}",
            "",
        ]
        if r["self_evaluation_notes"]:
            lines += [f"**Notes:** {r['self_evaluation_notes']}", ""]

    return "\n".join(lines)


_BENCHMARK_LEVELS = [
    ("Level 1 - Superficial", "#ece9f7", "#5b4d8a", "benchmark_level_1"),
    ("Level 2 - Needs-Based", "#fdeedb", "#a8631a", "benchmark_level_2"),
    ("Level 3 - Insight-Driven", "#dff3e7", "#1f8a55", "benchmark_level_3"),
]


def _render_benchmark_grid(response: dict) -> str:
    cells = []
    for label, bg, fg, key in _BENCHMARK_LEVELS:
        text = html.escape(response[key]) if response.get(key) else ""
        cells.append(
            f'<td style="background:{bg};color:{fg};padding:12px;border-radius:8px;'
            f'vertical-align:top;width:33%;">'
            f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
            f'margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:13px;">{text}</div></td>'
        )
    return '<table style="width:100%;border-spacing:8px 0;margin:12px 0;"><tr>' + "".join(cells) + "</tr></table>"


def compile_brief_html(project: dict, responses: list) -> str:
    """HTML counterpart to compile_brief_markdown, for emailing the report
    (backend/main.py's send-report endpoint). Includes the Level 1/2/3
    benchmark comparison per question, which the markdown version omits.
    All user- and LLM-supplied text is HTML-escaped before interpolation,
    since submitted answers, self-evaluation notes, and benchmark text are
    free text that could otherwise break the HTML structure or inject markup."""
    parts = [
        f"<h1>Strategic Brief: {html.escape(project['name'])}</h1>",
        f"<p><strong>Customer:</strong> {html.escape(project['customer_name'])}</p>",
    ]
    if project.get("industry_context"):
        parts.append(f"<p><strong>Industry Context:</strong> {html.escape(project['industry_context'])}</p>")

    if not responses:
        parts.append("<p><em>No responses have been submitted for this project yet.</em></p>")
        return "".join(parts)

    current_stage = None
    for r in responses:
        if r["stage_name"] != current_stage:
            current_stage = r["stage_name"]
            parts.append(f"<h2>{html.escape(current_stage)}</h2>")

        parts.append(f"<h3>{html.escape(r['level'])}: {html.escape(r['question_text'])}</h3>")

        answer = html.escape(r["submitted_text"]) if r["submitted_text"] else "<em>No answer submitted.</em>"
        parts.append(f"<p><strong>Submitted Answer:</strong> {answer}</p>")

        status = html.escape(r["self_evaluation_status"]) if r["self_evaluation_status"] else "<em>Not self-evaluated.</em>"
        parts.append(f"<p><strong>Self-Evaluation:</strong> {status}</p>")

        if r["self_evaluation_notes"]:
            parts.append(f"<p><strong>Notes:</strong> {html.escape(r['self_evaluation_notes'])}</p>")

        if r.get("benchmark_level_1") or r.get("benchmark_level_2") or r.get("benchmark_level_3"):
            parts.append(_render_benchmark_grid(r))
        else:
            parts.append("<p><em>Benchmark comparison not available for this response.</em></p>")

    return "".join(parts)
