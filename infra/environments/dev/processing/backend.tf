terraform {
  backend "s3" {
    key          = "pipeline-fondos/dev/processing/terraform.tfstate"
    region       = "eu-west-3"
    encrypt      = true
    use_lockfile = true
  }
}
