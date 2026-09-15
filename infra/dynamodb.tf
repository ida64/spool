resource "aws_dynamodb_table" "event_counts" {
  name         = "${local.name_prefix}-event-counts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_name"

  attribute {
    name = "event_name"
    type = "S"
  }
}

resource "aws_dynamodb_table" "processed_events" {
  name         = "${local.name_prefix}-processed-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
