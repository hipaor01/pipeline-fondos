terraform {
  backend "s3" {
    key          = "pipeline-fondos/dev/storage/terraform.tfstate"
    region       = "eu-west-3"
    encrypt      = true
    use_lockfile = true
  }
}

# El nombre del bucket de estado se proporciona mediante -backend-config.
