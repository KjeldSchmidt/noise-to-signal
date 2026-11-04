output "function_name" {
  value = aws_lambda_function.web.function_name
}

output "function_arn" {
  value = aws_lambda_function.web.arn
}

output "function_url" {
  description = "Raw Lambda Function URL (origin only; prefer service_url)"
  value       = aws_lambda_function_url.web.function_url
}

output "service_url" {
  description = "Public HTTPS URL (custom domain; use for Google OAuth)"
  value       = "https://${var.public_hostname}/"
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.web.domain_name
}

output "app_secret_name" {
  value = aws_secretsmanager_secret.app.name
}

output "app_secret_arn" {
  description = "Shared app secret (SECRET_KEY, DATABASE_URL, INTERNAL_API_TOKEN) for web + worker Lambdas"
  value       = aws_secretsmanager_secret.app.arn
}

output "google_oauth_secret_name" {
  value = data.aws_secretsmanager_secret.google_oauth.name
}

output "db_name" {
  value = var.db_name
}

output "image_identifier" {
  value = local.image_identifier
}

output "feed_items_queue_url" {
  value = aws_sqs_queue.feed_items.url
}

output "feed_items_queue_arn" {
  value = aws_sqs_queue.feed_items.arn
}
