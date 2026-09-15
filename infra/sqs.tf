resource "aws_sqs_queue" "processor_failures" {
  name                      = "${local.name_prefix}-processor-failures"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
