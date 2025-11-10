#!/bin/bash
# Debug Lambda Function Issues

set -e

echo "🔍 Lambda Debugging Tool"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

FUNCTION_NAME=${1:-riftrewind-api}
REGION=${AWS_REGION:-us-east-1}

echo "Function: ${FUNCTION_NAME}"
echo "Region: ${REGION}"
echo ""

# Check if function exists
echo "Step 1: Checking if Lambda function exists..."
if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} &>/dev/null; then
    echo "✅ Function exists"
else
    echo "❌ Function not found!"
    exit 1
fi

# Get function configuration
echo ""
echo "Step 2: Checking function configuration..."
aws lambda get-function-configuration \
    --function-name ${FUNCTION_NAME} \
    --region ${REGION} \
    --query '{Runtime:Runtime,Handler:Handler,Timeout:Timeout,Memory:MemorySize,LastModified:LastModified}' \
    --output table

# Check environment variables
echo ""
echo "Step 3: Checking environment variables..."
ENV_VARS=$(aws lambda get-function-configuration \
    --function-name ${FUNCTION_NAME} \
    --region ${REGION} \
    --query 'Environment.Variables' \
    --output json)

echo "$ENV_VARS" | jq .

# Check for required variables
echo ""
echo "Validating required environment variables..."
MODELS_BUCKET=$(echo "$ENV_VARS" | jq -r '.MODELS_BUCKET // empty')
SECRET_NAME=$(echo "$ENV_VARS" | jq -r '.SECRET_NAME // empty')
AWS_REGION_VAR=$(echo "$ENV_VARS" | jq -r '.AWS_REGION // empty')

if [ -z "$MODELS_BUCKET" ]; then
    echo "⚠️  WARNING: MODELS_BUCKET not set!"
else
    echo "✅ MODELS_BUCKET: ${MODELS_BUCKET}"
fi

if [ -z "$SECRET_NAME" ]; then
    echo "⚠️  WARNING: SECRET_NAME not set!"
else
    echo "✅ SECRET_NAME: ${SECRET_NAME}"
fi

# Check CloudWatch Logs
echo ""
echo "Step 4: Fetching recent CloudWatch Logs..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"

# Get most recent log stream
LOG_STREAM=$(aws logs describe-log-streams \
    --log-group-name ${LOG_GROUP} \
    --order-by LastEventTime \
    --descending \
    --max-items 1 \
    --region ${REGION} \
    --query 'logStreams[0].logStreamName' \
    --output text 2>/dev/null || echo "")

if [ -z "$LOG_STREAM" ] || [ "$LOG_STREAM" == "None" ]; then
    echo "⚠️  No logs found yet. Try invoking the function first."
else
    echo "Latest log stream: ${LOG_STREAM}"
    echo ""
    echo "Last 50 log entries:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    aws logs get-log-events \
        --log-group-name ${LOG_GROUP} \
        --log-stream-name "${LOG_STREAM}" \
        --limit 50 \
        --region ${REGION} \
        --query 'events[*].message' \
        --output text
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 To view logs in real-time, run:"
echo "   aws logs tail /aws/lambda/${FUNCTION_NAME} --follow --region ${REGION}"
echo ""
echo "💡 To test the function directly, run:"
echo "   ./aws/test-lambda.sh"
echo ""
