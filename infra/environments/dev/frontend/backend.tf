terraform {
  backend "s3" {
    key          = "pipeline-fondos/dev/frontend/terraform.tfstate"
    region       = "eu-west-3"
    encrypt      = true
    use_lockfile = true
  }
}
