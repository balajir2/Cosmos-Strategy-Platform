# Artifact Ingestion Pipeline - Terraform Module

Provisions the GCP resources for the async artifact ingestion pipeline
(spec: `docs/superpowers/specs/2026-09-02-artifact-ingestion-pipeline-design.md`):
the `cosmos-artifacts-{env}` bucket, the `cosmos-artifact-raw-trigger`
Eventarc trigger, the `cosmos-artifact-processor` Cloud Run service, and
their service accounts/IAM bindings.

## One-time prerequisite: Terraform state bucket

Terraform can't create the bucket that holds its own state, so create it
once per environment before the first `terraform init`:

    gcloud storage buckets create gs://cosmos-tfstate-<env> \
      --project=<project-id> --location=<region> --uniform-bucket-level-access

## Deploying (including to a new/corporate GCP account)

    terraform init \
      -backend-config="bucket=cosmos-tfstate-<env>" \
      -backend-config="prefix=artifact-pipeline"

    terraform apply \
      -var="project_id=<project-id>" \
      -var="env=<env>" \
      -var="processor_image=<image-uri>" \
      -var="database_url_secret_id=<secret-id>"

Moving to a different GCP account is the same two commands against that
account's `project_id`/state bucket - no manual console steps.

## Variables

See `variables.tf`. `processor_image` and `database_url_secret_id` are
expected to already exist (built/pushed by CI, and provisioned by the
main app's own deployment work respectively) - this module does not
create them.
