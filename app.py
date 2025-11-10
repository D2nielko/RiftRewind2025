"""
Flask Web Application for League of Legends Performance Tracker

This application allows users to enter player information and view
performance scores for their last 10 games.
"""

import os
import sys
import json
from flask import Flask, render_template, request, jsonify
from mangum import Mangum
import logging

# Add ml_training to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ml_training'))

from ml_training.data_collection import RiotDataCollector
from ml_training.performance_predictor import PerformancePredictor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
MODEL_DIR = 'ml_training/models/'
MODELS_BUCKET = os.environ.get('MODELS_BUCKET')  # S3 bucket for models (optional)
SECRET_NAME = os.environ.get('SECRET_NAME', 'riftrewind/riot-api-key')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-2')

# Get Riot API key (try AWS Secrets Manager first, then environment variable)
RIOT_API_KEY = ''
try:
    # Try to get from AWS Secrets Manager if available
    if SECRET_NAME and not os.environ.get('RIOT_API_KEY'):
        try:
            import boto3
            secrets_client = boto3.client('secretsmanager', region_name=AWS_REGION)
            secret_response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
            secret_data = json.loads(secret_response['SecretString'])
            RIOT_API_KEY = secret_data['RIOT_API_KEY']
            logger.info("Riot API key loaded from AWS Secrets Manager")
        except ImportError:
            logger.info("boto3 not available, skipping AWS Secrets Manager")
        except Exception as e:
            logger.warning(f"Could not load from Secrets Manager: {e}")

    # Fall back to environment variable
    if not RIOT_API_KEY:
        RIOT_API_KEY = os.environ.get('RIOT_API_KEY', '')
        if RIOT_API_KEY:
            logger.info("Riot API key loaded from environment variable")
except Exception as e:
    logger.error(f"Error loading API key: {e}")

# Region mappings
REGION_MAPPINGS = {
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

# Initialize predictor
try:
    # Use S3 if MODELS_BUCKET is specified
    if MODELS_BUCKET:
        try:
            import boto3
            s3_client = boto3.client('s3', region_name=AWS_REGION)
            predictor = PerformancePredictor(
                model_dir='models/',
                s3_client=s3_client,
                bucket=MODELS_BUCKET
            )
            logger.info(f"Performance predictor loaded from S3 bucket: {MODELS_BUCKET}")
        except Exception as e:
            logger.error(f"Failed to load from S3, trying local: {e}")
            predictor = PerformancePredictor(model_dir=MODEL_DIR)
            logger.info("Performance predictor loaded from local storage")
    else:
        # Load from local directory
        predictor = PerformancePredictor(model_dir=MODEL_DIR)
        logger.info("Performance predictor loaded from local storage")
except Exception as e:
    logger.error(f"Failed to load performance predictor: {e}")
    predictor = None


@app.route('/')
def index():
    """Homepage with player input form"""
    return render_template('index.html', regions=list(REGION_MAPPINGS.keys()))


@app.route('/api/player-performance', methods=['POST'])
def get_player_performance():
    """
    API endpoint to fetch player performance data

    Request body:
    {
        "gameName": "PlayerName",
        "tagLine": "NA1",
        "region": "NA"
    }

    Response:
    {
        "success": true,
        "player": {
            "gameName": "PlayerName",
            "tagLine": "NA1",
            "puuid": "..."
        },
        "matches": [
            {
                "matchId": "...",
                "champion": "Ahri",
                "role": "MIDDLE",
                "performance_score": 85.5,
                "grade": "A",
                "percentile": 92.5,
                "win": true,
                "kda": "10/2/15",
                "cs": 250,
                "damage": 45000,
                "vision_score": 35,
                "game_duration": "25:30"
            },
            ...
        ]
    }
    """
    if not RIOT_API_KEY:
        return jsonify({
            'success': False,
            'error': 'Riot API key not configured. Please set RIOT_API_KEY environment variable.'
        }), 500

    if not predictor:
        return jsonify({
            'success': False,
            'error': 'Performance predictor not loaded. Please ensure models are trained.'
        }), 500

    try:
        data = request.get_json()
        game_name = data.get('gameName', '').strip()
        tag_line = data.get('tagLine', '').strip()
        region = data.get('region', 'NA')

        if not game_name or not tag_line:
            return jsonify({
                'success': False,
                'error': 'Player name and tagline are required'
            }), 400

        if region not in REGION_MAPPINGS:
            return jsonify({
                'success': False,
                'error': f'Invalid region: {region}'
            }), 400

        # Get region configuration
        region_config = REGION_MAPPINGS[region]
        platform = region_config['platform']
        routing = region_config['routing']

        # Initialize Riot API collector
        collector = RiotDataCollector(
            api_key=RIOT_API_KEY,
            region=platform,
            routing=routing
        )

        # Get player PUUID from Riot ID
        logger.info(f"Fetching player: {game_name}#{tag_line} in {region}")
        account_url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"

        import requests
        response = requests.get(account_url, headers={'X-Riot-Token': RIOT_API_KEY}, timeout=10)

        if response.status_code == 404:
            return jsonify({
                'success': False,
                'error': f'Player not found: {game_name}#{tag_line}'
            }), 404
        elif response.status_code != 200:
            return jsonify({
                'success': False,
                'error': f'Failed to fetch player data (Status: {response.status_code})'
            }), response.status_code

        account_data = response.json()
        puuid = account_data['puuid']

        # Get last 10 matches
        logger.info(f"Fetching match history for PUUID: {puuid}")
        match_ids = collector.get_match_history(puuid, count=10)

        if not match_ids:
            return jsonify({
                'success': False,
                'error': 'No matches found for this player'
            }), 404

        # Process each match
        matches = []
        for match_id in match_ids:
            logger.info(f"Processing match: {match_id}")
            match_data = collector.get_match_details(match_id)

            if not match_data:
                continue

            # Find player's participant data
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
            return jsonify({
                'success': False,
                'error': 'Could not analyze any matches for this player'
            }), 404

        # Calculate average performance
        avg_score = sum(m['performance_score'] for m in matches) / len(matches)

        return jsonify({
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
        })

    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@app.route('/results')
def results():
    """Results page (displays data via JavaScript fetch)"""
    return render_template('results.html')


handler = Mangum(app)

if __name__ == '__main__':
    if not RIOT_API_KEY:
        logger.warning("RIOT_API_KEY not set! Application will not work without it.")
        logger.warning("Set it using: export RIOT_API_KEY='your_key_here'")

    app.run(debug=True, host='0.0.0.0', port=5000)
