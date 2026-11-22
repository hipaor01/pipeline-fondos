terraform {
  backend "s3" {
    key          = "pipeline-fondos/dev/artifacts/terraform.tfstate"
    region       = "eu-west-3"
    encrypt      = true
    use_lockfile = true
  }
}

# La pipeline proporciona el nombre del bucket mediante -backend-config.
