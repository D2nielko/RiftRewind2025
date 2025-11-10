#!/bin/bash
# Test Lambda function directly (bypassing API Gateway)

set -e

FUNCTION_NAME=${1:-riftrewind-api}
REGION=${AWS_REGION:-us-east-1}

echo "🧪 Testing Lambda Function: ${FUNCTION_NAME}"
echo ""

# Create test event
cat > /tmp/lambda-test-event.json <<'EOF'
{
  "httpMethod": "POST",
  "path": "/api/player-performance",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": "{\"gameName\":\"BottledCrab\",\"tagLine\":\"NA1\",\"region\":\"NA\"}"
}
EOF

echo "Test payload:"
cat /tmp/lambda-test-event.json | jq .
echo ""
echo "Invoking Lambda function..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Invoke function
aws lambda invoke \
    --function-name ${FUNCTION_NAME} \
    --payload file:///tmp/lambda-test-event.json \
    --cli-binary-format raw-in-base64-out \
    --region ${REGION} \
    /tmp/lambda-response.json

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Response:"
cat /tmp/lambda-response.json | jq .

echo ""
echo ""
echo "Response status code:"
cat /tmp/lambda-response.json | jq -r '.statusCode // "No status code"'

# Check if there's an error
ERROR=$(cat /tmp/lambda-response.json | jq -r '.body' | jq -r '.error // empty' 2>/dev/null || echo "")

if [ ! -z "$ERROR" ]; then
    echo ""
    echo "❌ Error found: ${ERROR}"
fi

# Clean up
rm /tmp/lambda-test-event.json /tmp/lambda-response.json 2>/dev/null || true

echo ""
echo "💡 To see detailed logs, run:"
echo "   ./aws/debug-lambda.sh"
echo ""
