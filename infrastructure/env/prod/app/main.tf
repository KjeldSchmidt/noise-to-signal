terraform {
  required_version = ">= 1.13.0"

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

  backend "s3" {
    bucket       = "tck-labs-tfstate-6fd94603"
    key          = "noise-to-signal.prod.app.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-central-1"
}

data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "tck-labs-tfstate-6fd94603"
    key    = "noise-to-signal.shared.tfstate"
    region = "eu-central-1"
  }
}

module "web" {
  source = "../../../modules/web_app"

  project             = "noise-to-signal"
  environment         = "prod"
  db_name             = "noise_to_signal_prod"
  ecr_repository_url  = data.terraform_remote_state.shared.outputs.ecr_repository_url
  image_tag           = var.image_tag
  public_hostname     = "signal-to-noise.fyi"
  hosted_zone_id      = data.terraform_remote_state.shared.outputs.route53_zone_id
  acm_certificate_arn = data.terraform_remote_state.shared.outputs.acm_certificate_arn
}

module "workers" {
  source = "../../../modules/workers"

  project              = "noise-to-signal"
  environment          = "prod"
  ecr_repository_url   = data.terraform_remote_state.shared.outputs.ecr_repository_url
  image_tag            = var.image_tag
  public_hostname      = "signal-to-noise.fyi"
  app_secret_arn       = module.web.app_secret_arn
  feed_items_queue_arn = module.web.feed_items_queue_arn

  workers = {
    feed_consumer = {
      schedule_expression = "rate(240 minutes)"
      memory_size         = 512
      timeout             = 120
    }
    news_parser = {
      subscribe_feed_items = true
      memory_size          = 512
      timeout              = 60
    }
  }
}

variable "image_tag" {
  type    = string
  default = "latest"
}

output "ecr_repository_url" {
  value = data.terraform_remote_state.shared.outputs.ecr_repository_url
}

output "service_url" {
  value = module.web.service_url
}

output "function_url" {
  value = module.web.function_url
}

output "function_name" {
  value = module.web.function_name
}

output "function_arn" {
  value = module.web.function_arn
}

output "cloudfront_domain_name" {
  value = module.web.cloudfront_domain_name
}

output "public_hostname" {
  value = "signal-to-noise.fyi"
}

output "app_secret_name" {
  value = module.web.app_secret_name
}

output "app_secret_arn" {
  value = module.web.app_secret_arn
}

output "google_oauth_secret_name" {
  value = module.web.google_oauth_secret_name
}

output "db_name" {
  value = module.web.db_name
}

output "image_identifier" {
  value = module.web.image_identifier
}

output "worker_function_names" {
  value = module.workers.function_names
}

output "worker_function_arns" {
  value = module.workers.function_arns
}

output "worker_image_identifiers" {
  value = module.workers.image_identifiers
}

output "feed_items_queue_url" {
  value = module.web.feed_items_queue_url
}
