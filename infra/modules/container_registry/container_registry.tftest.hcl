mock_provider "aws" {}

variables {
  repository_name = "test"
  environment     = "dev"
}

run "politica_por_defecto" {
  command = plan
  assert {
    condition = jsondecode(aws_ecr_lifecycle_policy.this.policy).rules[0].selection == {
      tagStatus = "any", countType = "imageCountMoreThan", countNumber = 30
    }
    error_message = "El comportamiento predeterminado debe conservar la política existente."
  }
}

run "politica_de_captura" {
  command = plan
  variables {
    expirable_tag_prefix = "desechable-"
  }
  assert {
    condition = (
      jsondecode(aws_ecr_lifecycle_policy.this.policy).rules[0].selection.tagStatus == "tagged" &&
      jsondecode(aws_ecr_lifecycle_policy.this.policy).rules[0].selection.tagPrefixList == ["desechable-"]
    )
    error_message = "Solo las imágenes marcadas como desechables deben poder expirar."
  }
}
