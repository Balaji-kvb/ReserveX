# ECR repositories for the three ReserveX microservices.
# WHY: EKS node groups pull container images from ECR.
# Cost: ECR charges only for storage consumed; no idle compute cost.

locals {
  ecr_repos = [
    "reservex-user-service",
    "reservex-event-service",
    "reservex-booking-service",
  ]
}

resource "aws_ecr_repository" "services" {
  for_each = toset(local.ecr_repos)

  name                 = each.value
  image_tag_mutability = "MUTABLE"
  force_delete         = true # allow terraform destroy even if images exist

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Service = each.value
  }
}

# Lifecycle policy: keep only the 10 most recent images per repo
# to avoid unbounded storage costs.
resource "aws_ecr_lifecycle_policy" "cleanup" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

output "ecr_repository_urls" {
  description = "ECR repository URLs for each microservice"
  value       = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}
