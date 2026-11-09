terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.14"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

data "aws_secretsmanager_secret" "shared_rds" {
  name = var.shared_rds_secret_name
}

data "aws_secretsmanager_secret_version" "shared_rds" {
  secret_id = data.aws_secretsmanager_secret.shared_rds.id
}

locals {
  name_prefix = "${var.project}-${var.environment}"
  tags = {
    Project     = var.project
    Environment = var.environment
  }

  rds = jsondecode(data.aws_secretsmanager_secret_version.shared_rds.secret_string)

  database_url = format(
    "postgresql://%s:%s@%s:%s/%s?sslmode=require",
    local.rds.username,
    urlencode(local.rds.password),
    local.rds.host,
    tostring(local.rds.port),
    var.db_name,
  )

  image_identifier = "${var.ecr_repository_url}:${var.image_tag}"

  google_oauth_secret_name = var.google_oauth_secret_name != "" ? var.google_oauth_secret_name : "${var.project}/${var.environment}/google-oauth"

  app_secret   = jsondecode(aws_secretsmanager_secret_version.app.secret_string)
  google_oauth = jsondecode(data.aws_secretsmanager_secret_version.google_oauth.secret_string)

  function_url_hostname = trimsuffix(
    replace(aws_lambda_function_url.web.function_url, "https://", ""),
    "/",
  )
}

resource "random_password" "django_secret" {
  length  = 50
  special = false
}

resource "random_password" "internal_api_token" {
  length  = 64
  special = false
}

data "aws_secretsmanager_secret" "google_oauth" {
  name = local.google_oauth_secret_name
}

data "aws_secretsmanager_secret_version" "google_oauth" {
  secret_id = data.aws_secretsmanager_secret.google_oauth.id
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project}/${var.environment}/app"
  description             = "noise-to-signal Lambda runtime secrets (SECRET_KEY, DATABASE_URL, INTERNAL_API_TOKEN)"
  recovery_window_in_days = 0
  tags                    = local.tags
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    SECRET_KEY         = random_password.django_secret.result
    DATABASE_URL       = local.database_url
    INTERNAL_API_TOKEN = random_password.internal_api_token.result
  })
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name_prefix}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_secrets" {
  statement {
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      aws_secretsmanager_secret.app.arn,
      data.aws_secretsmanager_secret.google_oauth.arn,
    ]
  }
}

resource "aws_iam_role_policy" "lambda_secrets" {
  name   = "secrets"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_secrets.json
}

resource "aws_sqs_queue" "feed_items_dlq" {
  name                      = "${local.name_prefix}-feed-items-dlq"
  message_retention_seconds = 1209600
  tags                      = local.tags
}

resource "aws_sqs_queue" "feed_items" {
  name = "${local.name_prefix}-feed-items"
  # news_parser timeout is 120s; AWS recommends ≥6× Lambda timeout for SQS.
  visibility_timeout_seconds = 720
  message_retention_seconds  = 345600
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.feed_items_dlq.arn
    maxReceiveCount     = 5
  })
  tags = local.tags
}

data "aws_iam_policy_document" "lambda_sqs_send" {
  statement {
    actions   = ["sqs:SendMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"]
    resources = [aws_sqs_queue.feed_items.arn]
  }
}

resource "aws_iam_role_policy" "lambda_sqs_send" {
  name   = "sqs-feed-items-send"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_sqs_send.json
}

resource "aws_lambda_function" "web" {
  function_name = local.name_prefix
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.image_identifier
  memory_size   = var.memory_size
  timeout       = var.timeout
  architectures = ["x86_64"]

  image_config {
    command = ["config.lambda_handler.handler"]
  }

  environment {
    variables = {
      DEBUG        = "false"
      DATABASE_SSL = "true"
      # Host comes from CloudFront via X-Forwarded-Host (see cloudfront_function).
      ALLOWED_HOSTS = join(",", [
        var.public_hostname,
        ".noise-to-signal.fyi",
        ".cloudfront.net",
        ".lambda-url.${var.aws_region}.on.aws",
      ])
      SITE_DOMAIN          = var.public_hostname
      SECRET_KEY           = local.app_secret.SECRET_KEY
      DATABASE_URL         = local.app_secret.DATABASE_URL
      INTERNAL_API_TOKEN   = local.app_secret.INTERNAL_API_TOKEN
      FEED_ITEMS_QUEUE_URL = aws_sqs_queue.feed_items.url
      GOOGLE_CLIENT_ID     = local.google_oauth.GOOGLE_CLIENT_ID
      GOOGLE_CLIENT_SECRET = local.google_oauth.GOOGLE_CLIENT_SECRET
    }
  }

  tags = local.tags

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_secrets,
    aws_iam_role_policy.lambda_sqs_send,
    aws_secretsmanager_secret_version.app,
  ]
}

resource "aws_lambda_function_url" "web" {
  function_name      = aws_lambda_function.web.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "function_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.web.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

# CloudFront Functions cannot set X-Forwarded-* (disallowed → 502).
# Pass viewer Host as a custom header; Django middleware promotes it.
resource "aws_cloudfront_function" "x_forwarded_host" {
  name    = "${local.name_prefix}-xfh"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = <<-EOF
    function handler(event) {
      var request = event.request;
      if (request.headers.host) {
        request.headers["x-viewer-host"] = { value: request.headers.host.value };
      }
      return request;
    }
  EOF
}

resource "aws_cloudfront_distribution" "web" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = local.name_prefix
  aliases             = [var.public_hostname]
  default_root_object = ""
  price_class         = "PriceClass_100"
  wait_for_deployment = true
  tags                = local.tags

  origin {
    domain_name = local.function_url_hostname
    origin_id   = "lambda-function-url"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "lambda-function-url"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods  = ["GET", "HEAD"]
    compress        = true

    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.x_forwarded_host.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

resource "aws_route53_record" "app_a" {
  zone_id = var.hosted_zone_id
  name    = var.public_hostname
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "app_aaaa" {
  zone_id = var.hosted_zone_id
  name    = var.public_hostname
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.web.domain_name
    zone_id                = aws_cloudfront_distribution.web.hosted_zone_id
    evaluate_target_health = false
  }
}
