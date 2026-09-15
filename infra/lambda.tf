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

resource "aws_lambda_function" "ingest" {
  function_name    = "${local.name_prefix}-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  timeout          = 10
  environment { variables = { KINESIS_STREAM_NAME = aws_kinesis_stream.events.name } }
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
  environment { variables = { TABLE_NAME = aws_dynamodb_table.event_counts.name } }
}

resource "aws_lambda_event_source_mapping" "processor" {
  event_source_arn  = aws_kinesis_stream.events.arn
  function_name     = aws_lambda_function.processor.arn
  starting_position = "LATEST"
  batch_size        = 100
  enabled           = true
}

