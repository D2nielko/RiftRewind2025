// API Configuration
// Replace this URL with your API Gateway endpoint
const API_CONFIG = {
    // After deploying Lambda + API Gateway, replace this with your API Gateway URL
    // Example: https://abc123.execute-api.us-east-1.amazonaws.com/prod
    API_ENDPOINT: 'YOUR_API_GATEWAY_URL_HERE',

    // If you get CORS errors, make sure API Gateway has CORS enabled
};

// Helper function to make API calls
async function callAPI(path, method = 'GET', body = null) {
    const url = `${API_CONFIG.API_ENDPOINT}${path}`;

    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json',
        }
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch(url, options);

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'API request failed');
    }

    return await response.json();
}
