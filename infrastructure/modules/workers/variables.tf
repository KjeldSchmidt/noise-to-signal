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
    schedule_expression             = optional(string)
    subscribe_feed_items            = optional(bool, false)
    invoke_bedrock                  = optional(bool, false)
    use_agentcore_memory            = optional(bool, false)
    langsmith_agent_id              = optional(string)
    langsmith_tracing_sampling_rate = optional(number)
    memory_size                     = optional(number, 512)
    timeout                         = optional(number, 60)
    # SQS ESM only; AWS minimum is 2. Caps parallel worker invokes for relaxed drain.
    sqs_maximum_concurrency = optional(number)
    # Write theme-analysis artifacts when analysis_artifacts_enabled is true.
    write_analysis_artifacts = optional(bool, false)
  }))
  description = "Map of worker name → config. Name must match lambdas/<name>/ and ECR tag prefix."
}

variable "analysis_artifacts_enabled" {
  type        = bool
  default     = false
  description = "Plan-time flag: wire analysis S3 IAM/env (do not key count off computed bucket ARN)."
}

variable "analysis_artifacts_bucket_name" {
  type        = string
  default     = ""
  description = "S3 bucket for theme_analysis artifacts."
}

variable "analysis_artifacts_bucket_arn" {
  type        = string
  default     = ""
  description = "ARN of analysis_artifacts_bucket_name (may be unknown until apply)."
}

variable "agentcore_memory_enabled" {
  type        = bool
  default     = false
  description = "Plan-time flag: wire AgentCore Memory IAM/env (do not key count off computed memory id/arn)."
}

variable "agentcore_memory_id" {
  type        = string
  default     = ""
  description = "Bedrock AgentCore Memory id for preference workers (may be unknown until apply)."
}

variable "agentcore_preference_namespace" {
  type        = string
  default     = "/preferences/{actorId}"
  description = "Namespace template matching the USER_PREFERENCE strategy."
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
