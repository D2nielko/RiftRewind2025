# Static Website for Lambda Deployment

This directory contains the standalone frontend for RiftRewind when deployed with Lambda + API Gateway.

## Files

- `index.html` - Homepage with player search form
- `results.html` - Results page showing performance analysis
- `css/style.css` - Stylesheet (League of Legends themed)
- `js/config.js` - **API configuration (UPDATE THIS!)**

## Configuration

Before deploying, you **must** update `js/config.js` with your API Gateway URL:

```javascript
const API_CONFIG = {
    API_ENDPOINT: 'https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/prod'
};
```

## Deployment

### Automated Deployment

Use the provided script (from project root):

```bash
export API_GATEWAY_URL="https://your-api-id.execute-api.us-east-1.amazonaws.com/prod"
./aws/deploy-lambda-frontend.sh
```

### Manual Deployment

1. Update `js/config.js` with your API Gateway URL
2. Upload to S3:

```bash
aws s3 sync . s3://your-bucket-name/ --exclude "*.md"
```

## Architecture

```
Browser → S3 Static Website → API Gateway → Lambda → Riot API
                                          ↓
                                      S3 (Models)
```

## Local Testing

To test locally:

1. Update `js/config.js` with your API Gateway URL
2. Open `index.html` in a browser (or use a local server):

```bash
python3 -m http.server 8000
```

Then visit: http://localhost:8000

## Notes

- This is a **static website** - no server-side rendering
- All API calls go to Lambda via API Gateway
- CORS must be enabled on API Gateway
- API Gateway URL is hardcoded in config.js
