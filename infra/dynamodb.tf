resource "aws_dynamodb_table" "event_counts" {
  name         = "${local.name_prefix}-event-counts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_name"

  attribute {
    name = "event_name"
    type = "S"
  }
}

