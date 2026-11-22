terraform {
  backend "s3" {
    key          = "pipeline-fondos/dev/terraform.tfstate"
    region       = "eu-west-3"
    encrypt      = true
    use_lockfile = true
  }
}

# El bucket se proporciona durante `terraform init` porque su nombre incluye
# el ID de la cuenta y se obtiene del output de infra/bootstrap.
