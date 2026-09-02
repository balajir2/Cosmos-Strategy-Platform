locals {
  bucket_name = "cosmos-artifacts-${var.env}"
}

resource "google_project_service" "required" {
  for_each = toset([
    "storage.googleapis.com",
    "run.googleapis.com",
    "eventarc.googleapis.com",
    "speech.googleapis.com",
    "pubsub.googleapis.com",
  ])
  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

resource "google_storage_bucket" "artifacts" {
  name                        = local.bucket_name
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  depends_on = [google_project_service.required]
}

resource "google_service_account" "backend" {
  account_id   = "cosmos-backend-sa"
  display_name = "Cosmos backend (main app) service account"
  project      = var.project_id
}

resource "google_service_account" "processor" {
  account_id   = "cosmos-processor-sa"
  display_name = "Cosmos artifact processor service account"
  project      = var.project_id
}

# objectAdmin, not objectCreator: the backend's artifact-delete endpoint
# deletes at whatever gcs_object_path currently holds, which is raw/... for
# any artifact still Queued/Uploaded or stuck mid-processing. Create-only
# would 403 there and leave stuck artifacts undeletable.
resource "google_storage_bucket_iam_member" "backend_writes_raw" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.backend.email}"

  condition {
    title      = "raw-prefix-only"
    expression = "resource.name.startsWith(\"projects/_/buckets/${local.bucket_name}/objects/raw/\")"
  }
}

resource "google_storage_bucket_iam_member" "backend_admins_processed_and_failed" {
  for_each = toset(["processed", "failed"])
  bucket   = google_storage_bucket.artifacts.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${google_service_account.backend.email}"

  condition {
    title      = "${each.value}-prefix-only"
    expression = "resource.name.startsWith(\"projects/_/buckets/${local.bucket_name}/objects/${each.value}/\")"
  }
}

resource "google_storage_bucket_iam_member" "processor_full_access" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.processor.email}"
}

# The audio-staging bucket for Speech-to-Text isn't owned by this module, so
# bind against the bucket name rather than a bucket resource. The processor
# both writes and cleans up the staged audio, hence objectAdmin.
resource "google_storage_bucket_iam_member" "processor_admins_transcribe_bucket" {
  bucket = var.transcribe_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_project_iam_member" "processor_eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

data "google_storage_project_service_account" "gcs_service_account" {
  project = var.project_id
}

resource "google_project_iam_member" "gcs_publishes_to_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs_service_account.email_address}"
}

resource "google_secret_manager_secret_iam_member" "processor_reads_database_url" {
  secret_id = var.database_url_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_project_iam_member" "processor_speech_user" {
  project = var.project_id
  role    = "roles/speech.editor"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_cloud_run_v2_service" "processor" {
  name     = "cosmos-artifact-processor"
  project  = var.project_id
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.processor.email
    # Generous ceiling for transcribe_audio's ~5-minute Speech-to-Text polling
    # plus parse/embed time; the default request timeout would cut audio off.
    timeout = "900s"

    containers {
      image   = var.processor_image
      command = ["uvicorn"]
      args    = ["processor_main:app", "--host", "0.0.0.0", "--port", "8080"]

      # The 512 MiB / 1 vCPU Cloud Run v2 default OOMs: processor_main loads a
      # SentenceTransformer (model + torch) at import time.
      resources {
        limits = {
          memory = "2Gi"
          cpu    = "2"
        }
      }

      env {
        name  = "GCS_ARTIFACTS_BUCKET"
        value = local.bucket_name
      }
      env {
        name  = "GCS_TRANSCRIBE_BUCKET"
        value = var.transcribe_bucket_name
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.database_url_secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_eventarc_trigger" "artifact_raw_uploaded" {
  name     = "cosmos-artifact-raw-trigger"
  project  = var.project_id
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  matching_criteria {
    attribute = "bucket"
    value     = google_storage_bucket.artifacts.name
  }

  service_account = google_service_account.processor.email

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.processor.name
      region  = var.region
      path    = "/"
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service_iam_member" "eventarc_invokes_processor" {
  name     = google_cloud_run_v2_service.processor.name
  project  = var.project_id
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.processor.email}"
}
