variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "image_tag" {
  type        = string
  default     = "latest"
  description = "Base tag; each worker image is <name>-<image_tag> in ECR"
}

variable "ecr_repository_url" {
  type        = string
  description = "Shared ECR repository URL from the shared stack"
}

variable "public_hostname" {
  type        = string
  description = "Public web hostname (e.g. beta.noise-to-signal.fyi) for WEB_API_BASE_URL"
}

variable "app_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for noise-to-signal/<env>/app (INTERNAL_API_TOKEN)"
}

variable "feed_items_queue_arn" {
  type        = string
  description = "SQS queue ARN for news_parser event source mapping (from web_app)"
}

variable "workers" {
  type = map(object({
    schedule_expression  = optional(string)
    subscribe_feed_items = optional(bool, false)
    invoke_bedrock       = optional(bool, false)
    langsmith_agent_id   = optional(string)
    memory_size          = optional(number, 512)
    timeout              = optional(number, 60)
  }))
  description = "Map of worker name → config. Name must match lambdas/<name>/ and ECR tag prefix."
}

variable "bedrock_region" {
  type        = string
  default     = ""
  description = "Optional Bedrock region override (defaults to the Lambda AWS region)."
}

variable "langsmith_secret_name" {
  type        = string
  default     = ""
  description = "Secrets Manager name for LangSmith API key JSON. Empty → {project}/{environment}/langsmith"
}

variable "langsmith_endpoint" {
  type        = string
  default     = "https://eu.api.smith.langchain.com"
  description = "LangSmith API endpoint (EU by default)."
}
