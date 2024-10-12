# Provider
provider "aws" {
  profile = "assets_checker"
  region = "ap-northeast-1"
  default_tags {
    tags = {
      owner     = "notion-assets"
      terraform = "true"
    }
  }
}

locals {
  parsed_data = jsondecode(file("${path.module}/config.json"))
  env_vars = merge({
    for key, value in lookup(local.parsed_data, "env_vars", {}) :
    key => sensitive(value)
  }, {"ASSETS_DATA": replace(file("${path.module}/assets.json"), "\\s+", "")})
  layers = concat([aws_lambda_layer_version.aiohttp_layer.arn], lookup(local.parsed_data, "layers", []))
}

resource "aws_iam_role" "lambda_exec_role" {
  name = "asset_checker_lambda_exec_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy_attachment" "lambda_policy" {
  name       = "asset_checker_lambda_policy_attach"
  roles      = [aws_iam_role.lambda_exec_role.name]
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}


locals {
  aiohttp_layer_dir = "${path.module}/aiohttp_layer"
}

data "external" "lambda_layer" {
  program = ["./pip_init.sh"]
}

data "archive_file" "lambda_layer_zip" {
  type        = "zip"
  source_dir  = data.external.lambda_layer.result.path
  output_path = "${path.module}/aiohttp_layer.zip"
}

resource "aws_lambda_layer_version" "aiohttp_layer" {
  filename   = "${path.module}/aiohttp_layer.zip"
  layer_name = "aiohttp_layer"
  compatible_runtimes = ["python3.12"]  # Update to the Python version of your Lambda function
  source_code_hash = filebase64sha256(data.archive_file.lambda_layer_zip.output_path)
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/src/"
  output_path = "${path.module}/src-zipped.zip"
}

resource "aws_lambda_function" "python_lambda" {
  function_name = "assets_check"
  role          = aws_iam_role.lambda_exec_role.arn
  handler       = "func.lambda_handler"
  runtime       = "python3.12"
  filename      = "${path.module}/src-zipped.zip"
  source_code_hash = filebase64sha256(data.archive_file.lambda_zip.output_path)
  layers        = local.layers

  environment {
    variables = local.env_vars
  }
}

resource "aws_lambda_function_url" "lambda_function_url" {
  function_name = aws_lambda_function.python_lambda.function_name
  authorization_type = "NONE"

  provisioner "local-exec" {
    command = "echo Function URL is ${self.function_url}"
  }
}

resource "aws_dynamodb_table" "assets_checker_table" {
  name           = "assets_checker_table"
  billing_mode   = "PAY_PER_REQUEST" 
  hash_key       = "name"

  attribute {
    name = "name"
    type = "S"
  }
}