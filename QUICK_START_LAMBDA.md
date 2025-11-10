# Quick Start: Lambda Deployment

Fastest way to get RiftRewind running on AWS Lambda + API Gateway.

## Prerequisites

- AWS CLI configured: `aws configure`
- Riot API Key
- 30 minutes

---

## Step 1: Setup AWS Resources (5 min)

```bash
./aws/setup-aws-resources.sh
```

**Save the output!** You'll need the S3 bucket name.

---

## Step 2: Get Your API Gateway URL (20 min)

You need to create:
1. Lambda function
2. API Gateway
3. Connect them

Follow the detailed guide:
```bash
cat LAMBDA_DEPLOYMENT_GUIDE.md
```

Or use AWS Console:
1. Go to AWS Lambda Console
2. Create function → Upload `lambda_handler.py`
3. Create API Gateway (REST API)
4. Add POST method to `/api/player-performance`
5. Deploy to stage `prod`
6. **Copy the Invoke URL** - this is your API Gateway URL

Example URL: `https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod`

---

## Step 3: Deploy Frontend (5 min)

```bash
export API_GATEWAY_URL="https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod"
./aws/deploy-lambda-frontend.sh
```

The script will output your website URL!

---

## Done! 🎉

Visit your website URL (from Step 3 output).

---

## Troubleshooting

### "Where do I get the API Gateway URL?"

After creating API Gateway and deploying it:

**CLI:**
```bash
# If you saved the API ID
aws apigateway get-rest-apis

# Your URL format:
https://{API_ID}.execute-api.{REGION}.amazonaws.com/prod
```

**Console:**
1. Go to API Gateway Console
2. Click your API
3. Click "Stages" → "prod"
4. See "Invoke URL" at top

### "Frontend shows 'API not configured'"

You need to run the deployment script with your API Gateway URL:

```bash
export API_GATEWAY_URL="your_url_here"
./aws/deploy-lambda-frontend.sh
```

### "CORS errors in browser"

Make sure:
1. OPTIONS method exists in API Gateway
2. Lambda handler returns CORS headers
3. API Gateway is redeployed after CORS changes

---

## Cost

**~$2-5/month** for typical usage (1000-10000 requests/month)

Much cheaper than running EC2 24/7!

---

## Next Steps

- Set up CloudFront for HTTPS
- Add custom domain with Route 53
- Set up CloudWatch alarms
- Enable API caching

See `LAMBDA_DEPLOYMENT_GUIDE.md` for details.
