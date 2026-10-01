terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }

    helm = {
      source  = "hashicorp/helm"
      version = "3.3.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  required_version = ">= 1.5.0"
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "ReserveX"
      Environment = "Production"
    }
  }
}

data "aws_eks_cluster" "reservex" {
  name = module.eks.cluster_name
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.reservex.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.reservex.certificate_authority[0].data)

  exec {
    api_version = "client.authentication.k8s.io/v1"
    command     = "aws"

    args = [
      "eks",
      "get-token",
      "--cluster-name",
      data.aws_eks_cluster.reservex.name,
      "--region",
      var.aws_region,
    ]
  }
}

provider "helm" {
  kubernetes = {
    host                   = data.aws_eks_cluster.reservex.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.reservex.certificate_authority[0].data)

    exec = {
      api_version = "client.authentication.k8s.io/v1"
      command     = "aws"

      args = [
        "eks",
        "get-token",
        "--cluster-name",
        data.aws_eks_cluster.reservex.name,
        "--region",
        var.aws_region,
      ]
    }
  }
}
