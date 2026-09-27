# Phase 15: EC2 load generator
# WHY: We need a machine outside the Kubernetes cluster to run k6
# and simulate external traffic hitting the AWS Network Load Balancer (NLB).
# Running k6 from our local laptop over the internet might be bottlenecked
# by local bandwidth or Wi-Fi. An EC2 instance in the same VPC is ideal.

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_security_group" "load_generator_sg" {
  name        = "reservex-load-generator-sg"
  description = "Security group for load generator"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_role" "ssm_role" {
  name = "reservex-load-generator-ssm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_policy" {
  role       = aws_iam_role.ssm_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ssm_profile" {
  name = "reservex-load-generator-profile"
  role = aws_iam_role.ssm_role.name
}

resource "aws_instance" "load_generator" {
  ami           = data.aws_ami.amazon_linux_2023.id
  instance_type = "t3.medium" # Needs some CPU to generate high load

  subnet_id              = module.vpc.private_subnets[0]
  vpc_security_group_ids = [aws_security_group.load_generator_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ssm_profile.name

  # Install k6 automatically
  user_data = <<-EOF
              #!/bin/bash
              sudo dnf install -y https://dl.k6.io/rpm/repo.rpm
              sudo dnf install -y k6
              EOF

  tags = {
    Name = "reservex-load-generator"
  }
}

output "load_generator_id" {
  value       = aws_instance.load_generator.id
  description = "Use AWS Systems Manager (SSM) Session Manager to connect to this instance"
}
