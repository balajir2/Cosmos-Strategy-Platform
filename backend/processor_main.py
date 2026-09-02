from fastapi import FastAPI, Request
from sentence_transformers import SentenceTransformer

import gcs_artifact_storage
import project_artifacts_db
import project_knowledge_base

app = FastAPI(title="Cosmos Artifact Processor")

# Must match the model rag_engine.RagEngine loads, so processor-written
# project_kb_chunks embeddings stay comparable with the ones the main app
# writes and queries.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingOnlyEngine:
    """The minimum shape ingest_artifact needs (it only ever touches
    `.embedding_model`). Deliberately NOT a full RagEngine: RagEngine.__init__
    also runs load_or_build_index(), which - against an empty or misconfigured
    framework_kb_chunks table, or an image without archives/ - would have a
    processor cold start write into the SHARED Framework Knowledge Base, which
    this service has no business touching. It also skips the LLM-provider and
    PDF-parsing setup the processor never uses."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.embedding_model = SentenceTransformer(model_name)


rag = EmbeddingOnlyEngine()


def parse_event_payload(body: dict) -> dict:
    name = body["name"]
    parts = name.split("/")
    if len(parts) < 4 or parts[0] != "raw":
        raise ValueError(f"Unexpected object path for artifact processing (expected 'raw/...'): '{name}'")
    project_id, artifact_id = int(parts[1]), int(parts[2])
    filename = "/".join(parts[3:])
    return {"bucket": body["bucket"], "name": name, "project_id": project_id, "artifact_id": artifact_id, "filename": filename}


def _recover_failed(object_name: str, artifact_id: int, error: Exception) -> dict:
    """Best-effort cleanup after an exception mid-processing. Without it,
    ingest_artifact's early flip to 'Processing' would strand the artifact
    there forever: the idempotency guard skips anything not
    Uploaded/Queued, so every Eventarc retry would no-op. Each step is
    guarded so a failure here can never raise - a 500 makes Eventarc retry a
    delivery that cannot succeed."""
    print(f"Error processing artifact {artifact_id}: {error}")
    failed_path = None
    try:
        failed_path = gcs_artifact_storage.move_object(object_name, "failed")
    except Exception as move_error:
        print(f"Could not move artifact {artifact_id}'s object to failed/: {move_error}")
    try:
        project_artifacts_db.update_artifact_status(artifact_id, "Failed", gcs_object_path=failed_path)
    except Exception as db_error:
        print(f"Could not mark artifact {artifact_id} as Failed: {db_error}")
    return {"status": "failed", "artifact_id": artifact_id, "reason": str(error)}


@app.post("/")
async def handle_gcs_event(request: Request):
    body = await request.json()
    try:
        event = parse_event_payload(body)
    except (ValueError, KeyError) as e:
        # Eventarc's GCS-direct triggers can only match on bucket/type - there
        # is no object-name-prefix filter - so this service's own writes to
        # processed/ and failed/ re-trigger it. Those (and any other payload we
        # can't parse) must return 200: a 500 would make Eventarc/Pub-Sub retry
        # a delivery that can never succeed, for days.
        return {"status": "skipped", "reason": str(e)}

    artifact_id = event["artifact_id"]

    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None:
        return {"status": "skipped", "reason": "artifact no longer exists"}
    # 'Uploaded' is the DB default, and the upload endpoint flips the row to
    # 'Queued' only after the GCS write returns - so an event delivered inside
    # that window legitimately still reads 'Uploaded'. Treating it as
    # unprocessable would strand the artifact permanently (no-op, no retry).
    if artifact["status"] not in ("Uploaded", "Queued"):
        return {"status": "skipped", "reason": f"already {artifact['status']}"}

    try:
        file_bytes = gcs_artifact_storage.download_object(event["name"])
        result = project_knowledge_base.ingest_artifact(rag, artifact_id, file_bytes)
        if result is None:
            # ingest_artifact's own closing status update matched no row: the
            # artifact was deleted mid-processing. Nothing left to move to.
            gcs_artifact_storage.delete_object(event["name"])
            return {"status": "skipped", "reason": "artifact deleted during processing"}

        dest_prefix = "processed" if result["status"] in ("Indexed", "Transcript Needed") else "failed"
        new_path = gcs_artifact_storage.move_object(event["name"], dest_prefix)

        current = project_artifacts_db.get_artifact_by_id(artifact_id)
        if current is None:
            gcs_artifact_storage.delete_object(new_path)
            return {"status": "skipped", "reason": "artifact deleted during processing"}

        project_artifacts_db.update_artifact_status(artifact_id, result["status"], gcs_object_path=new_path)
        return {"status": "processed", "artifact_id": artifact_id}
    except Exception as e:
        return _recover_failed(event["name"], artifact_id, e)
