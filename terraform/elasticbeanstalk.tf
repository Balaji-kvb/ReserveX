# Elastic Beanstalk application and environment for ReserveX staging.
# WHY: Provides a quick staging deployment target before full EKS production.
# Cost: Single-instance environment (no ELB) to minimize costs.

resource "aws_elastic_beanstalk_application" "reservex" {
  name        = "reservex"
  description = "ReserveX event reservation platform"
}

resource "aws_elastic_beanstalk_environment" "staging" {
  name                = "reservex-staging"
  application         = aws_elastic_beanstalk_application.reservex.name
  solution_stack_name = "64bit Amazon Linux 2023 v4.5.2 running Docker"
  tier                = "WebServer"

  # Single-instance: no ELB, cheapest option for staging.
  setting {
    namespace = "aws:elasticbeanstalk:environment"
    name      = "EnvironmentType"
    value     = "SingleInstance"
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "InstanceType"
    value     = "t3.micro"
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "IamInstanceProfile"
    value     = aws_iam_instance_profile.eb_profile.name
  }

  # Place in VPC private subnet so it can reach the same network.
  setting {
    namespace = "aws:ec2:vpc"
    name      = "VPCId"
    value     = module.vpc.vpc_id
  }

  setting {
    namespace = "aws:ec2:vpc"
    name      = "Subnets"
    value     = module.vpc.public_subnets[0]
  }

  tags = {
    Stage = "Staging"
  }
}

# ----- IAM for Elastic Beanstalk instances -----

resource "aws_iam_role" "eb_instance" {
  name = "reservex-eb-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eb_web" {
  role       = aws_iam_role.eb_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkWebTier"
}

resource "aws_iam_role_policy_attachment" "eb_docker" {
  role       = aws_iam_role.eb_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkMulticontainerDocker"
}

resource "aws_iam_role_policy_attachment" "eb_ecr_read" {
  role       = aws_iam_role.eb_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "eb_profile" {
  name = "reservex-eb-instance-profile"
  role = aws_iam_role.eb_instance.name
}

output "eb_environment_url" {
  description = "Elastic Beanstalk staging environment URL"
  value       = aws_elastic_beanstalk_environment.staging.cname
}
