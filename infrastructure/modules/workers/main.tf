terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.14"
    }
  }
}

data "aws_secretsmanager_secret_version" "app" {
  secret_id = var.app_secret_arn
}

locals {
  name_prefix = "${var.project}-${var.environment}"
  tags = {
    Project     = var.project
    Environment = var.environment
  }
  app_secret = jsondecode(data.aws_secretsmanager_secret_version.app.secret_string)
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  for_each = var.workers

  name               = "${local.name_prefix}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = merge(local.tags, { Worker = each.key })
}

resource "aws_iam_role_policy_attachment" "basic" {
  for_each = var.workers

  role       = aws_iam_role.worker[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "secrets" {
  statement {
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [var.app_secret_arn]
  }
}

resource "aws_iam_role_policy" "secrets" {
  for_each = var.workers

  name   = "secrets"
  role   = aws_iam_role.worker[each.key].id
  policy = data.aws_iam_policy_document.secrets.json
}

resource "aws_lambda_function" "worker" {
  for_each = var.workers

  function_name = "${local.name_prefix}-${each.key}"
  role          = aws_iam_role.worker[each.key].arn
  package_type  = "Image"
  image_uri     = "${var.ecr_repository_url}:${each.key}-${var.image_tag}"
  memory_size   = each.value.memory_size
  timeout       = each.value.timeout
  architectures = ["x86_64"]

  image_config {
    command = ["main.handler"]
  }

  environment {
    variables = {
      WEB_API_BASE_URL   = "https://${var.public_hostname}"
      INTERNAL_API_TOKEN = local.app_secret.INTERNAL_API_TOKEN
    }
  }

  tags = merge(local.tags, { Worker = each.key })

  depends_on = [
    aws_iam_role_policy_attachment.basic,
    aws_iam_role_policy.secrets,
  ]
}

resource "aws_cloudwatch_event_rule" "schedule" {
  for_each = {
    for name, cfg in var.workers : name => cfg
    if try(cfg.schedule_expression, null) != null && cfg.schedule_expression != ""
  }

  name                = "${local.name_prefix}-${each.key}"
  description         = "Schedule for ${each.key}"
  schedule_expression = each.value.schedule_expression
  tags                = merge(local.tags, { Worker = each.key })
}

resource "aws_cloudwatch_event_target" "lambda" {
  for_each = aws_cloudwatch_event_rule.schedule

  rule      = each.value.name
  target_id = each.key
  arn       = aws_lambda_function.worker[each.key].arn
}

resource "aws_lambda_permission" "events" {
  for_each = aws_cloudwatch_event_rule.schedule

  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.worker[each.key].function_name
  principal     = "events.amazonaws.com"
  source_arn    = each.value.arn
}
