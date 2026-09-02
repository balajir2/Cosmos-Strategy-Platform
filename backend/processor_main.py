from fastapi import FastAPI, Request

import gcs_artifact_storage
import project_artifacts_db
import project_knowledge_base
from rag_engine import RagEngine

app = FastAPI(title="Cosmos Artifact Processor")
rag = RagEngine()


def parse_event_payload(body: dict) -> dict:
    name = body["name"]
    parts = name.split("/")
    if len(parts) < 4 or parts[0] != "raw":
        raise ValueError(f"Unexpected object path for artifact processing (expected 'raw/...'): '{name}'")
    project_id, artifact_id = int(parts[1]), int(parts[2])
    filename = "/".join(parts[3:])
    return {"bucket": body["bucket"], "name": name, "project_id": project_id, "artifact_id": artifact_id, "filename": filename}


@app.post("/")
async def handle_gcs_event(request: Request):
    body = await request.json()
    event = parse_event_payload(body)
    artifact_id = event["artifact_id"]

    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None:
        return {"status": "skipped", "reason": "artifact no longer exists"}
    if artifact["status"] != "Queued":
        return {"status": "skipped", "reason": f"already {artifact['status']}"}

    file_bytes = gcs_artifact_storage.download_object(event["name"])
    result = project_knowledge_base.ingest_artifact(rag, artifact_id, file_bytes)

    dest_prefix = "processed" if result["status"] in ("Indexed", "Transcript Needed") else "failed"
    new_path = gcs_artifact_storage.move_object(event["name"], dest_prefix)

    current = project_artifacts_db.get_artifact_by_id(artifact_id)
    if current is None:
        gcs_artifact_storage.delete_object(new_path)
        return {"status": "skipped", "reason": "artifact deleted during processing"}

    project_artifacts_db.update_artifact_status(artifact_id, result["status"], gcs_object_path=new_path)
    return {"status": "processed", "artifact_id": artifact_id}
