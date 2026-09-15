resource "aws_sns_topic" "incidents" {
  name = "${local.name_prefix}-incidents"
}

resource "aws_cloudwatch_metric_alarm" "processor_errors" {
  alarm_name        = "${local.name_prefix}-processor-errors"
  alarm_description = "Triggers when the Spool processor experiences repeated errors."

  namespace   = "AWS/Lambda"
  metric_name = "Errors"
  statistic   = "Sum"

  period             = 300
  evaluation_periods = 1
  threshold          = 3

  comparison_operator = "GreaterThanOrEqualToThreshold"

  dimensions = {
    FunctionName = aws_lambda_function.processor.function_name
  }

  treat_missing_data = "notBreaching"

  alarm_actions = [
    aws_sns_topic.incidents.arn
  ]
}

resource "aws_sns_topic_subscription" "incident_analyzer" {
  topic_arn = aws_sns_topic.incidents.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.incident_analyzer.arn
}

resource "aws_lambda_permission" "sns_incident_analyzer" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.incident_analyzer.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.incidents.arn
}