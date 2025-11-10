# Complete RiftRewind Setup Guide - Start to Finish

This guide walks you through setting up RiftRewind from scratch using Lambda + API Gateway + S3.

## ✅ What You Already Have

Based on your setup, you should have:
- ✅ Lambda function deployed
- ✅ ML models in S3
- ✅ Riot API key in Secrets Manager

## 🎯 What We're Going to Do

1. Create API Gateway and connect it to Lambda (automated!)
2. Test the API
3. Deploy the frontend to S3
4. Access your website

**Time required**: ~10 minutes

---

## Step 1: Create API Gateway (Automated)

Run this single command - it does everything for you:

```bash
./aws/setup-api-gateway.sh
```

**What this script does:**
1. ✅ Creates API Gateway REST API
2. ✅ Creates `/api/player-performance` endpoint
3. ✅ Connects it to your Lambda function
4. ✅ Configures CORS (fixes browser errors)
5. ✅ Deploys to `prod` stage
6. ✅ Tests the API
7. ✅ Shows you the API Gateway URL

**Expected output:**
```
✅ API Gateway Setup Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🌐 API Gateway URL:
   https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod
```

**Save that URL!** You'll need it in the next step.

---

## Step 2: Test Your API

The script tests it automatically, but you can also test manually:

```bash
# Replace with your actual API Gateway URL
API_URL="https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod"

curl -X POST "${API_URL}/api/player-performance" \
    -H "Content-Type: application/json" \
    -d '{"gameName":"BottledCrab","tagLine":"NA1","region":"NA"}'
```

**Expected result:**
- If successful: JSON with player performance data
- If error: Check Step 4 (Troubleshooting) below

---

## Step 3: Deploy Frontend to S3

Now deploy your website using the API Gateway URL from Step 1:

```bash
# Use your API Gateway URL from Step 1
export API_GATEWAY_URL="https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod"

# Deploy frontend
./aws/deploy-lambda-frontend.sh
```

**What this script does:**
1. ✅ Creates S3 bucket for static website
2. ✅ Configures bucket for public web hosting
3. ✅ Updates frontend with your API Gateway URL
4. ✅ Uploads HTML/CSS/JS files
5. ✅ Shows you the website URL

**Expected output:**
```
✅ Deployment Complete!

🌐 Your website is now live at:
   http://riftrewind-web-123456.s3-website-us-east-1.amazonaws.com
```

---

## Step 4: Access Your Website

Visit the URL from Step 3!

Example: `http://riftrewind-web-123456.s3-website-us-east-1.amazonaws.com`

You should see the RiftRewind homepage where you can:
1. Enter a player's game name
2. Enter their tagline
3. Select region
4. Click "Analyze Performance"

---

## 🐛 Troubleshooting

### Issue: API returns 500 Internal Server Error

**Check Lambda logs:**
```bash
aws logs tail /aws/lambda/riftrewind-api --follow
```

**Common causes:**
1. **Missing environment variables** in Lambda
   - Required: `MODELS_BUCKET`, `SECRET_NAME`, `AWS_REGION`
   - Fix: Update Lambda environment variables in AWS Console

2. **Missing Lambda layer** (dependencies not installed)
   - Check: Lambda function has a layer attached
   - Fix: See LAMBDA_DEPLOYMENT_GUIDE.md Step 2.2

3. **IAM permissions** missing
   - Lambda needs permission to read S3 (models) and Secrets Manager (API key)
   - Fix: Check Lambda execution role has RiftRewindTaskPolicy attached

**Debug Lambda:**
```bash
./aws/debug-lambda.sh
```

This shows:
- Lambda configuration
- Environment variables
- Recent error logs

---

### Issue: Frontend shows "API not configured"

**Cause**: Frontend wasn't deployed with API Gateway URL

**Fix**: Re-run frontend deployment with correct URL:
```bash
export API_GATEWAY_URL="https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod"
./aws/deploy-lambda-frontend.sh
```

---

### Issue: CORS errors in browser console

**Symptoms**:
```
Access to fetch has been blocked by CORS policy
```

**Fix**: Re-run the API Gateway setup (it configures CORS automatically):
```bash
./aws/setup-api-gateway.sh
```

---

### Issue: "Player not found" errors

**Possible causes:**
1. **Wrong region** - Make sure player region matches
2. **Riot API key expired** - Generate new key at https://developer.riotgames.com
3. **Incorrect tagline** - Taglines are case-sensitive

**Update Riot API key:**
```bash
aws secretsmanager update-secret \
    --secret-id riftrewind/riot-api-key \
    --secret-string '{"RIOT_API_KEY":"your_new_key_here"}'
```

---

### Issue: Lambda timeout

**Symptoms**: Request takes too long and times out

**Fix**: Increase Lambda timeout:
```bash
aws lambda update-function-configuration \
    --function-name riftrewind-api \
    --timeout 60
```

---

## 📋 Quick Reference Commands

### View API Gateway URL
```bash
# Your URL is saved here after running setup
cat /tmp/api-gateway-url.txt
```

### View Lambda logs
```bash
aws logs tail /aws/lambda/riftrewind-api --follow
```

### Test Lambda directly (bypass API Gateway)
```bash
./aws/test-lambda.sh
```

### Debug Lambda issues
```bash
./aws/debug-lambda.sh
```

### Update Lambda code
```bash
# After changing lambda_handler.py
cd lambda-package
zip -r ../lambda-function.zip .
cd ..

aws lambda update-function-code \
    --function-name riftrewind-api \
    --zip-file fileb://lambda-function.zip
```

### Delete and recreate API Gateway
```bash
# Get your API ID
aws apigateway get-rest-apis

# Delete it
aws apigateway delete-rest-api --rest-api-id YOUR_API_ID

# Recreate it
./aws/setup-api-gateway.sh
```

---

## 🎉 Success Checklist

- [ ] API Gateway created and shows URL
- [ ] API Gateway test returns data (not 500 error)
- [ ] Frontend deployed to S3
- [ ] Website loads in browser
- [ ] Can search for a player
- [ ] Results page shows performance data

---

## 💰 Cost Breakdown

For **1,000 requests/month**:
- Lambda: $0 (free tier)
- API Gateway: $0.00 (free tier)
- S3 (website): $0.50
- S3 (models): $0.50
- Secrets Manager: $0.40
- Data transfer: $1.00

**Total: ~$2.40/month**

---

## 🔗 Useful Links

- **AWS Lambda Console**: https://console.aws.amazon.com/lambda
- **API Gateway Console**: https://console.aws.amazon.com/apigateway
- **S3 Console**: https://console.aws.amazon.com/s3
- **CloudWatch Logs**: https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups/log-group/$252Faws$252Flambda$252Friftrewind-api
- **Riot Developer Portal**: https://developer.riotgames.com

---

## 📞 Need More Help?

1. Check **LAMBDA_DEPLOYMENT_GUIDE.md** for detailed explanations
2. Run **./aws/debug-lambda.sh** to diagnose Lambda issues
3. Check CloudWatch logs for error messages
4. Verify all environment variables are set correctly

---

## Summary

You just deployed a **fully serverless** application:

```
Browser → S3 (Frontend) → API Gateway → Lambda → Riot API
                                        ↓
                                    S3 (Models)
                                        ↓
                                Secrets Manager
```

- **No servers to manage**
- **Auto-scaling** (handles 1 to 1,000,000 requests)
- **Pay only for what you use**
- **Highly available** across multiple data centers

Enjoy your RiftRewind deployment! 🎮
