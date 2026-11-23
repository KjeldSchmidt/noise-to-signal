terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.14"
    }
  }
}

locals {
  name_prefix = replace("${var.project}_${var.environment}_prefs", "-", "_")
  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_bedrockagentcore_memory" "prefs" {
  name                  = local.name_prefix
  description           = "noise-to-signal user preference memory (${var.environment})"
  event_expiry_duration = var.event_expiry_days
  tags                  = local.tags
}

resource "aws_bedrockagentcore_memory_strategy" "user_preference" {
  name                = "UserPreferences"
  memory_id           = aws_bedrockagentcore_memory.prefs.id
  type                = "USER_PREFERENCE"
  description         = "Extract lasting reading preferences per actorId"
  namespace_templates = [var.namespace_template]
}
