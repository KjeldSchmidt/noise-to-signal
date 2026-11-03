output "function_names" {
  value = { for name, fn in aws_lambda_function.worker : name => fn.function_name }
}

output "function_arns" {
  value = { for name, fn in aws_lambda_function.worker : name => fn.arn }
}

output "image_identifiers" {
  value = {
    for name, fn in aws_lambda_function.worker : name => fn.image_uri
  }
}
