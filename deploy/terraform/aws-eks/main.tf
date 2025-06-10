# Terraform module to create EKS cluster and deploy sentientos via Helm

provider "aws" {
  region = var.region
}

module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  version         = "~> 19.0"
  cluster_name    = var.cluster_name
  cluster_version = "1.29"
  subnet_ids      = var.subnet_ids
  vpc_id          = var.vpc_id
}

resource "helm_release" "sentientos" {
  name       = "sentientos"
  repository = "oci://ghcr.io/${var.github_owner}/charts"
  chart      = "sentientos"
  version    = "0.4.1"
  values     = [file("../../helm/sentientos/values.yaml")]
}

variable "region" {}
variable "cluster_name" {}
variable "subnet_ids" { type = list(string) }
variable "vpc_id" {}
variable "github_owner" {}
