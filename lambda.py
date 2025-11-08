import json
import os
import logging
import boto3
import urllib3

# Initialize clients outside of handler
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
s3_client = boto3.client('s3')
http = urllib3.PoolManager()

# Initialize logger
logger = logging.getLogger()
logger.setLevel("INFO")

def get_puuid_from_riot_id(game_name, tag_line, platform_region):
    """
    Get PUUID from Riot ID using the new Account-V1 API
    Uses regional routing (americas, europe, asia, sea)
    """
    # Map platform regions to regional routing values
    region_mapping = {
        'na1': 'americas', 'br1': 'americas', 'la1': 'americas', 'la2': 'americas',
        'euw1': 'europe', 'eun1': 'europe', 'tr1': 'europe', 'ru': 'europe',
        'kr': 'asia', 'jp1': 'asia',
        'oc1': 'sea', 'ph2': 'sea', 'sg2': 'sea', 'th2': 'sea', 'tw2': 'sea', 'vn2': 'sea'
    }
    
    regional_route = region_mapping.get(platform_region.lower(), 'americas')
    riot_api_key = os.environ.get('RIOT_API_KEY')
    
    # New endpoint: /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}
    url = f"https://{regional_route}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {'X-Riot-Token': riot_api_key}
    
    logger.info(f"Fetching PUUID from: {url}")
    response = http.request('GET', url, headers=headers)
    
    if response.status != 200:
        error_msg = f"Riot API error getting PUUID: {response.status} - {response.data.decode('utf-8')}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    account_data = json.loads(response.data.decode('utf-8'))
    logger.info(f"Successfully retrieved PUUID for {game_name}#{tag_line}")
    return account_data['puuid']

def get_summoner_by_puuid(puuid, region):
    """
    Get summoner data using PUUID
    Uses platform routing (na1, euw1, kr, etc.)
    """
    riot_api_key = os.environ.get('RIOT_API_KEY')
    url = f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {'X-Riot-Token': riot_api_key}
    
    logger.info(f"Fetching summoner data from: {url}")
    response = http.request('GET', url, headers=headers)
    
    if response.status != 200:
        error_msg = f"Summoner API error: {response.status} - {response.data.decode('utf-8')}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    summoner_data = json.loads(response.data.decode('utf-8'))
    logger.info(f"Successfully retrieved summoner data for PUUID: {puuid[:8]}...")
    return summoner_data

def fetch_match_history(puuid, platform_region):
    """Fetch recent match history"""
    # Map platform to regional routing for match API
    region_mapping = {
        'na1': 'americas', 'br1': 'americas', 'la1': 'americas', 'la2': 'americas',
        'euw1': 'europe', 'eun1': 'europe', 'tr1': 'europe', 'ru': 'europe',
        'kr': 'asia', 'jp1': 'asia',
        'oc1': 'sea', 'ph2': 'sea', 'sg2': 'sea', 'th2': 'sea', 'tw2': 'sea', 'vn2': 'sea'
    }
    
    routing = region_mapping.get(platform_region.lower(), 'americas')
    riot_api_key = os.environ.get('RIOT_API_KEY')
    
    # Get match IDs
    url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count=20"
    headers = {'X-Riot-Token': riot_api_key}
    
    logger.info(f"Fetching match IDs from: {url}")
    response = http.request('GET', url, headers=headers)
    
    if response.status != 200:
        error_msg = f"Match history error: {response.status} - {response.data.decode('utf-8')}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    match_ids = json.loads(response.data.decode('utf-8'))
    logger.info(f"Found {len(match_ids)} matches")
    
    # Fetch detailed match data (first 5 for now)
    matches = []
    for i, match_id in enumerate(match_ids[:5]):
        match_url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        match_response = http.request('GET', match_url, headers=headers)
        
        if match_response.status == 200:
            matches.append(json.loads(match_response.data.decode('utf-8')))
            logger.info(f"Fetched match {i+1}/5: {match_id}")
        else:
            logger.warning(f"Failed to fetch match {match_id}: {match_response.status}")
    
    logger.info(f"Successfully fetched {len(matches)} detailed matches")
    return matches

def store_to_s3(summoner_data, match_history, game_name, tag_line):
    """Store data in S3"""
    bucket_name = os.environ.get('S3_BUCKET_NAME')
    if not bucket_name:
        raise ValueError("Missing required environment variable S3_BUCKET_NAME")
    
    data = {
        'summoner': summoner_data,
        'matches': match_history
    }
    
    riot_id = f"{game_name}_{tag_line}"
    key = f"riot-data/{riot_id}_{summoner_data['puuid']}.json"
    
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )
        logger.info(f"Successfully stored data to s3://{bucket_name}/{key}")
    except Exception as e:
        logger.error(f"Failed to upload to S3: {str(e)}")
        raise

def analyze_with_bedrock(summoner_data, match_history, game_name, tag_line):
    """Use Bedrock Claude to analyze the data"""
    
    # Prepare summary of match data
    match_summary = []
    for match in match_history:
        # Find the player's stats in this match
        for participant in match['info']['participants']:
            if participant['puuid'] == summoner_data['puuid']:
                match_summary.append({
                    'champion': participant['championName'],
                    'win': participant['win'],
                    'kills': participant['kills'],
                    'deaths': participant['deaths'],
                    'assists': participant['assists'],
                    'cs': participant['totalMinionsKilled'],
                    'visionScore': participant.get('visionScore', 0),
                    'gameDuration': match['info']['gameDuration'] // 60  # Convert to minutes
                })
                break
    
    # Create prompt for Claude
    prompt = f"""Analyze this League of Legends player's recent performance:

Riot ID: {game_name}#{tag_line}
Summoner Level: {summoner_data['summonerLevel']}

Recent matches (last {len(match_summary)} games):
{json.dumps(match_summary, indent=2)}

Provide a brief analysis including:
1. Overall performance trends (win rate, KDA patterns)
2. Key strengths based on the stats
3. One specific, actionable recommendation for improvement

Keep it concise and focused on the data provided."""

    logger.info("Calling Bedrock for analysis...")
    
    try:
        # Call Bedrock
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })
        
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
            body=body
        )
        
        response_body = json.loads(response['body'].read())
        analysis = response_body['content'][0]['text']
        
        logger.info("Successfully received analysis from Bedrock")
        return analysis
        
    except Exception as e:
        logger.error(f"Bedrock analysis failed: {str(e)}")
        raise

def lambda_handler(event, context):
    """
    Main Lambda handler function
    
    Parameters:
        event: Dict containing game_name, tag_line, and region
        context: Lambda runtime context
        
    Returns:
        Dict containing status and analysis results
    """
    try:
        # Parse the input event
        game_name = event['game_name']
        tag_line = event['tag_line']
        region = event['region']
        
        logger.info(f"Processing request for {game_name}#{tag_line} in region {region}")
        
        # Validate environment variables
        riot_api_key = os.environ.get('RIOT_API_KEY')
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        
        if not riot_api_key:
            raise ValueError("Missing required environment variable RIOT_API_KEY")
        if not bucket_name:
            raise ValueError("Missing required environment variable S3_BUCKET_NAME")
        
        # Step 1: Get PUUID from Riot ID
        puuid = get_puuid_from_riot_id(game_name, tag_line, region)
        
        # Step 2: Get summoner data using PUUID
        summoner_data = get_summoner_by_puuid(puuid, region)
        
        # Step 3: Fetch match history
        match_history = fetch_match_history(puuid, region)
        
        # Step 4: Store raw data in S3
        store_to_s3(summoner_data, match_history, game_name, tag_line)
        
        # Step 5: Analyze with Bedrock
        analysis = analyze_with_bedrock(summoner_data, match_history, game_name, tag_line)
        
        logger.info(f"Successfully completed analysis for {game_name}#{tag_line}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Analysis completed successfully',
                'riotId': f"{game_name}#{tag_line}",
                'summoner': {
                    'name': summoner_data.get('name', ''),
                    'level': summoner_data['summonerLevel'],
                    'puuid': puuid
                },
                'matchesAnalyzed': len(match_history),
                'analysis': analysis
            })
        }
        
    except KeyError as e:
        error_msg = f"Missing required parameter: {str(e)}"
        logger.error(error_msg)
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': error_msg,
                'message': 'Required parameters: game_name, tag_line, region'
            })
        }
        
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        logger.error(error_msg)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_msg
            })
        }
