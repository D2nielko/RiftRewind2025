#!/bin/bash
# Deploy RiftRewind frontend to S3 for Lambda + API Gateway setup

set -e

echo "🌐 Deploying RiftRewind Frontend to S3"

# Configuration
REGION=${AWS_REGION:-us-east-2}
BUCKET_NAME=${WEBSITE_BUCKET:-riftrewind-web-$(date +%s)}
API_GATEWAY_URL=${API_GATEWAY_URL:-}

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS CLI not configured. Run: aws configure"
    exit 1
fi

# Check if API Gateway URL is provided
if [ -z "$API_GATEWAY_URL" ]; then
    echo ""
    echo "⚠️  API Gateway URL not set!"
    echo ""
    read -p "Enter your API Gateway URL (e.g., https://abc123.execute-api.us-east-2.amazonaws.com/prod): " API_GATEWAY_URL

    if [ -z "$API_GATEWAY_URL" ]; then
        echo "❌ No API Gateway URL provided"
        exit 1
    fi
fi

# Remove trailing slash if present
API_GATEWAY_URL=${API_GATEWAY_URL%/}

echo "📝 Configuration:"
echo "  - Region: ${REGION}"
echo "  - Bucket: ${BUCKET_NAME}"
echo "  - API Gateway: ${API_GATEWAY_URL}"
echo ""

# Create S3 bucket
echo "📦 Step 1: Creating S3 bucket..."
if ! aws s3 ls "s3://${BUCKET_NAME}" 2>/dev/null; then
    aws s3 mb "s3://${BUCKET_NAME}" --region ${REGION}
    echo "✅ Created bucket: ${BUCKET_NAME}"
else
    echo "ℹ️  Bucket already exists: ${BUCKET_NAME}"
fi

# Configure bucket for static website hosting
echo "🌐 Step 2: Configuring static website hosting..."
aws s3 website "s3://${BUCKET_NAME}/" \
    --index-document index.html \
    --error-document index.html \
    --region ${REGION}
echo "✅ Website hosting configured"

# Set bucket policy for public read
echo "🔓 Step 3: Setting bucket policy for public access..."
cat > /tmp/bucket-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"
    }
  ]
}
EOF

# Disable block public access
aws s3api put-public-access-block \
    --bucket ${BUCKET_NAME} \
    --public-access-block-configuration \
    "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false" \
    --region ${REGION}

# Apply bucket policy
aws s3api put-bucket-policy \
    --bucket ${BUCKET_NAME} \
    --policy file:///tmp/bucket-policy.json \
    --region ${REGION}

rm /tmp/bucket-policy.json
echo "✅ Bucket policy applied"

# Update config.js with API Gateway URL
echo "⚙️  Step 4: Updating API configuration..."
sed -i.bak "s|YOUR_API_GATEWAY_URL_HERE|${API_GATEWAY_URL}|g" static-website/js/config.js
echo "✅ API endpoint configured"

# Upload files to S3
echo "📤 Step 5: Uploading website files..."
aws s3 sync static-website/ "s3://${BUCKET_NAME}/" \
    --region ${REGION} \
    --delete \
    --cache-control "max-age=3600"

# Set proper content types
aws s3 cp "s3://${BUCKET_NAME}/" "s3://${BUCKET_NAME}/" \
    --exclude "*" \
    --include "*.html" \
    --content-type "text/html" \
    --metadata-directive REPLACE \
    --recursive \
    --region ${REGION}

aws s3 cp "s3://${BUCKET_NAME}/" "s3://${BUCKET_NAME}/" \
    --exclude "*" \
    --include "*.css" \
    --content-type "text/css" \
    --metadata-directive REPLACE \
    --recursive \
    --region ${REGION}

aws s3 cp "s3://${BUCKET_NAME}/" "s3://${BUCKET_NAME}/" \
    --exclude "*" \
    --include "*.js" \
    --content-type "application/javascript" \
    --metadata-directive REPLACE \
    --recursive \
    --region ${REGION}

echo "✅ Files uploaded"

# Restore original config.js
mv static-website/js/config.js.bak static-website/js/config.js 2>/dev/null || true

# Get website URL
WEBSITE_URL="http://${BUCKET_NAME}.s3-website-${REGION}.amazonaws.com"

echo ""
echo "✅ Deployment Complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Your website is now live at:"
echo "   ${WEBSITE_URL}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📌 Next Steps:"
echo ""
echo "1. Visit your website:"
echo "   ${WEBSITE_URL}"
echo ""
echo "2. (Optional) Set up CloudFront for HTTPS:"
echo "   aws cloudfront create-distribution --origin-domain-name ${BUCKET_NAME}.s3-website-${REGION}.amazonaws.com"
echo ""
echo "3. (Optional) Configure custom domain with Route 53"
echo ""
echo "💡 Tips:"
echo "  - Website URL: ${WEBSITE_URL}"
echo "  - API Endpoint: ${API_GATEWAY_URL}"
echo "  - To update: Re-run this script or use 'aws s3 sync'"
echo ""
