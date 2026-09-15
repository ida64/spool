output "api_endpoint" {
  description = "POST endpoint for submitting events."
  value       = "${aws_api_gateway_stage.events.invoke_url}/events"
}

output "batch_api_endpoint" {
  description = "POST endpoint for submitting batches of events."
  value       = "${aws_api_gateway_stage.events.invoke_url}/events/batch"
}

output "api_key_value" {
  description = "API Gateway key for Roblox X-API-Key requests. Treat as secret."
  sensitive   = true
  value       = aws_api_gateway_api_key.ingest.value
}

output "kinesis_stream_name" {
  value = aws_kinesis_stream.events.name
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.event_counts.name
}

output "ingest_lambda_name" {
  value = aws_lambda_function.ingest.function_name
}

output "processor_lambda_name" {
  value = aws_lambda_function.processor.function_name
}

output "processor_failure_queue_url" {
  description = "Queue containing processor batches that exhausted retries."
  value       = aws_sqs_queue.processor_failures.url
}
