resource "aws_api_gateway_rest_api" "events" {
  name = "${local.name_prefix}-api"
}

resource "aws_api_gateway_resource" "events" {
  rest_api_id = aws_api_gateway_rest_api.events.id
  parent_id   = aws_api_gateway_rest_api.events.root_resource_id
  path_part   = "events"
}

resource "aws_api_gateway_method" "post_events" {
  rest_api_id   = aws_api_gateway_rest_api.events.id
  resource_id   = aws_api_gateway_resource.events.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "post_events" {
  rest_api_id             = aws_api_gateway_rest_api.events.id
  resource_id             = aws_api_gateway_resource.events.id
  http_method             = aws_api_gateway_method.post_events.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ingest.invoke_arn
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.events.execution_arn}/*/POST/events"
}

resource "aws_api_gateway_deployment" "events" {
  rest_api_id = aws_api_gateway_rest_api.events.id
  depends_on = [
    aws_api_gateway_integration.post_events,
    aws_api_gateway_integration.post_batch
  ]

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_method.post_events.id,
      aws_api_gateway_integration.post_events.id,
      aws_api_gateway_method.post_batch.id,
      aws_api_gateway_integration.post_batch.id
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "events" {
  rest_api_id   = aws_api_gateway_rest_api.events.id
  deployment_id = aws_api_gateway_deployment.events.id
  stage_name    = var.environment
}

resource "aws_api_gateway_resource" "batch" {
  rest_api_id = aws_api_gateway_rest_api.events.id
  parent_id   = aws_api_gateway_resource.events.id
  path_part   = "batch"
}

resource "aws_api_gateway_method" "post_batch" {
  rest_api_id   = aws_api_gateway_rest_api.events.id
  resource_id   = aws_api_gateway_resource.batch.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "post_batch" {
  rest_api_id             = aws_api_gateway_rest_api.events.id
  resource_id             = aws_api_gateway_resource.batch.id
  http_method             = aws_api_gateway_method.post_batch.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.batch_ingest.invoke_arn
}

resource "aws_lambda_permission" "api_gateway_batch" {
  statement_id  = "AllowApiGatewayInvokeBatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.batch_ingest.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.events.execution_arn}/*/POST/events/batch"
}