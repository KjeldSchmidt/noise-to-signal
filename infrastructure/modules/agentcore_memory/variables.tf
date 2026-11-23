variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "event_expiry_days" {
  type        = number
  default     = 90
  description = "Short-term event TTL in days (7–365)."
}

variable "namespace_template" {
  type        = string
  default     = "/preferences/{actorId}"
  description = "User Preference strategy namespace template."
}
