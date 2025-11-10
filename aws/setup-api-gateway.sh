#!/bin/bash
# Automated API Gateway Setup for RiftRewind
# This script creates API Gateway and connects it to your Lambda function

set -e

echo "🚀 Setting up API Gateway for RiftRewind"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Configuration
FUNCTION_NAME=${LAMBDA_FUNCTION_NAME:-riftrewind-api}
REGION=${AWS_REGION:-us-east-2}
API_NAME="riftrewind-api"
STAGE_NAME="prod"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS CLI not configured. Run: aws configure"
    exit 1
fi

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account ID: ${ACCOUNT_ID}"
echo "Region: ${REGION}"
echo "Lambda Function: ${FUNCTION_NAME}"
echo ""

# Check if Lambda function exists
echo "Step 1: Verifying Lambda function exists..."
if ! aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} &>/dev/null; then
    echo "❌ Lambda function '${FUNCTION_NAME}' not found!"
    echo "Please deploy your Lambda function first."
    exit 1
fi

LAMBDA_ARN=$(aws lambda get-function \
    --function-name ${FUNCTION_NAME} \
    --region ${REGION} \
    --query 'Configuration.FunctionArn' \
    --output text)

echo "✅ Lambda function found: ${LAMBDA_ARN}"
echo ""

# Create REST API
echo "Step 2: Creating API Gateway REST API..."
API_ID=$(aws apigateway create-rest-api \
    --name ${API_NAME} \
    --description "RiftRewind Performance Tracker API" \
    --endpoint-configuration types=REGIONAL \
    --region ${REGION} \
    --query 'id' \
    --output text)

echo "✅ API created with ID: ${API_ID}"
echo ""

# Get root resource ID
echo "Step 3: Getting root resource..."
ROOT_ID=$(aws apigateway get-resources \
    --rest-api-id ${API_ID} \
    --region ${REGION} \
    --query 'items[0].id' \
    --output text)

echo "✅ Root resource ID: ${ROOT_ID}"
echo ""

# Create /api resource
echo "Step 4: Creating /api resource..."
API_RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id ${API_ID} \
    --parent-id ${ROOT_ID} \
    --path-part api \
    --region ${REGION} \
    --query 'id' \
    --output text)

echo "✅ /api resource created: ${API_RESOURCE_ID}"
echo ""

# Create /api/player-performance resource
echo "Step 5: Creating /api/player-performance resource..."
PERFORMANCE_RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id ${API_ID} \
    --parent-id ${API_RESOURCE_ID} \
    --path-part player-performance \
    --region ${REGION} \
    --query 'id' \
    --output text)

echo "✅ /api/player-performance resource created: ${PERFORMANCE_RESOURCE_ID}"
echo ""

# Create POST method
echo "Step 6: Creating POST method..."
aws apigateway put-method \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method POST \
    --authorization-type NONE \
    --region ${REGION} \
    --no-api-key-required

echo "✅ POST method created"
echo ""

# Create OPTIONS method for CORS
echo "Step 7: Creating OPTIONS method for CORS..."
aws apigateway put-method \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS \
    --authorization-type NONE \
    --region ${REGION} \
    --no-api-key-required

echo "✅ OPTIONS method created"
echo ""

# Integrate POST with Lambda (AWS_PROXY)
echo "Step 8: Integrating POST method with Lambda..."
aws apigateway put-integration \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" \
    --region ${REGION}

echo "✅ Lambda integration configured"
echo ""

# Set up CORS for OPTIONS
echo "Step 9: Configuring CORS..."

# OPTIONS integration (MOCK)
aws apigateway put-integration \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS \
    --type MOCK \
    --request-templates '{"application/json":"{\"statusCode\": 200}"}' \
    --region ${REGION}

# OPTIONS method response
aws apigateway put-method-response \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters \
        "method.response.header.Access-Control-Allow-Headers=false,method.response.header.Access-Control-Allow-Methods=false,method.response.header.Access-Control-Allow-Origin=false" \
    --region ${REGION}

# OPTIONS integration response
aws apigateway put-integration-response \
    --rest-api-id ${API_ID} \
    --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Headers":"'"'"'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"'"'","method.response.header.Access-Control-Allow-Methods":"'"'"'POST,OPTIONS'"'"'","method.response.header.Access-Control-Allow-Origin":"'"'"'*'"'"'"}' \
    --region ${REGION}

echo "✅ CORS configured"
echo ""

# Grant API Gateway permission to invoke Lambda
echo "Step 10: Granting API Gateway permission to invoke Lambda..."

# Remove old permission if exists
aws lambda remove-permission \
    --function-name ${FUNCTION_NAME} \
    --statement-id apigateway-invoke-${API_ID} \
    --region ${REGION} 2>/dev/null || true

# Add new permission
aws lambda add-permission \
    --function-name ${FUNCTION_NAME} \
    --statement-id apigateway-invoke-${API_ID} \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT_ID}:${API_ID}/*/*" \
    --region ${REGION}

echo "✅ Lambda permission granted"
echo ""

# Deploy API to prod stage
echo "Step 11: Deploying API to '${STAGE_NAME}' stage..."
aws apigateway create-deployment \
    --rest-api-id ${API_ID} \
    --stage-name ${STAGE_NAME} \
    --stage-description "Production stage" \
    --description "Initial deployment" \
    --region ${REGION}

echo "✅ API deployed to ${STAGE_NAME} stage"
echo ""

# Construct API Gateway URL
API_GATEWAY_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/${STAGE_NAME}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ API Gateway Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Your API Details:"
echo "   API ID: ${API_ID}"
echo "   Stage: ${STAGE_NAME}"
echo "   Region: ${REGION}"
echo ""
echo "🌐 API Gateway URL:"
echo "   ${API_GATEWAY_URL}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Save to file for easy access
echo "${API_GATEWAY_URL}" > /tmp/api-gateway-url.txt
echo "✅ API Gateway URL saved to: /tmp/api-gateway-url.txt"
echo ""

# Test the API
echo "🧪 Testing API Gateway endpoint..."
echo ""

TEST_RESPONSE=$(curl -s -X POST "${API_GATEWAY_URL}/api/player-performance" \
    -H "Content-Type: application/json" \
    -d '{"gameName":"Faker","tagLine":"KR1","region":"KR"}' \
    -w "\nHTTP_STATUS:%{http_code}" || echo "HTTP_STATUS:000")

HTTP_STATUS=$(echo "$TEST_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$TEST_RESPONSE" | sed '/HTTP_STATUS:/d')

echo "Response Status: ${HTTP_STATUS}"

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ API is working correctly!"
    echo ""
    echo "Sample response:"
    echo "$RESPONSE_BODY" | jq '.' 2>/dev/null || echo "$RESPONSE_BODY"
else
    echo "⚠️  API returned status ${HTTP_STATUS}"
    echo ""
    echo "Response:"
    echo "$RESPONSE_BODY"
    echo ""
    echo "💡 This might be okay if the player doesn't exist."
    echo "   Check CloudWatch logs for details:"
    echo "   aws logs tail /aws/lambda/${FUNCTION_NAME} --follow"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📌 Next Steps:"
echo ""
echo "1. Deploy your frontend with this API URL:"
echo "   export API_GATEWAY_URL=\"${API_GATEWAY_URL}\""
echo "   ./aws/deploy-lambda-frontend.sh"
echo ""
echo "2. Or manually test the API:"
echo "   curl -X POST \"${API_GATEWAY_URL}/api/player-performance\" \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"gameName\":\"BottledCrab\",\"tagLine\":\"NA1\",\"region\":\"NA\"}'"
echo ""
echo "3. View API in AWS Console:"
echo "   https://console.aws.amazon.com/apigateway/main/apis/${API_ID}/stages/${STAGE_NAME}?region=${REGION}"
echo ""
