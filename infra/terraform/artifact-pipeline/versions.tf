terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    # Configured via `terraform init -backend-config=...` (bucket/prefix vary
    # by environment) - see README.md. Terraform backend blocks cannot
    # reference variables, so this is intentionally left partial.
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
