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

