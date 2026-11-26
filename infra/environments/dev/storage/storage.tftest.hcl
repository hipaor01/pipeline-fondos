mock_provider "aws" {
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
}

run "bucket_nuevo" {
  command = plan
  variables {
    bucket_name   = "bucket-documentos-prueba"
    create_bucket = true
  }
  assert {
    condition     = length(aws_s3_bucket.documents) == 1 && aws_s3_bucket.documents[0].force_destroy == false
    error_message = "El bucket nuevo debe existir y preservar sus objetos al destruirse."
  }
  assert {
    condition     = aws_s3_bucket_versioning.documents[0].versioning_configuration[0].status == "Enabled" && one(aws_s3_bucket_server_side_encryption_configuration.documents[0].rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "El bucket debe estar versionado y cifrado con SSE-S3."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.documents[0].block_public_acls && aws_s3_bucket_public_access_block.documents[0].block_public_policy && aws_s3_bucket_public_access_block.documents[0].ignore_public_acls && aws_s3_bucket_public_access_block.documents[0].restrict_public_buckets
    error_message = "Deben estar activos los cuatro bloqueos de acceso público."
  }
  assert {
    condition     = output.bucket_name == "bucket-documentos-prueba" && output.bucket_arn == "arn:aws:s3:::bucket-documentos-prueba" && output.bucket_region == "eu-west-3"
    error_message = "Las salidas deben identificar el bucket y la región."
  }
}

run "bucket_existente" {
  command = plan
  variables {
    bucket_name = "bucket-existente-prueba"
  }
  assert {
    condition     = length(aws_s3_bucket.documents) == 0 && length(aws_s3_bucket_versioning.documents) == 0 && length(aws_s3_bucket_server_side_encryption_configuration.documents) == 0 && length(aws_s3_bucket_public_access_block.documents) == 0
    error_message = "La referencia a un bucket existente no debe administrar recursos."
  }
  assert {
    condition     = output.bucket_name == "bucket-existente-prueba" && output.bucket_arn == "arn:aws:s3:::bucket-existente-prueba"
    error_message = "Las salidas deben referenciar el bucket existente."
  }
}
