# AWS Deployment Guide for RiftRewind

This guide covers multiple methods to deploy your RiftRewind League of Legends Performance Tracker to AWS.

## Architecture Options

### Option 1: AWS Elastic Beanstalk (Recommended for beginners)
**Best for**: Quick deployment, automatic scaling, managed infrastructure

**Architecture**:
- Elastic Beanstalk (Flask app)
- S3 (ML models storage)
- Secrets Manager (Riot API key)
- CloudFront (optional, for CDN)

**Pros**: Easy to deploy, auto-scaling, load balancing included
**Cons**: Less control, potentially higher cost for low traffic

---

### Option 2: AWS Lambda + API Gateway (Serverless)
**Best for**: Cost efficiency, automatic scaling, pay-per-use

**Architecture**:
- Lambda Functions (API endpoints)
- API Gateway (HTTP endpoints)
- S3 (Static website + ML models)
- Secrets Manager (Riot API key)
- CloudFront (Static content delivery)

**Pros**: Very cost-effective, infinite scaling, no server management
**Cons**: Cold start latency, complexity with large ML models

---

### Option 3: EC2 with Application Load Balancer
**Best for**: Full control, custom configurations

**Architecture**:
- EC2 instances (Flask app)
- Application Load Balancer
- S3 (ML models)
- Secrets Manager (Riot API key)
- Auto Scaling Group

**Pros**: Full control, flexible
**Cons**: More management overhead, need to configure scaling

---

### Option 4: ECS Fargate (Containerized)
**Best for**: Modern deployments, scalability

**Architecture**:
- ECS Fargate (Docker containers)
- Application Load Balancer
- ECR (Container registry)
- S3 (ML models)
- Secrets Manager (Riot API key)

**Pros**: Modern, scalable, no server management
**Cons**: Requires Docker knowledge

---

## Detailed Deployment Instructions

## 🚀 Option 1: AWS Elastic Beanstalk (Recommended)

### Prerequisites
- AWS Account
- AWS CLI installed and configured
- EB CLI installed: `pip install awsebcli`

### Step 1: Prepare Your Application

The application is already prepared with the necessary files.

### Step 2: Configure AWS Secrets Manager

Store your Riot API key securely:

```bash
# Create secret for Riot API key
aws secretsmanager create-secret \
    --name riftrewind/riot-api-key \
    --description "Riot Games API Key for RiftRewind" \
    --secret-string '{"RIOT_API_KEY":"your_api_key_here"}' \
    --region us-east-1
```

### Step 3: Upload ML Models to S3

```bash
# Create S3 bucket for models
aws s3 mb s3://riftrewind-models-YOUR_UNIQUE_ID --region us-east-1

# Upload models
aws s3 sync ml_training/models/ s3://riftrewind-models-YOUR_UNIQUE_ID/models/
```

### Step 4: Initialize Elastic Beanstalk

```bash
# Initialize EB in your project directory
eb init -p python-3.11 riftrewind --region us-east-1

# Create environment
eb create riftrewind-prod \
    --instance-type t3.medium \
    --envvars MODELS_BUCKET=riftrewind-models-YOUR_UNIQUE_ID
```

### Step 5: Configure Environment Variables

```bash
# Set environment variables
eb setenv \
    MODELS_BUCKET=riftrewind-models-YOUR_UNIQUE_ID \
    AWS_REGION=us-east-1 \
    SECRET_NAME=riftrewind/riot-api-key
```

### Step 6: Deploy

```bash
# Deploy application
eb deploy

# Open in browser
eb open
```

### Step 7: Configure IAM Permissions

Your EB instance needs permissions to:
- Read from S3 (models)
- Read from Secrets Manager (API key)

Add this policy to the EB instance role:

```json
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
        "arn:aws:s3:::riftrewind-models-YOUR_UNIQUE_ID",
        "arn:aws:s3:::riftrewind-models-YOUR_UNIQUE_ID/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:riftrewind/riot-api-key-*"
    }
  ]
}
```

---

## 🔧 Option 2: AWS Lambda + API Gateway (Serverless)

### Step 1: Create Lambda Layer for Dependencies

```bash
# Create layer directory
mkdir -p lambda-layer/python

# Install dependencies
pip install -r requirements.txt -t lambda-layer/python/

# Create layer zip
cd lambda-layer
zip -r flask-layer.zip python/
cd ..

# Upload to AWS
aws lambda publish-layer-version \
    --layer-name riftrewind-dependencies \
    --zip-file fileb://lambda-layer/flask-layer.zip \
    --compatible-runtimes python3.11 \
    --region us-east-1
```

### Step 2: Upload ML Models to S3

```bash
# Create bucket and upload models
aws s3 mb s3://riftrewind-models-YOUR_UNIQUE_ID --region us-east-1
aws s3 sync ml_training/models/ s3://riftrewind-models-YOUR_UNIQUE_ID/models/
```

### Step 3: Create Lambda Function

```bash
# Package application
zip -r app.zip app.py ml_training/

# Create Lambda function
aws lambda create-function \
    --function-name riftrewind-api \
    --runtime python3.11 \
    --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-execution-role \
    --handler lambda_handler.handler \
    --zip-file fileb://app.zip \
    --timeout 30 \
    --memory-size 1024 \
    --environment Variables="{MODELS_BUCKET=riftrewind-models-YOUR_UNIQUE_ID}" \
    --region us-east-1
```

### Step 4: Create API Gateway

```bash
# Create REST API
aws apigateway create-rest-api \
    --name riftrewind-api \
    --description "RiftRewind Performance Tracker API" \
    --region us-east-1
```

### Step 5: Deploy Static Frontend to S3 + CloudFront

```bash
# Create S3 bucket for website
aws s3 mb s3://riftrewind-web-YOUR_UNIQUE_ID --region us-east-1

# Configure as static website
aws s3 website s3://riftrewind-web-YOUR_UNIQUE_ID/ \
    --index-document index.html \
    --error-document index.html

# Upload static files
aws s3 sync templates/ s3://riftrewind-web-YOUR_UNIQUE_ID/ \
    --exclude "*.py"
aws s3 sync static/ s3://riftrewind-web-YOUR_UNIQUE_ID/static/
```

---

## 🖥️ Option 3: EC2 Deployment

### Step 1: Launch EC2 Instance

```bash
# Launch Ubuntu instance
aws ec2 run-instances \
    --image-id ami-0c7217cdde317cfec \
    --instance-type t3.medium \
    --key-name YOUR_KEY_PAIR \
    --security-group-ids sg-YOUR_SG_ID \
    --subnet-id subnet-YOUR_SUBNET_ID \
    --region us-east-1 \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=riftrewind-web}]'
```

### Step 2: Connect and Setup

```bash
# SSH into instance
ssh -i your-key.pem ubuntu@YOUR_INSTANCE_IP

# Install dependencies
sudo apt update
sudo apt install -y python3-pip nginx

# Clone your repository
git clone https://github.com/YOUR_USERNAME/RiftRewind2025.git
cd RiftRewind2025

# Install Python dependencies
pip3 install -r requirements.txt

# Install AWS CLI and download models
pip3 install awscli
aws s3 sync s3://riftrewind-models-YOUR_UNIQUE_ID/models/ ml_training/models/

# Get Riot API key from Secrets Manager
export RIOT_API_KEY=$(aws secretsmanager get-secret-value \
    --secret-id riftrewind/riot-api-key \
    --query SecretString \
    --output text | jq -r .RIOT_API_KEY)
```

### Step 3: Configure Gunicorn and Nginx

```bash
# Install Gunicorn
pip3 install gunicorn

# Create systemd service
sudo nano /etc/systemd/system/riftrewind.service
```

Add this content:

```ini
[Unit]
Description=RiftRewind Flask Application
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/RiftRewind2025
Environment="RIOT_API_KEY=YOUR_KEY"
ExecStart=/usr/local/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

Configure Nginx:

```bash
sudo nano /etc/nginx/sites-available/riftrewind
```

Add:

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static {
        alias /home/ubuntu/RiftRewind2025/static;
    }
}
```

Enable and start:

```bash
sudo ln -s /etc/nginx/sites-available/riftrewind /etc/nginx/sites-enabled/
sudo systemctl restart nginx
sudo systemctl start riftrewind
sudo systemctl enable riftrewind
```

---

## 🐳 Option 4: ECS Fargate (Docker)

This option uses the Dockerfile we'll create.

### Step 1: Build and Push Docker Image

```bash
# Build image
docker build -t riftrewind .

# Tag for ECR
docker tag riftrewind:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/riftrewind:latest

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin \
    YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Create ECR repository
aws ecr create-repository --repository-name riftrewind --region us-east-1

# Push image
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/riftrewind:latest
```

### Step 2: Create ECS Cluster and Service

```bash
# Create cluster
aws ecs create-cluster --cluster-name riftrewind-cluster --region us-east-1

# Create task definition (see task-definition.json)
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create service
aws ecs create-service \
    --cluster riftrewind-cluster \
    --service-name riftrewind-service \
    --task-definition riftrewind-task \
    --desired-count 2 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --region us-east-1
```

---

## Cost Estimates

### Elastic Beanstalk (t3.medium)
- **EC2**: ~$30/month
- **Load Balancer**: ~$16/month
- **S3**: <$1/month
- **Total**: ~$47/month

### Lambda + API Gateway
- **Lambda**: ~$0 (free tier) to $5/month
- **API Gateway**: ~$3.50 per million requests
- **S3**: <$1/month
- **Total**: ~$1-10/month (depending on traffic)

### EC2 (t3.medium)
- **EC2**: ~$30/month
- **S3**: <$1/month
- **Total**: ~$31/month

### ECS Fargate
- **Fargate**: ~$30-50/month
- **Load Balancer**: ~$16/month
- **S3**: <$1/month
- **Total**: ~$47-67/month

---

## Security Best Practices

1. **Never commit API keys** - Use AWS Secrets Manager or Parameter Store
2. **Use IAM roles** - Attach roles to EC2/Lambda instead of access keys
3. **Enable HTTPS** - Use ACM (AWS Certificate Manager) for SSL/TLS
4. **Restrict Security Groups** - Only allow necessary ports (80, 443)
5. **Enable CloudWatch Logs** - Monitor application logs
6. **Set up CloudWatch Alarms** - Alert on errors or high usage
7. **Use VPC** - Deploy in private subnets when possible
8. **Enable WAF** - Protect against common web exploits

---

## Monitoring and Logging

### CloudWatch Logs

```bash
# View logs for Elastic Beanstalk
eb logs

# View logs for Lambda
aws logs tail /aws/lambda/riftrewind-api --follow
```

### CloudWatch Metrics

Set up alarms for:
- CPU utilization > 80%
- Memory utilization > 80%
- 5xx errors
- Request latency > 2s

---

## CI/CD Pipeline (Optional)

Use AWS CodePipeline for automated deployments:

1. **Source**: GitHub
2. **Build**: CodeBuild (run tests)
3. **Deploy**: Elastic Beanstalk / ECS / Lambda

---

## Next Steps

1. Choose your deployment option
2. Follow the detailed steps above
3. Configure monitoring and alerts
4. Set up a custom domain with Route 53
5. Enable HTTPS with ACM
6. Implement caching with CloudFront

---

## Troubleshooting

### Models not loading
- Check S3 bucket permissions
- Verify IAM role has S3 read access
- Check environment variable for bucket name

### API key not found
- Verify Secrets Manager secret exists
- Check IAM role has secretsmanager:GetSecretValue permission
- Verify region matches

### High latency
- Use CloudFront for static assets
- Increase instance size
- Enable caching
- Use Lambda@Edge for edge computing

---

## Support

For issues specific to AWS deployment, check:
- AWS Documentation
- CloudWatch Logs
- AWS Support (if you have a support plan)
