#!/bin/bash
# Setup script for AWS resources

set -e

echo "🔧 Setting up AWS resources for RiftRewind"

# Configuration
REGION=${AWS_REGION:-us-east-1}
BUCKET_NAME=${MODELS_BUCKET:-riftrewind-models-$(date +%s)}
SECRET_NAME="riftrewind/riot-api-key"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS CLI not configured. Run: aws configure"
    exit 1
fi

echo "📦 Step 1: Creating S3 bucket for ML models"
if ! aws s3 ls "s3://${BUCKET_NAME}" 2>/dev/null; then
    aws s3 mb "s3://${BUCKET_NAME}" --region ${REGION}
    echo "✅ Created bucket: ${BUCKET_NAME}"
else
    echo "ℹ️  Bucket already exists: ${BUCKET_NAME}"
fi

echo "📤 Step 2: Uploading ML models to S3"
aws s3 sync ml_training/models/ "s3://${BUCKET_NAME}/models/" --region ${REGION}
echo "✅ Models uploaded to s3://${BUCKET_NAME}/models/"

echo "🔐 Step 3: Setting up Secrets Manager"
read -p "Enter your Riot API Key: " RIOT_API_KEY

if [ -z "${RIOT_API_KEY}" ]; then
    echo "❌ No API key provided"
    exit 1
fi

# Check if secret already exists
if aws secretsmanager describe-secret --secret-id ${SECRET_NAME} --region ${REGION} &>/dev/null; then
    echo "ℹ️  Secret already exists. Updating..."
    aws secretsmanager update-secret \
        --secret-id ${SECRET_NAME} \
        --secret-string "{\"RIOT_API_KEY\":\"${RIOT_API_KEY}\"}" \
        --region ${REGION}
else
    echo "Creating new secret..."
    aws secretsmanager create-secret \
        --name ${SECRET_NAME} \
        --description "Riot Games API Key for RiftRewind" \
        --secret-string "{\"RIOT_API_KEY\":\"${RIOT_API_KEY}\"}" \
        --region ${REGION}
fi
echo "✅ Secret configured"

echo "📝 Step 4: Creating IAM policy for application"
POLICY_NAME="RiftRewindTaskPolicy"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create policy document with actual bucket name
cat > /tmp/riftrewind-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}",
        "arn:aws:s3:::${BUCKET_NAME}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:${REGION}:${ACCOUNT_ID}:secret:${SECRET_NAME}-*"
    }
  ]
}
EOF

# Create or update policy
if aws iam get-policy --policy-arn "arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}" &>/dev/null; then
    echo "ℹ️  Policy already exists, creating new version..."
    aws iam create-policy-version \
        --policy-arn "arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}" \
        --policy-document file:///tmp/riftrewind-policy.json \
        --set-as-default
else
    aws iam create-policy \
        --policy-name ${POLICY_NAME} \
        --policy-document file:///tmp/riftrewind-policy.json \
        --description "Policy for RiftRewind application to access S3 models and Secrets Manager"
fi
echo "✅ IAM policy configured"

rm /tmp/riftrewind-policy.json

echo ""
echo "✅ AWS resources setup complete!"
echo ""
echo "📋 Summary:"
echo "  - S3 Bucket: ${BUCKET_NAME}"
echo "  - Secret Name: ${SECRET_NAME}"
echo "  - Region: ${REGION}"
echo "  - IAM Policy: ${POLICY_NAME}"
echo ""
echo "📌 Next steps:"
echo "  1. Attach the policy to your EC2/ECS/Lambda execution role"
echo "  2. Set environment variables:"
echo "     export MODELS_BUCKET=${BUCKET_NAME}"
echo "     export AWS_REGION=${REGION}"
echo "     export SECRET_NAME=${SECRET_NAME}"
echo ""
echo "  3. Deploy your application using one of:"
echo "     - ./aws/deploy-to-eb.sh (Elastic Beanstalk)"
echo "     - docker build & push to ECR (ECS/Fargate)"
echo "     - See AWS_DEPLOYMENT_GUIDE.md for more options"
