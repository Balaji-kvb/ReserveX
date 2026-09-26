#!/bin/bash
set -e

# Phase 14: ECR images (multi-arch for ARM to x86)
# WHY multi-arch: The developer is on an Apple Silicon (ARM) Mac.
# AWS EKS nodes are typically x86_64 (Intel/AMD).
# If we just run 'docker build', it builds an ARM image which crashes on EKS.
# We must use 'docker buildx' to cross-compile for linux/amd64.

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "Error: AWS_ACCOUNT_ID environment variable is not set."
    echo "Usage: AWS_ACCOUNT_ID=123456789012 AWS_REGION=us-east-1 ./build_and_push.sh"
    exit 1
fi

AWS_REGION=${AWS_REGION:-us-east-1}
ECR_BASE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
VERSION=${1:-latest}

echo "=== Authenticating with ECR ==="
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_BASE

# Ensure buildx is setup
docker buildx create --use --name multi-arch-builder 2>/dev/null || true

build_and_push() {
    SERVICE=$1
    echo "=== Building and pushing $SERVICE ==="
    
    # Ensure ECR repository exists
    aws ecr describe-repositories --repository-names reservex-$SERVICE --region $AWS_REGION || \
    aws ecr create-repository --repository-name reservex-$SERVICE --region $AWS_REGION

    docker buildx build \
        --platform linux/amd64,linux/arm64 \
        -t $ECR_BASE/reservex-$SERVICE:$VERSION \
        --push \
        services/$SERVICE
}

build_and_push "user-service"
build_and_push "event-service"
build_and_push "booking-service"

echo "=== All images built and pushed successfully ==="
