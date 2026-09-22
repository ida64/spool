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


resource "aws_dynamodb_table" "projects" {
  name         = "${local.name_prefix}-projects"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "project_id"

  attribute {
    name = "project_id"
    type = "S"
  }
}

resource "aws_dynamodb_table_item" "default_project" {
  table_name = aws_dynamodb_table.projects.name
  hash_key   = aws_dynamodb_table.projects.hash_key

  item = jsonencode({
    project_id = { S = var.default_project_id }
    token_hash = { S = sha256(var.ingest_token) }
    enabled    = { BOOL = true }
  })
}

resource "aws_dynamodb_table" "event_buckets" {
  name         = "${local.name_prefix}-event-buckets"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "event_name"
  range_key    = "bucket"

  attribute {
    name = "event_name"
    type = "S"
  }

  attribute {
    name = "bucket"
    type = "S"
  }
}
