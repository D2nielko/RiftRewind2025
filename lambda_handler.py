"""
AWS Lambda Handler for RiftRewind
Serverless deployment using Lambda + API Gateway
"""

import json
import os
import sys
from pathlib import Path

# Add ml_training to path
sys.path.insert(0, str(Path(__file__).parent / 'ml_training'))

# Initialize outside handler for reuse across invocations
predictor = None
collector = None

def init_resources():
    """Initialize resources (called once per Lambda container)"""
    global predictor, collector

    import boto3
    from ml_training.performance_predictor import PerformancePredictor
    from ml_training.data_collection import RiotDataCollector

    # Get configuration from environment
    secret_name = os.environ.get('SECRET_NAME', 'riftrewind/riot-api-key')
    models_bucket = os.environ.get('MODELS_BUCKET')
    region = os.environ.get('AWS_REGION', 'us-east-1')

    # Get Riot API key from Secrets Manager
    secrets_client = boto3.client('secretsmanager', region_name=region)
    try:
        secret_response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_data = json.loads(secret_response['SecretString'])
        riot_api_key = secret_data['RIOT_API_KEY']
    except Exception as e:
        print(f"Error getting secret: {e}")
        riot_api_key = os.environ.get('RIOT_API_KEY', '')

    # Initialize predictor with S3
    if models_bucket:
        s3_client = boto3.client('s3', region_name=region)
        predictor = PerformancePredictor(
            model_dir='models/',
            s3_client=s3_client,
            bucket=models_bucket
        )
    else:
        # Fallback to local models (if packaged with Lambda)
        predictor = PerformancePredictor(model_dir='ml_training/models/')

    # Initialize collector
    collector = {'api_key': riot_api_key}

    print("Resources initialized successfully")


def handler(event, context):
    """
    Lambda handler for API Gateway requests

    Expected event format from API Gateway:
    {
        "httpMethod": "POST",
        "path": "/api/player-performance",
        "body": "{\"gameName\":\"...\",\"tagLine\":\"...\",\"region\":\"...\"}"
    }
    """
    global predictor, collector

    # Initialize resources if not already done
    if predictor is None:
        init_resources()

    # Parse request
    http_method = event.get('httpMethod')
    path = event.get('path', '/')

    # CORS headers
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }

    # Handle OPTIONS (CORS preflight)
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': ''
        }

    # Handle API endpoints
    if path == '/api/player-performance' and http_method == 'POST':
        return handle_player_performance(event, headers)

    # Default response
    return {
        'statusCode': 404,
        'headers': headers,
        'body': json.dumps({'error': 'Not found'})
    }


def handle_player_performance(event, headers):
    """Handle player performance request"""
    global predictor, collector

    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        game_name = body.get('gameName', '').strip()
        tag_line = body.get('tagLine', '').strip()
        region = body.get('region', 'NA')

        if not game_name or not tag_line:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'success': False, 'error': 'Player name and tagline required'})
            }

        # Region mappings
        region_mappings = {
            'NA': {'platform': 'na1', 'routing': 'americas'},
            'EUW': {'platform': 'euw1', 'routing': 'europe'},
            'EUNE': {'platform': 'eun1', 'routing': 'europe'},
            'KR': {'platform': 'kr', 'routing': 'asia'},
            'BR': {'platform': 'br1', 'routing': 'americas'},
            'LAN': {'platform': 'la1', 'routing': 'americas'},
            'LAS': {'platform': 'la2', 'routing': 'americas'},
            'OCE': {'platform': 'oc1', 'routing': 'americas'},
            'TR': {'platform': 'tr1', 'routing': 'europe'},
            'RU': {'platform': 'ru', 'routing': 'europe'},
            'JP': {'platform': 'jp1', 'routing': 'asia'},
        }

        if region not in region_mappings:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'success': False, 'error': f'Invalid region: {region}'})
            }

        region_config = region_mappings[region]
        platform = region_config['platform']
        routing = region_config['routing']

        # Import here to avoid issues with Lambda cold start
        import requests
        from ml_training.data_collection import RiotDataCollector

        # Initialize collector
        data_collector = RiotDataCollector(
            api_key=collector['api_key'],
            region=platform,
            routing=routing
        )

        # Get player PUUID
        account_url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        response = requests.get(
            account_url,
            headers={'X-Riot-Token': collector['api_key']},
            timeout=10
        )

        if response.status_code == 404:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'success': False, 'error': f'Player not found: {game_name}#{tag_line}'})
            }
        elif response.status_code != 200:
            return {
                'statusCode': response.status_code,
                'headers': headers,
                'body': json.dumps({'success': False, 'error': f'Failed to fetch player data'})
            }

        account_data = response.json()
        puuid = account_data['puuid']

        # Get match history
        match_ids = data_collector.get_match_history(puuid, count=10)

        if not match_ids:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'success': False, 'error': 'No matches found'})
            }

        # Process matches
        matches = []
        for match_id in match_ids:
            match_data = data_collector.get_match_details(match_id)
            if not match_data:
                continue

            # Find player's participant
            participant = None
            for p in match_data['info']['participants']:
                if p['puuid'] == puuid:
                    participant = p
                    break

            if not participant:
                continue

            # Predict performance
            prediction = predictor.predict_performance(participant, match_data['info'])

            if prediction:
                duration_mins = match_data['info']['gameDuration'] // 60
                duration_secs = match_data['info']['gameDuration'] % 60

                matches.append({
                    'matchId': match_id,
                    'champion': prediction['champion'],
                    'role': prediction['role'],
                    'performance_score': prediction['performance_score'],
                    'grade': prediction['grade'],
                    'percentile': prediction['percentile'],
                    'win': prediction['win'],
                    'kda': f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
                    'cs': participant['totalMinionsKilled'],
                    'damage': participant['totalDamageDealtToChampions'],
                    'vision_score': participant['visionScore'],
                    'game_duration': f"{duration_mins}:{duration_secs:02d}"
                })

        if not matches:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'success': False, 'error': 'Could not analyze matches'})
            }

        # Calculate summary
        avg_score = sum(m['performance_score'] for m in matches) / len(matches)

        result = {
            'success': True,
            'player': {
                'gameName': game_name,
                'tagLine': tag_line,
                'puuid': puuid,
                'region': region
            },
            'matches': matches,
            'summary': {
                'total_matches': len(matches),
                'average_score': round(avg_score, 2),
                'wins': sum(1 for m in matches if m['win']),
                'losses': sum(1 for m in matches if not m['win'])
            }
        }

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(result)
        }

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'success': False, 'error': str(e)})
        }
