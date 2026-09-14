resource "aws_kinesis_stream" "events" {
  name = "${local.name_prefix}-events"
  stream_mode_details { stream_mode = "ON_DEMAND" }
  retention_period = 24
}

