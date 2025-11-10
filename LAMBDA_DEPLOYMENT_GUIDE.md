# Complete Lambda + API Gateway Deployment Guide

This guide walks you through deploying RiftRewind as a serverless application using AWS Lambda + API Gateway + S3.

## Architecture Overview

```
┌──────────────┐      ┌─────────────────┐      ┌──────────────┐
│   Browser    │─────>│  S3 Website     │      │  API Gateway │
│              │      │  (Frontend)     │─────>│              │
└──────────────┘      └─────────────────┘      └──────┬───────┘
                                                       │
                                                       v
                                              ┌────────────────┐
                                              │  Lambda        │
                                              │  (Backend)     │
                                              └────────┬───────┘
                                                       │
                      ┌────────────────────────────────┼────────────────┐
                      │                                │                │
                      v                                v                v
              ┌───────────────┐              ┌─────────────┐  ┌────────────┐
              │  S3 (Models)  │              │  Secrets    │  │ Riot API   │
              │               │              │  Manager    │  │            │
              └───────────────┘              └─────────────┘  └────────────┘
```

## Prerequisites

- AWS Account with CLI configured
- Riot Games API Key
- AWS CLI installed: `pip install awscli`
- Basic knowledge of AWS services

---

## Part 1: Setup AWS Resources (One-time setup)

### Step 1: Run the Setup Script

```bash
./aws/setup-aws-resources.sh
```

This will:
- Create S3 bucket for ML models
- Upload your models
- Store Riot API key in Secrets Manager
- Create IAM policies

**Save the bucket name** - you'll need it later!

---

## Part 2: Deploy Lambda Function

### Step 2.1: Create Lambda Execution Role

```bash
# Get your AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create trust policy
cat > /tmp/lambda-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
    --role-name riftrewind-lambda-execution-role \
    --assume-role-policy-document file:///tmp/lambda-trust-policy.json

# Attach AWS managed policies
aws iam attach-role-policy \
    --role-name riftrewind-lambda-execution-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Attach your custom policy (created by setup script)
aws iam attach-role-policy \
    --role-name riftrewind-lambda-execution-role \
    --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/RiftRewindTaskPolicy
```

### Step 2.2: Create Lambda Layer for Dependencies

The ML libraries are too large for a direct Lambda upload, so we use layers:

```bash
# Create directory for layer
mkdir -p lambda-layers/python

# Install dependencies (use x86_64 Linux compatible packages)
pip install \
    --platform manylinux2014_x86_64 \
    --target lambda-layers/python \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    requests numpy scikit-learn xgboost boto3

# Create zip
cd lambda-layers
zip -r ../lambda-layer.zip python/
cd ..

# Upload to AWS
aws lambda publish-layer-version \
    --layer-name riftrewind-dependencies \
    --description "Dependencies for RiftRewind (numpy, sklearn, xgboost, requests, boto3)" \
    --zip-file fileb://lambda-layer.zip \
    --compatible-runtimes python3.11 \
    --region us-east-1

# Save the Layer ARN that's returned - you'll need it!
```

**Note**: The output will include a `LayerVersionArn` like:
`arn:aws:lambda:us-east-1:123456789:layer:riftrewind-dependencies:1`

### Step 2.3: Package and Deploy Lambda Function

```bash
# Create deployment package
mkdir -p lambda-package
cp lambda_handler.py lambda-package/
cp -r ml_training lambda-package/

# Create zip
cd lambda-package
zip -r ../lambda-function.zip .
cd ..

# Create Lambda function
# Replace LAYER_ARN with the ARN from step 2.2
# Replace MODELS_BUCKET with your S3 bucket name from step 1

aws lambda create-function \
    --function-name riftrewind-api \
    --runtime python3.11 \
    --role arn:aws:iam::${ACCOUNT_ID}:role/riftrewind-lambda-execution-role \
    --handler lambda_handler.handler \
    --zip-file fileb://lambda-function.zip \
    --timeout 60 \
    --memory-size 1024 \
    --layers LAYER_ARN \
    --environment "Variables={MODELS_BUCKET=YOUR_MODELS_BUCKET_NAME,AWS_REGION=us-east-1,SECRET_NAME=riftrewind/riot-api-key}" \
    --region us-east-1
```

### Step 2.4: Test Lambda Function

```bash
# Create test event
cat > /tmp/test-event.json <<EOF
{
  "httpMethod": "POST",
  "path": "/api/player-performance",
  "body": "{\"gameName\":\"Faker\",\"tagLine\":\"KR1\",\"region\":\"KR\"}"
}
EOF

# Test the function
aws lambda invoke \
    --function-name riftrewind-api \
    --payload file:///tmp/test-event.json \
    /tmp/response.json \
    --region us-east-1

# Check the response
cat /tmp/response.json
```

If successful, you should see player performance data!

---

## Part 3: Create API Gateway

### Step 3.1: Create REST API

```bash
# Create API
API_ID=$(aws apigateway create-rest-api \
    --name riftrewind-api \
    --description "RiftRewind Performance Tracker API" \
    --region us-east-1 \
    --query 'id' \
    --output text)

echo "API ID: ${API_ID}"

# Get root resource ID
ROOT_ID=$(aws apigateway get-resources \
    --rest-api-id ${API_ID} \
    --region us-east-1 \
    --query 'items[0].id' \
    --output text)

echo "Root Resource ID: ${ROOT_ID}"
```

### Step 3.2: Create /api Resource

```bash
# Create /api resource
API_RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id ${API_ID} \
    --parent-id ${ROOT_ID} \
    --path-part api \
    --region us-east-1 \
    --query 'id' \
    --output text)

echo "API Resource ID: ${API_RESOURCE_ID}"
```

### Step 3.3: Create /api/player-performance Resource

```bash
# Create /api/player-performance resource
PERFORMANCE_RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id ${API_ID} \
    --parent-id ${API_RESOURCE_ID} \
    --path-part player-performance \
    --region us-east-1 \
    --query 'id' \
    --output text)

echo "Performance Resource ID: ${PERFORMANCE_RESOURCE_ID}"
```

### Step 3.4: Create POST Method

```bash
# Create POST method
aws apigateway put-method \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method POST \
    --authorization-type NONE \
    --region us-east-1

# Create OPTIONS method for CORS
aws apigateway put-method \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS \
    --authorization-type NONE \
    --region us-east-1
```

### Step 3.5: Integrate with Lambda

```bash
# Get Lambda ARN
LAMBDA_ARN=$(aws lambda get-function \
    --function-name riftrewind-api \
    --region us-east-1 \
    --query 'Configuration.FunctionArn' \
    --output text)

# Set up integration
aws apigateway put-integration \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" \
    --region us-east-1

# Set up CORS OPTIONS integration
aws apigateway put-integration \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS \
    --type MOCK \
    --request-templates '{"application/json": "{\"statusCode\": 200}"}' \
    --region us-east-1
```

### Step 3.6: Configure CORS Response

```bash
# Set OPTIONS method response
aws apigateway put-method-response \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters \
        "method.response.header.Access-Control-Allow-Headers=false,method.response.header.Access-Control-Allow-Methods=false,method.response.header.Access-Control-Allow-Origin=false" \
    --region us-east-1

# Set OPTIONS integration response
aws apigateway put-integration-response \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters \
        '{"method.response.header.Access-Control-Allow-Headers":"'"'"'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"'"'","method.response.header.Access-Control-Allow-Methods":"'"'"'POST,OPTIONS'"'"'","method.response.header.Access-Control-Allow-Origin":"'"'"'*'"'"'"}' \
    --region us-east-1
```

### Step 3.7: Grant API Gateway Permission to Invoke Lambda

```bash
aws lambda add-permission \
    --function-name riftrewind-api \
    --statement-id apigateway-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:us-east-1:${ACCOUNT_ID}:${API_ID}/*/*" \
    --region us-east-1
```

### Step 3.8: Deploy API

```bash
# Create deployment
aws apigateway create-deployment \
    --rest-api-id ${API_ID} \
    --stage-name prod \
    --region us-east-1

# Your API Gateway URL is:
API_GATEWAY_URL="https://${API_ID}.execute-api.us-east-1.amazonaws.com/prod"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ API Gateway Deployed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Your API Gateway URL:"
echo "${API_GATEWAY_URL}"
echo ""
echo "Save this URL - you'll need it for the frontend!"
echo ""
```

### Step 3.9: Test API Gateway

```bash
# Test the API
curl -X POST "${API_GATEWAY_URL}/api/player-performance" \
    -H "Content-Type: application/json" \
    -d '{"gameName":"Faker","tagLine":"KR1","region":"KR"}'
```

---

## Part 4: Deploy Frontend to S3

Now that your backend is ready, deploy the frontend:

```bash
# Run the deployment script with your API Gateway URL
export API_GATEWAY_URL="https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod"
./aws/deploy-lambda-frontend.sh
```

The script will:
1. Create an S3 bucket for your website
2. Configure it for static website hosting
3. Update the frontend to use your API Gateway URL
4. Upload all files

---

## 🎉 You're Done!

Your website is now live! The deployment script will show you the URL.

### Access Your Website

Visit: `http://YOUR-BUCKET-NAME.s3-website-us-east-1.amazonaws.com`

---

## Optional: Add HTTPS with CloudFront

For HTTPS support, create a CloudFront distribution:

```bash
# Create CloudFront distribution
aws cloudfront create-distribution \
    --origin-domain-name YOUR-BUCKET-NAME.s3-website-us-east-1.amazonaws.com \
    --default-root-object index.html
```

---

## Troubleshooting

### "API not configured" error on website
- Make sure you ran `deploy-lambda-frontend.sh` with the correct API Gateway URL
- Check `static-website/js/config.js` - it should have your API URL

### CORS errors
- Verify OPTIONS method is configured in API Gateway
- Check that Lambda handler returns CORS headers
- Redeploy API Gateway: `aws apigateway create-deployment --rest-api-id ${API_ID} --stage-name prod`

### Lambda errors
- Check CloudWatch Logs: `aws logs tail /aws/lambda/riftrewind-api --follow`
- Verify environment variables are set correctly
- Check IAM permissions for S3 and Secrets Manager

### "No models found" error
- Verify models are in S3: `aws s3 ls s3://YOUR_BUCKET/models/`
- Check Lambda has permission to read from S3
- Verify MODELS_BUCKET environment variable is correct

---

## Cost Estimate

**Monthly costs for typical usage (1000 requests/month):**

- **Lambda**: ~$0 (free tier: 1M requests/month)
- **API Gateway**: ~$3.50 per million requests ≈ $0.00
- **S3 (website)**: ~$0.50/month
- **S3 (models)**: ~$0.50/month
- **Secrets Manager**: ~$0.40/month
- **Data Transfer**: ~$1/month

**Total: ~$2.40/month** (Much cheaper than EC2!)

---

## Updating Your Application

### Update Lambda Function

```bash
# Update code
cd lambda-package
zip -r ../lambda-function.zip .
cd ..

aws lambda update-function-code \
    --function-name riftrewind-api \
    --zip-file fileb://lambda-function.zip \
    --region us-east-1
```

### Update Frontend

```bash
# Re-run the deployment script
export API_GATEWAY_URL="your_api_gateway_url"
./aws/deploy-lambda-frontend.sh
```

---

## Clean Up (Delete Everything)

```bash
# Delete Lambda function
aws lambda delete-function --function-name riftrewind-api

# Delete API Gateway
aws apigateway delete-rest-api --rest-api-id ${API_ID}

# Delete S3 buckets
aws s3 rb s3://YOUR_WEBSITE_BUCKET --force
aws s3 rb s3://YOUR_MODELS_BUCKET --force

# Delete Secret
aws secretsmanager delete-secret --secret-id riftrewind/riot-api-key --force-delete-without-recovery

# Delete IAM role
aws iam detach-role-policy --role-name riftrewind-lambda-execution-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name riftrewind-lambda-execution-role
```

---

## Summary

You now have:
- ✅ Backend: Lambda function processing requests
- ✅ API: API Gateway exposing HTTP endpoints
- ✅ Frontend: S3 static website
- ✅ Security: Secrets Manager for API keys
- ✅ Models: S3 storage for ML models

**Total setup time**: ~30 minutes
**Monthly cost**: ~$2.40
**Scalability**: Automatic (handles 1 to 1,000,000 requests)
