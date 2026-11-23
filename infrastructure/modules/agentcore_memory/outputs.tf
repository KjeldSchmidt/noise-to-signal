output "memory_id" {
  value = aws_bedrockagentcore_memory.prefs.id
}

output "memory_arn" {
  value = aws_bedrockagentcore_memory.prefs.arn
}

output "namespace_template" {
  value = var.namespace_template
}
