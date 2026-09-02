variable "project_id" {
  description = "GCP project to deploy into (e.g. the dev account or the corporate account)."
  type        = string
}

variable "region" {
  description = "GCP region for the bucket and Cloud Run service."
  type        = string
  default     = "us-central1"
}

variable "env" {
  description = "Environment name, used in resource naming (e.g. 'dev', 'prod')."
  type        = string
}

variable "processor_image" {
  description = "Container image URI for the cosmos-artifact-processor Cloud Run service (built/pushed by CI)."
  type        = string
}

variable "transcribe_bucket_name" {
  description = "GCS bucket used to stage audio for Google Speech-to-Text (GCS_TRANSCRIBE_BUCKET), already provisioned outside this module. Without it every audio artifact degrades to 'Transcript Needed'."
  type        = string
}

variable "database_url_secret_id" {
  description = "Secret Manager secret ID holding the Neon DATABASE_URL, already provisioned outside this module."
  type        = string
}
