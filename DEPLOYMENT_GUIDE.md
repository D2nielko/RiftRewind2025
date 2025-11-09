# ML Performance Scoring - Deployment Guide

Complete guide to deploying the ML performance scoring system to AWS Lambda.

---

## Quick Start

### 1. Collect Training Data (2-4 hours)

```bash
cd ml_training
pip install -r requirements.txt

python data_collection.py \
  --api-key YOUR_RIOT_API_KEY \
  --num-matches 5000 \
  --output training_data.json \
  --region na1 \
  --routing americas
```

### 2. Train Models (10-20 minutes)

```bash
python train_models.py \
  --input training_data.json \
  --output-dir models/
```

### 3. Test Models Locally

```bash
python test_models.py --models-dir models/
```

### 4. Upload Models to S3

```bash
# Create S3 bucket
aws s3 mb s3://riftrewind-ml-models

# Upload models
aws s3 sync models/ s3://riftrewind-ml-models/models/
```

### 5. Create Lambda Layer

```bash
# Create layer directory
mkdir -p lambda_layer/python

# Install dependencies
pip install -r lambda_layer_requirements.txt -t lambda_layer/python/

# Create zip
cd lambda_layer
zip -r ml_layer.zip python/

# Upload to AWS
aws lambda publish-layer-version \
  --layer-name riftrewind-ml-layer \
  --description "XGBoost and scikit-learn for performance scoring" \
  --zip-file fileb://ml_layer.zip \
  --compatible-runtimes python3.11 python3.12
```

### 6. Deploy Lambda Function

```bash
# Update Lambda function code
zip -r lambda_function.zip ml-lambda2.py ml_training/

# Upload
aws lambda update-function-code \
  --function-name ml-lambda2 \
  --zip-file fileb://lambda_function.zip

# Add layer (replace LAYER_ARN with output from step 5)
aws lambda update-function-configuration \
  --function-name ml-lambda2 \
  --layers LAYER_ARN

# Set environment variable
aws lambda update-function-configuration \
  --function-name ml-lambda2 \
  --environment Variables={MODEL_BUCKET=riftrewind-ml-models}
```

### 7. Update IAM Role

Add S3 read permissions to Lambda execution role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::riftrewind-ml-models/models/*"
    }
  ]
}
```

---

## Verification

### Test Lambda Function

Create test event:

```json
{
  "bucket": "your-data-bucket",
  "key": "raw-data/player_data.json"
}
```

Expected output should include:

```json
{
  "statusCode": 200,
  "body": {
    "cached": false,
    "reason": "No existing results",
    "matches_analyzed": 10
  }
}
```

Check CloudWatch logs for:
```
Loading performance models from S3...
✅ Performance models loaded
📊 Computing performance scores...
✅ Computed 10 performance scores
```

### Verify S3 Output

Check `analysis/` folder for final results:

```json
{
  "ml_results": {
    "performance_scores": {
      "matches": [
        {
          "match_id": "NA1_123456",
          "champion": "Khazix",
          "role": "JUNGLE",
          "performance_score": 78.5,
          "grade": "B",
          "percentile": 72.8,
          "win": true,
          "kda": 4.88
        }
      ],
      "summary": {
        "avg_score": 72.3,
        "max_score": 85.2,
        "min_score": 58.1,
        "std_score": 8.7,
        "avg_grade": "B"
      }
    }
  }
}
```

---

## Troubleshooting

### Issue: Models not loading

**Symptoms:**
```
Failed to load performance models: NoSuchKey
```

**Solution:**
1. Verify S3 bucket name is correct
2. Check models are in `s3://bucket/models/` directory
3. List bucket contents: `aws s3 ls s3://riftrewind-ml-models/models/`
4. Ensure Lambda role has S3 read permissions

---

### Issue: Import error for performance_predictor

**Symptoms:**
```
ModuleNotFoundError: No module named 'ml_training'
```

**Solution:**
Ensure `ml_training/` directory is included in Lambda deployment:

```bash
zip -r lambda_function.zip ml-lambda2.py ml_training/
```

---

### Issue: XGBoost import error

**Symptoms:**
```
ModuleNotFoundError: No module named 'xgboost'
```

**Solution:**
1. Verify Lambda layer is attached
2. Check layer includes xgboost: `unzip -l ml_layer.zip | grep xgboost`
3. Ensure layer is compatible with Lambda runtime (python3.11)
4. Recreate layer if needed

---

### Issue: Performance scores too low

**Symptoms:**
All scores below 50

**Possible causes:**
1. Models trained on high-elo data (Challenger+)
2. Testing on lower-rank players
3. Insufficient training data

**Solutions:**
- Collect data from multiple ranks
- Adjust performance score formula weights in `train_models.py`
- Retrain with at least 5,000 matches

---

## Updating Models

### When to retrain:
- New game patches change meta
- Quarterly (every 3 months)
- After collecting 10,000+ new matches

### Update process:

```bash
# 1. Collect new data
python data_collection.py \
  --api-key YOUR_KEY \
  --num-matches 5000 \
  --output training_data_new.json

# 2. Merge with old data (optional)
python merge_datasets.py \
  --old training_data_old.json \
  --new training_data_new.json \
  --output training_data_merged.json

# 3. Retrain models
python train_models.py \
  --input training_data_merged.json \
  --output-dir models_v2/

# 4. Test new models
python test_models.py --models-dir models_v2/

# 5. Upload to S3
aws s3 sync models_v2/ s3://riftrewind-ml-models/models/ --delete

# 6. Lambda auto-loads new models on next cold start
```

---

## Monitoring

### CloudWatch Metrics to Track

1. **Model Loading Time**
   - First invocation: 5-10 seconds
   - Warm starts: <100ms

2. **Prediction Success Rate**
   - Should be >95%
   - Check for role mismatches

3. **Average Performance Scores**
   - Expected: 40-70 range
   - Alert if avg <30 or >80

### Custom Metrics

Add to Lambda function:

```python
from aws_embedded_metrics import metric_scope

@metric_scope
def lambda_handler(event, context, metrics):
    # ... existing code ...

    if performance_scores:
        avg_score = np.mean([s['performance_score'] for s in performance_scores['matches']])
        metrics.put_metric('AvgPerformanceScore', avg_score)
        metrics.put_metric('PredictionCount', len(performance_scores['matches']))
```

---

## Cost Optimization

### Lambda Layer Optimization

Current layer size: ~150MB (XGBoost + scikit-learn)

To reduce:
1. Use slim XGBoost build
2. Remove unused sklearn modules
3. Use Lambda container images instead

### Model Storage

- Models: ~50MB total (5 models × 10MB each)
- S3 storage cost: $0.01/month
- S3 requests: ~$0.05/month (assuming 10,000 invocations)

### Lambda Costs

- Memory: 512MB recommended
- Duration: ~2-3 seconds (with models loaded)
- Cost per 10,000 invocations: ~$0.20

---

## Production Checklist

- [ ] Collected 5,000+ training matches
- [ ] Trained models with RMSE <12
- [ ] Tested models locally
- [ ] Uploaded models to S3
- [ ] Created Lambda layer with XGBoost
- [ ] Updated Lambda function code
- [ ] Attached layer to Lambda
- [ ] Set MODEL_BUCKET environment variable
- [ ] Updated IAM permissions
- [ ] Tested Lambda with sample data
- [ ] Verified CloudWatch logs
- [ ] Confirmed S3 output format
- [ ] Set up CloudWatch alarms
- [ ] Documented model version

---

## Support

For issues:
1. Check CloudWatch logs: `/aws/lambda/ml-lambda2`
2. Test locally with `test_models.py`
3. Verify S3 bucket permissions
4. Ensure API key is valid for data collection

Model performance questions:
- Review training metrics in `models/model_metadata.json`
- Check feature importance for unexpected results
- Consider retraining with more data
