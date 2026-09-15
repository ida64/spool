variable "aws_region" {
  description = "AWS region for the telemetry platform."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used in resource names."
  type        = string
  default     = "spool"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "ingest_token" {
  description = "Bearer token accepted by Roblox ingestion requests. Set via TF_VAR_ingest_token."
  type        = string
  sensitive   = true
}

variable "allowed_game_id" {
  description = "Optional Roblox universe/game ID allowed to submit events. Empty disables the check."
  type        = string
  default     = ""
}

variable "api_rate_limit" {
  description = "Maximum API requests per second for the Spool usage plan."
  type        = number
  default     = 10
}

variable "api_burst_limit" {
  description = "Maximum short burst of API requests for the Spool usage plan."
  type        = number
  default     = 20
}
