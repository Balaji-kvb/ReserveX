# Lambda function for the async notification/audit webhook.
# WHY (Phase 16): The Booking Service invokes this Lambda with
# InvocationType="Event" after a successful booking commit.
# Lambda failure MUST NOT roll back or affect the booking.
# Cost: Lambda charges only per invocation; zero idle cost.

# ----- IAM Role for Lambda execution -----

resource "aws_iam_role" "lambda_exec" {
  name = "reservex-lambda-exec-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ----- Package the Lambda code -----

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda/webhook.py"
  output_path = "${path.module}/.build/lambda_webhook.zip"
}

# ----- Lambda Function -----

resource "aws_lambda_function" "webhook" {
  function_name = "reservex-notification"
  description   = "Async webhook handler for booking confirmations"

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  runtime = "python3.12"
  handler = "webhook.lambda_handler"
  timeout = 30
  role    = aws_iam_role.lambda_exec.arn


  tags = {
    Service = "notification"
  }
}

# Async invocation settings:
# 0 retries — if it fails once, drop it.
# Booking is already committed; retrying adds no business value.
resource "aws_lambda_function_event_invoke_config" "webhook" {
  function_name                = aws_lambda_function.webhook.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 300
}

output "lambda_function_arn" {
  description = "ARN of the ReserveX notification Lambda"
  value       = aws_lambda_function.webhook.arn
}

output "lambda_function_name" {
  description = "Name of the ReserveX notification Lambda"
  value       = aws_lambda_function.webhook.function_name
}
