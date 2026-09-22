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

}

