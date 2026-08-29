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
