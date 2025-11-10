#!/bin/bash
# Deployment script for AWS Elastic Beanstalk

set -e

echo "🚀 Deploying RiftRewind to AWS Elastic Beanstalk"

# Check if EB CLI is installed
if ! command -v eb &> /dev/null; then
    echo "❌ EB CLI not found. Install with: pip install awsebcli"
    exit 1
fi

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS CLI not configured. Run: aws configure"
    exit 1
fi

# Configuration
REGION=${AWS_REGION:-us-east-2}
BUCKET_NAME=${MODELS_BUCKET:-riftrewind-models-$(date +%s)}
SECRET_NAME="riftrewind/riot-api-key"
APP_NAME="riftrewind"
ENV_NAME="${APP_NAME}-prod"

echo "📦 Creating S3 bucket for ML models..."
if ! aws s3 ls "s3://${BUCKET_NAME}" 2>/dev/null; then
    aws s3 mb "s3://${BUCKET_NAME}" --region ${REGION}
    echo "✅ Created bucket: ${BUCKET_NAME}"
else
    echo "ℹ️  Bucket already exists: ${BUCKET_NAME}"
fi

echo "📤 Uploading ML models to S3..."
aws s3 sync ml_training/models/ "s3://${BUCKET_NAME}/models/" --region ${REGION}
echo "✅ Models uploaded"

echo "🔐 Checking for Riot API key in Secrets Manager..."
if ! aws secretsmanager describe-secret --secret-id ${SECRET_NAME} --region ${REGION} &>/dev/null; then
    echo "❌ Secret '${SECRET_NAME}' not found in Secrets Manager"
    echo "Please create it with:"
    echo "  aws secretsmanager create-secret --name ${SECRET_NAME} --secret-string '{\"RIOT_API_KEY\":\"your_key_here\"}' --region ${REGION}"
    exit 1
fi
echo "✅ Secret found"

echo "🔧 Initializing Elastic Beanstalk..."
if [ ! -d ".elasticbeanstalk" ]; then
    eb init -p python-3.11 ${APP_NAME} --region ${REGION}
fi

echo "🌍 Creating/updating Elastic Beanstalk environment..."
if ! eb list | grep -q ${ENV_NAME}; then
    echo "Creating new environment: ${ENV_NAME}"
    eb create ${ENV_NAME} \
        --instance-type t3.medium \
        --envvars MODELS_BUCKET=${BUCKET_NAME},AWS_REGION=${REGION},SECRET_NAME=${SECRET_NAME}
else
    echo "Updating existing environment: ${ENV_NAME}"
    eb use ${ENV_NAME}
    eb setenv MODELS_BUCKET=${BUCKET_NAME} AWS_REGION=${REGION} SECRET_NAME=${SECRET_NAME}
fi

echo "🚀 Deploying application..."
eb deploy

echo "✅ Deployment complete!"
echo ""
echo "Your application is running at:"
eb status | grep CNAME

echo ""
echo "To view logs: eb logs"
echo "To open app: eb open"
