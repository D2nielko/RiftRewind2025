import json
import os
import logging
import boto3
import urllib3

# Initialize clients outside handler
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')
http = urllib3.PoolManager()

# Initialize logger
logger = logging.getLogger()
logger.setLevel("INFO")

def lambda_handler(event, context):
    """
    Data Fetcher Lambda - Fetches data from Riot API
    """
    try:
        # Parse input
        game_name = event['game_name']
        tag_line = event['tag_line']
        region = event['region']
        
        logger.info(f"Processing request for {game_name}#{tag_line} in {region}")
        
        # Get environment variables
        api_key = os.environ.get('RIOT_API_KEY')
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        ml_function_name = os.environ.get('ML_PROCESSOR_FUNCTION_NAME')
        
        if not api_key or not bucket_name:
            raise ValueError("Missing required environment variables")
        
        # 1. Get PUUID from Riot ID
        puuid = get_puuid_from_riot_id(game_name, tag_line, region, api_key)
        
        # 2. Get summoner data
        summoner_data = get_summoner_by_puuid(puuid, region, api_key)
        
        # 3. Get match history
        match_ids = get_match_ids(puuid, region, api_key, count=20)
        matches = get_matches_batch(match_ids[:10], region, api_key)
        
        # 4. Compile all data
        complete_data = {
            'game_name': game_name,
            'tag_line': tag_line,
            'summoner': summoner_data,
            'matches': matches
        }
        
        # 5. Store in S3
        riot_id = f"{game_name}_{tag_line}"
        key = f"raw-data/{riot_id}_{puuid}.json"
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(complete_data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"✅ Stored data to s3://{bucket_name}/{key}")
        
        # 6. Trigger ML processor
        if ml_function_name:
            lambda_client.invoke(
                FunctionName=ml_function_name,
                InvocationType='Event',  # Asynchronous
                Payload=json.dumps({
                    'bucket': bucket_name,
                    'key': key,
                    'game_name': game_name,
                    'tag_line': tag_line
                })
            )
            logger.info(f"✅ Triggered ML processor")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Data fetched successfully',
                'riotId': f"{game_name}#{tag_line}",
                's3_key': key,
                'matches_fetched': len(matches)
            })
        }
        
    except KeyError as e:
        logger.error(f"Missing parameter: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': f'Missing required parameter: {str(e)}',
                'required': ['game_name', 'tag_line', 'region']
            })
        }
    
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def get_puuid_from_riot_id(game_name, tag_line, platform_region, api_key):
    """Get PUUID from Riot ID"""
    region_mapping = {
        'na1': 'americas', 'br1': 'americas', 'la1': 'americas', 'la2': 'americas',
        'euw1': 'europe', 'eun1': 'europe', 'tr1': 'europe', 'ru': 'europe',
        'kr': 'asia', 'jp1': 'asia',
        'oc1': 'sea', 'ph2': 'sea', 'sg2': 'sea', 'th2': 'sea', 'tw2': 'sea', 'vn2': 'sea'
    }
    
    regional_route = region_mapping.get(platform_region.lower(), 'americas')
    url = f"https://{regional_route}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {'X-Riot-Token': api_key}
    
    logger.info(f"Fetching PUUID from: {url}")
    response = http.request('GET', url, headers=headers)
    
    if response.status != 200:
        raise Exception(f"Riot API error: {response.status} - {response.data.decode('utf-8')}")
    
    account_data = json.loads(response.data.decode('utf-8'))
    logger.info(f"Successfully retrieved PUUID")
    return account_data['puuid']

def get_summoner_by_puuid(puuid, region, api_key):
    """Get summoner data by PUUID"""
    url = f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {'X-Riot-Token': api_key}
    
    logger.info(f"Fetching summoner data")
    response = http.request('GET', url, headers=headers)
    
    if response.status != 200:
        raise Exception(f"Summoner API error: {response.status}")
    
    return json.loads(response.data.decode('utf-8'))

def get_match_ids(puuid, platform_region, api_key, count=20):
    """Get match IDs for a player"""
    region_mapping = {
        'na1': 'americas', 'br1': 'americas', 'la1': 'americas', 'la2': 'americas',
        'euw1': 'europe', 'eun1': 'europe', 'tr1': 'europe', 'ru': 'europe',
        'kr': 'asia', 'jp1': 'asia',
        'oc1': 'sea', 'ph2': 'sea', 'sg2': 'sea', 'th2': 'sea', 'tw2': 'sea', 'vn2': 'sea'
    }
    
    routing = region_mapping.get(platform_region.lower(), 'americas')
    url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}"
    headers = {'X-Riot-Token': api_key}
    
    logger.info(f"Fetching match IDs")
    response = http.request('GET', url, headers=headers)
    
    if response.status != 200:
        raise Exception(f"Match IDs error: {response.status}")
    
    match_ids = json.loads(response.data.decode('utf-8'))
    logger.info(f"Found {len(match_ids)} matches")
    return match_ids

def get_matches_batch(match_ids, platform_region, api_key):
    """Get multiple match details"""
    region_mapping = {
        'na1': 'americas', 'br1': 'americas', 'la1': 'americas', 'la2': 'americas',
        'euw1': 'europe', 'eun1': 'europe', 'tr1': 'europe', 'ru': 'europe',
        'kr': 'asia', 'jp1': 'asia',
        'oc1': 'sea', 'ph2': 'sea', 'sg2': 'sea', 'th2': 'sea', 'tw2': 'sea', 'vn2': 'sea'
    }
    
    routing = region_mapping.get(platform_region.lower(), 'americas')
    headers = {'X-Riot-Token': api_key}
    
    matches = []
    for i, match_id in enumerate(match_ids):
        try:
            url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{match_id}"
            response = http.request('GET', url, headers=headers)
            
            if response.status == 200:
                matches.append(json.loads(response.data.decode('utf-8')))
                logger.info(f"Fetched match {i+1}/{len(match_ids)}")
            else:
                logger.warning(f"Failed to fetch match {match_id}: {response.status}")
        except Exception as e:
            logger.warning(f"Error fetching match {match_id}: {str(e)}")
            continue
    
    return matches