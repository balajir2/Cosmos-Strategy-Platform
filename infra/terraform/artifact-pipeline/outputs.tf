output "bucket_name" {
  value       = google_storage_bucket.artifacts.name
  description = "The cosmos-artifacts-{env} bucket name."
}

output "processor_service_url" {
  value       = google_cloud_run_v2_service.processor.uri
  description = "The (private, Eventarc-only) URL of the cosmos-artifact-processor Cloud Run service."
}
