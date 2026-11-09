# Account-wide shared resources: ECR + DNS (Route 53 + ACM for CloudFront).
terraform {
  required_version = ">= 1.13.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.14"
    }
  }

  backend "s3" {
    bucket       = "tck-labs-tfstate-6fd94603"
    key          = "noise-to-signal.shared.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-central-1"
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

module "ecr" {
  source = "../../modules/ecr"

  project = "noise-to-signal"
}

module "dns" {
  source = "../../modules/dns"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  project     = "noise-to-signal"
  domain_name = "noise-to-signal.fyi"
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "ecr_repository_name" {
  value = module.ecr.repository_name
}

output "domain_name" {
  value = module.dns.domain_name
}

output "route53_zone_id" {
  value = module.dns.zone_id
}

output "acm_certificate_arn" {
  value = module.dns.acm_certificate_arn
}

output "name_servers" {
  description = "Set these NS records at the domain registrar for noise-to-signal.fyi"
  value       = module.dns.name_servers
}
