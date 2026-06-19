# Deployment Guide — Lambda + API Gateway + S3

Deploy RiftRewind as a serverless app: a Flask backend on AWS Lambda (via Mangum)
behind API Gateway, with ML models in S3, the Riot API key in Secrets Manager, and a
static frontend on S3.

```
┌──────────┐     ┌──────────────┐     ┌─────────────┐
│ Browser  │────>│  S3 Website  │────>│ API Gateway │
└──────────┘     │  (Frontend)  │     └──────┬──────┘
                 └──────────────┘            │
                                             v
                                      ┌─────────────┐
                                      │   Lambda    │
                                      │  (Backend)  │
                                      └──────┬──────┘
                  ┌──────────────────────────┼───────────────────┐
                  v                          v                    v
          ┌──────────────┐         ┌──────────────┐     ┌────────────┐
          │ S3 (Models)  │         │   Secrets    │     │  Riot API  │
          └──────────────┘         │   Manager    │     └────────────┘
                                   └──────────────┘
```

## Prerequisites

- AWS account with the CLI configured (`aws configure`)
- A Riot Games API key
- ~30 minutes

---

## Quick Start

```bash
# 1. Create S3 bucket for models, upload models, store API key, create IAM policy
./aws/setup-aws-resources.sh          # save the bucket name it prints

# 2. Create the Lambda function + API Gateway (see Parts 2–3 below)

# 3. Deploy the static frontend (uses the API Gateway URL from Part 3)
export API_GATEWAY_URL="https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod"
./aws/deploy-lambda-frontend.sh       # prints your website URL
```

---

## Part 1: One-time AWS resource setup

```bash
./aws/setup-aws-resources.sh
```

This creates an S3 bucket for the ML models, uploads them, stores the Riot API key in
Secrets Manager, and creates the IAM policy. **Save the bucket name.**

---

## Part 2: Deploy the Lambda function

### 2.1 Create the execution role

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > /tmp/lambda-trust-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Principal": { "Service": "lambda.amazonaws.com" }, "Action": "sts:AssumeRole" }
  ]
}
EOF

aws iam create-role \
    --role-name riftrewind-lambda-execution-role \
    --assume-role-policy-document file:///tmp/lambda-trust-policy.json

aws iam attach-role-policy \
    --role-name riftrewind-lambda-execution-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam attach-role-policy \
    --role-name riftrewind-lambda-execution-role \
    --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/RiftRewindTaskPolicy
```

### 2.2 Build a Lambda layer for dependencies

The ML libraries are too large for a direct upload, so package them as a layer:

```bash
mkdir -p lambda-layers/python

pip install \
    --platform manylinux2014_x86_64 \
    --target lambda-layers/python \
    --implementation cp \
    --python-version 3.11 \
    --only-binary=:all: \
    flask mangum requests numpy scikit-learn xgboost boto3

cd lambda-layers && zip -r ../lambda-layer.zip python/ && cd ..

aws lambda publish-layer-version \
    --layer-name riftrewind-dependencies \
    --description "Dependencies for RiftRewind (flask, mangum, numpy, sklearn, xgboost, requests, boto3)" \
    --zip-file fileb://lambda-layer.zip \
    --compatible-runtimes python3.11 \
    --region us-east-1
```

Save the `LayerVersionArn` from the output (e.g.
`arn:aws:lambda:us-east-1:123456789:layer:riftrewind-dependencies:1`).

> Note: `lambda-layer.zip` and the `lambda-layers/` build directory are gitignored —
> they are build artifacts, regenerated from `lambda_layer_requirements.txt`.

### 2.3 Package and deploy the function

The Lambda entry point is `lambda_function.lambda_handler`, which calls the Mangum
`handler` exported from `app.py`.

```bash
mkdir -p lambda-package
cp app.py lambda_function.py lambda-package/
cp -r ml_training lambda-package/
cd lambda-package && zip -r ../lambda-function.zip . && cd ..

# Replace LAYER_ARN (from 2.2) and YOUR_MODELS_BUCKET (from Part 1)
aws lambda create-function \
    --function-name riftrewind-api \
    --runtime python3.11 \
    --role arn:aws:iam::${ACCOUNT_ID}:role/riftrewind-lambda-execution-role \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://lambda-function.zip \
    --timeout 60 \
    --memory-size 1024 \
    --layers LAYER_ARN \
    --environment "Variables={MODELS_BUCKET=YOUR_MODELS_BUCKET,AWS_REGION=us-east-1,SECRET_NAME=riftrewind/riot-api-key}" \
    --region us-east-1
```

### 2.4 Test the function

```bash
cat > /tmp/test-event.json <<'EOF'
{ "httpMethod": "POST", "path": "/api/player-performance",
  "body": "{\"gameName\":\"Faker\",\"tagLine\":\"KR1\",\"region\":\"KR\"}" }
EOF

aws lambda invoke \
    --function-name riftrewind-api \
    --payload file:///tmp/test-event.json \
    /tmp/response.json --region us-east-1

cat /tmp/response.json
```

---

## Part 3: Create the API Gateway

### 3.1 Create the REST API

```bash
API_ID=$(aws apigateway create-rest-api \
    --name riftrewind-api --description "RiftRewind Performance Tracker API" \
    --region us-east-1 --query 'id' --output text)
echo "API ID: ${API_ID}"

ROOT_ID=$(aws apigateway get-resources --rest-api-id ${API_ID} \
    --region us-east-1 --query 'items[0].id' --output text)
```

### 3.2 Create `/api/player-performance`

```bash
API_RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id ${API_ID} --parent-id ${ROOT_ID} --path-part api \
    --region us-east-1 --query 'id' --output text)

PERFORMANCE_RESOURCE_ID=$(aws apigateway create-resource \
    --rest-api-id ${API_ID} --parent-id ${API_RESOURCE_ID} --path-part player-performance \
    --region us-east-1 --query 'id' --output text)
```

### 3.3 Create POST + OPTIONS methods

```bash
aws apigateway put-method --rest-api-id ${API_ID} --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method POST --authorization-type NONE --region us-east-1

aws apigateway put-method --rest-api-id ${API_ID} --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS --authorization-type NONE --region us-east-1
```

### 3.4 Integrate with Lambda (proxy) + CORS

```bash
LAMBDA_ARN=$(aws lambda get-function --function-name riftrewind-api \
    --region us-east-1 --query 'Configuration.FunctionArn' --output text)

aws apigateway put-integration --rest-api-id ${API_ID} --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method POST --type AWS_PROXY --integration-http-method POST \
    --uri "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations" \
    --region us-east-1

aws apigateway put-integration --rest-api-id ${API_ID} --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS --type MOCK \
    --request-templates '{"application/json": "{\"statusCode\": 200}"}' --region us-east-1

aws apigateway put-method-response --rest-api-id ${API_ID} --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS --status-code 200 \
    --response-parameters "method.response.header.Access-Control-Allow-Headers=false,method.response.header.Access-Control-Allow-Methods=false,method.response.header.Access-Control-Allow-Origin=false" \
    --region us-east-1

aws apigateway put-integration-response --rest-api-id ${API_ID} --resource-id ${PERFORMANCE_RESOURCE_ID} \
    --http-method OPTIONS --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Headers":"'"'"'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"'"'","method.response.header.Access-Control-Allow-Methods":"'"'"'POST,OPTIONS'"'"'","method.response.header.Access-Control-Allow-Origin":"'"'"'*'"'"'"}' \
    --region us-east-1
```

### 3.5 Grant invoke permission and deploy

```bash
aws lambda add-permission --function-name riftrewind-api \
    --statement-id apigateway-invoke --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:us-east-1:${ACCOUNT_ID}:${API_ID}/*/*" --region us-east-1

aws apigateway create-deployment --rest-api-id ${API_ID} --stage-name prod --region us-east-1

API_GATEWAY_URL="https://${API_ID}.execute-api.us-east-1.amazonaws.com/prod"
echo "API Gateway URL: ${API_GATEWAY_URL}"   # save this for the frontend
```

### 3.6 Test the endpoint

```bash
curl -X POST "${API_GATEWAY_URL}/api/player-performance" \
    -H "Content-Type: application/json" \
    -d '{"gameName":"Faker","tagLine":"KR1","region":"KR"}'
```

---

## Part 4: Deploy the frontend to S3

```bash
export API_GATEWAY_URL="https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod"
./aws/deploy-lambda-frontend.sh
```

The script creates an S3 website bucket, writes the API URL into
`static-website/js/config.js`, uploads the files, and prints the website URL
(`http://YOUR-BUCKET.s3-website-us-east-1.amazonaws.com`).

### Optional: HTTPS with CloudFront

```bash
aws cloudfront create-distribution \
    --origin-domain-name YOUR-BUCKET.s3-website-us-east-1.amazonaws.com \
    --default-root-object index.html
```

---

## Updating

```bash
# Backend
cd lambda-package && zip -r ../lambda-function.zip . && cd ..
aws lambda update-function-code --function-name riftrewind-api \
    --zip-file fileb://lambda-function.zip --region us-east-1

# Frontend
export API_GATEWAY_URL="your_api_gateway_url"
./aws/deploy-lambda-frontend.sh
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Website shows "API not configured" | Re-run `deploy-lambda-frontend.sh` with the correct `API_GATEWAY_URL`; check `static-website/js/config.js` |
| CORS errors | Ensure the OPTIONS method exists, the handler returns CORS headers, and the API was redeployed |
| Lambda errors | `aws logs tail /aws/lambda/riftrewind-api --follow`; verify env vars and IAM permissions |
| "No models found" | `aws s3 ls s3://YOUR_BUCKET/models/`; check `MODELS_BUCKET` and S3 read permissions |

---

## Cost (typical, ~1,000 requests/month)

| Service | Cost |
|---|---|
| Lambda | ~$0 (free tier) |
| API Gateway | ~$0 |
| S3 (website + models) | ~$1 |
| Secrets Manager | ~$0.40 |
| Data transfer | ~$1 |
| **Total** | **~$2.40/month** |

---

## Clean up

```bash
aws lambda delete-function --function-name riftrewind-api
aws apigateway delete-rest-api --rest-api-id ${API_ID}
aws s3 rb s3://YOUR_WEBSITE_BUCKET --force
aws s3 rb s3://YOUR_MODELS_BUCKET --force
aws secretsmanager delete-secret --secret-id riftrewind/riot-api-key --force-delete-without-recovery
aws iam detach-role-policy --role-name riftrewind-lambda-execution-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name riftrewind-lambda-execution-role
```
