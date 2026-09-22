data "archive_file" "ingest" {
  type        = "zip"
  source_file = "${path.module}/../services/ingest/handler.py"
  output_path = "${path.module}/ingest.zip"
}

data "archive_file" "batch_ingest" {
  type        = "zip"
  source_file = "${path.module}/../services/batch_ingest/handler.py"
  output_path = "${path.module}/batch_ingest.zip"
}

data "archive_file" "processor" {
  type        = "zip"
  source_file = "${path.module}/../services/processor/handler.py"
  output_path = "${path.module}/processor.zip"
}

data "archive_file" "incident_analyzer" {
  type        = "zip"
  source_file = "${path.module}/../services/incident_analyzer/handler.py"
  output_path = "${path.module}/incident_analyzer.zip"
}

resource "aws_lambda_function" "incident_analyzer" {
  function_name = "${local.name_prefix}-incident-analyzer"
  role          = aws_iam_role.incident_analyzer.arn

  runtime = "python3.12"
  handler = "handler.lambda_handler"

  filename         = data.archive_file.incident_analyzer.output_path
  source_code_hash = data.archive_file.incident_analyzer.output_base64sha256

  timeout     = 30
  memory_size = 128
}

resource "aws_lambda_function" "ingest" {
  function_name    = "${local.name_prefix}-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  timeout          = 10
  environment {
    variables = {
      KINESIS_STREAM_NAME = aws_kinesis_stream.events.name
      INGEST_TOKEN        = var.ingest_token
      ALLOWED_GAME_ID     = var.allowed_game_id
    }
  }
}

resource "aws_lambda_function" "batch_ingest" {
  function_name    = "${local.name_prefix}-batch-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.batch_ingest.output_path
  source_code_hash = data.archive_file.batch_ingest.output_base64sha256
  timeout          = 10

  environment {
    variables = {
      KINESIS_STREAM_NAME = aws_kinesis_stream.events.name
      INGEST_TOKEN        = var.ingest_token
      ALLOWED_GAME_ID     = var.allowed_game_id
    }
  }
}

resource "aws_lambda_function" "processor" {
  function_name    = "${local.name_prefix}-processor"
  role             = aws_iam_role.processor.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.processor.output_path
  source_code_hash = data.archive_file.processor.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      TABLE_NAME       = aws_dynamodb_table.event_counts.name
      DEDUP_TABLE_NAME = aws_dynamodb_table.processed_events.name
      BUCKET_TABLE_NAME = aws_dynamodb_table.event_buckets.name
    }
  }
}

resource "aws_lambda_event_source_mapping" "processor" {
  event_source_arn               = aws_kinesis_stream.events.arn
  function_name                  = aws_lambda_function.processor.arn
  starting_position              = "LATEST"
  batch_size                     = 100
  enabled                        = true
  function_response_types        = ["ReportBatchItemFailures"]
  bisect_batch_on_function_error = true
  maximum_retry_attempts         = 3
  maximum_record_age_in_seconds  = 3600

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.processor_failures.arn
    }
  }
}
