variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "eu-central-1"
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "ECR image tag (must already exist in the base-stack repository)"
}

variable "ecr_repository_url" {
  type        = string
  description = "From the base stack (ECR)"
}

variable "shared_rds_secret_name" {
  type    = string
  default = "tck-labs/shared/rds"
}

variable "db_name" {
  type = string
}

variable "google_oauth_secret_name" {
  type        = string
  default     = ""
  description = "Secrets Manager secret with GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET"
}

variable "memory_size" {
  type    = number
  default = 1024
}

variable "timeout" {
  type        = number
  default     = 90
  description = "Web Lambda timeout (chat sync-invokes news_chat; keep ≥ worker answer latency)."
}

variable "origin_read_timeout" {
  type        = number
  default     = 90
  description = "CloudFront origin response timeout (must cover chat round-trip)."
}

variable "news_chat_function_name" {
  type        = string
  default     = ""
  description = "Lambda function name for news_chat (empty disables invoke wiring)."
}

variable "public_hostname" {
  type        = string
  description = "Custom hostname for this env (e.g. beta.noise-to-signal.fyi)"
}

variable "hosted_zone_id" {
  type        = string
  description = "Route 53 zone id from the shared DNS stack"
}

variable "acm_certificate_arn" {
  type        = string
  description = "us-east-1 ACM certificate ARN (wildcard) from the shared DNS stack"
}
