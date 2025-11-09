import json
import os
import logging
import boto3
import numpy as np
from datetime import datetime

# ML imports
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import mean_squared_error, accuracy_score

s3_client = boto3.client('s3')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-2')
logger = logging.getLogger()
logger.setLevel("INFO")

def lambda_handler(event, context):
    """ML Processor Lambda with smart caching"""
    try:
        bucket = event['bucket']
        raw_key = event['key']
        
        # Read raw data
        raw_data = read_data_from_s3(bucket, raw_key)
        riot_id = f"{raw_data['game_name']}_{raw_data['tag_line']}"
        puuid = raw_data['summoner']['puuid']
        
        # Check cache
        ml_key = f"ml-results/{riot_id}_{puuid}_ml.json"
        existing_ml = get_existing_ml_results(bucket, ml_key)
        
        should_recompute, reason = should_recompute_ml(raw_data, existing_ml)
        logger.info(f"ML Decision: {should_recompute} - {reason}")
        
        if not should_recompute:
            logger.info("⚡ Using cached results")
            bedrock_analysis = call_bedrock(raw_data, existing_ml)
            store_final_analysis(bucket, f"analysis/{riot_id}_{puuid}_analysis.json", {
                'ml_results': existing_ml,
                'bedrock_analysis': bedrock_analysis,
                'cached': True,
                'cache_reason': reason
            })
            return {'statusCode': 200, 'cached': True, 'reason': reason}
        
        # Extract features
        features, metadata = extract_features(raw_data)
        
        if len(features) < 3:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Need at least 3 matches for analysis'})
            }
        
        # Run ML algorithms
        logger.info(f"🔬 Running ML analysis: {reason}")
        ml_results = run_comprehensive_ml_analysis(features, metadata)
        
        # Store metadata
        ml_results['processed_match_ids'] = [m['matchId'] for m in metadata]
        ml_results['last_updated'] = datetime.utcnow().isoformat()
        ml_results['num_matches_analyzed'] = len(features)
        ml_results['recompute_reason'] = reason
        
        # Store ML results
        store_to_s3(bucket, ml_key, ml_results)
        logger.info(f"✅ Stored ML results")
        
        # Generate Bedrock analysis
        bedrock_analysis = call_bedrock(raw_data, ml_results)
        
        # Store final analysis
        store_final_analysis(bucket, f"analysis/{riot_id}_{puuid}_analysis.json", {
            'riot_id': f"{raw_data['game_name']}#{raw_data['tag_line']}",
            'ml_results': ml_results,
            'bedrock_analysis': bedrock_analysis,
            'cached': False,
            'processed_at': datetime.utcnow().isoformat()
        })
        
        logger.info("✅ ML analysis completed")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'cached': False,
                'reason': reason,
                'matches_analyzed': len(features)
            })
        }
        
    except Exception as e:
        logger.error(f"ML processing failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def extract_features(raw_data):
    """Extract numerical features from match data"""
    matches = raw_data['matches']
    puuid = raw_data['summoner']['puuid']
    
    features = []
    metadata = []
    
    for match in matches:
        match_info = match['info']
        for participant in match_info['participants']:
            if participant['puuid'] == puuid:
                features.append({
                    'kills': participant['kills'],
                    'deaths': participant['deaths'],
                    'assists': participant['assists'],
                    'cs': participant['totalMinionsKilled'],
                    'gold': participant['goldEarned'],
                    'damage': participant['totalDamageDealtToChampions'],
                    'vision': participant.get('visionScore', 0),
                    'kda': (participant['kills'] + participant['assists']) / max(participant['deaths'], 1),
                    'win': 1 if participant['win'] else 0,
                    'cs_per_min': participant['totalMinionsKilled'] / (match_info['gameDuration'] / 60),
                    'gold_per_min': participant['goldEarned'] / (match_info['gameDuration'] / 60),
                    'damage_per_min': participant['totalDamageDealtToChampions'] / (match_info['gameDuration'] / 60)
                })
                
                metadata.append({
                    'matchId': match['metadata']['matchId'],
                    'champion': participant['championName'],
                    'win': participant['win']
                })
                break
    
    logger.info(f"Extracted {len(features)} feature sets")
    return features, metadata

def run_comprehensive_ml_analysis(features, metadata):
    """Run multiple ML algorithms"""
    logger.info("🤖 Starting ML analysis...")
    
    feature_names = ['kills', 'deaths', 'assists', 'cs', 'gold', 'damage', 'vision', 'kda', 'cs_per_min', 'gold_per_min', 'damage_per_min']
    
    X = np.array([[f[fn] for fn in feature_names] for f in features])
    y = np.array([f['win'] for f in features])
    
    results = {}
    
    # 1. PCA
    results['pca'] = run_pca_analysis(X, feature_names)
    
    # 2. K-Means Clustering
    results['clustering'] = run_clustering_analysis(X, metadata)
    
    # 3. Linear Regression
    results['linear_regression'] = run_linear_regression_analysis(X, feature_names)
    
    # 4. Logistic Regression
    results['logistic_regression'] = run_logistic_regression_analysis(X, y, feature_names)
    
    # 5. k-NN
    results['knn'] = run_knn_analysis(X, y)
    
    # 6. Decision Tree
    results['decision_tree'] = run_decision_tree_analysis(X, y, feature_names)
    
    # 7. Summary Statistics
    results['statistics'] = compute_statistics(features, metadata)
    
    logger.info("✅ All ML algorithms completed")
    return results

def run_pca_analysis(X, feature_names):
    """PCA - Feature importance"""
    logger.info("Running PCA...")
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    pca = PCA(n_components=min(3, len(X), len(feature_names)))
    X_pca = pca.fit_transform(X_scaled)
    
    feature_importance = np.abs(pca.components_[0])
    top_features_idx = np.argsort(feature_importance)[-5:][::-1]
    
    return {
        'explained_variance_ratio': pca.explained_variance_ratio_.tolist(),
        'n_components': pca.n_components_,
        'top_features': [feature_names[i] for i in top_features_idx],
        'top_features_importance': [float(feature_importance[i]) for i in top_features_idx]
    }

def run_clustering_analysis(X, metadata):
    """K-Means - Player archetypes"""
    logger.info("Running K-Means...")
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    n_clusters = min(3, max(2, len(X) // 3))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(X_scaled)
    
    return {
        'n_clusters': n_clusters,
        'cluster_labels': clusters.tolist(),
        'player_current_archetype': int(clusters[-1])
    }

def run_linear_regression_analysis(X, feature_names):
    """Linear Regression - Performance prediction"""
    logger.info("Running Linear Regression...")
    
    # Predict KDA from other features
    X_reg = X[:, [0, 1, 2, 3, 4, 5, 6]]  # Exclude KDA itself
    y_reg = X[:, 7]  # KDA as target
    
    lr = LinearRegression()
    lr.fit(X_reg, y_reg)
    
    predictions = lr.predict(X_reg)
    mse = mean_squared_error(y_reg, predictions)
    
    return {
        'coefficients': lr.coef_.tolist(),
        'intercept': float(lr.intercept_),
        'mse': float(mse),
        'r_squared': float(lr.score(X_reg, y_reg)),
        'predictions': predictions.tolist()
    }

def run_logistic_regression_analysis(X, y, feature_names):
    """Logistic Regression - Win prediction"""
    logger.info("Running Logistic Regression...")
    
    if len(np.unique(y)) < 2:
        return {'error': 'Insufficient class diversity'}
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    log_reg = LogisticRegression(random_state=42, max_iter=1000)
    log_reg.fit(X_scaled, y)
    
    win_probs = log_reg.predict_proba(X_scaled)
    predictions = log_reg.predict(X_scaled)
    
    coef_importance = np.abs(log_reg.coef_[0])
    top_features_idx = np.argsort(coef_importance)[-5:][::-1]
    
    return {
        'coefficients': log_reg.coef_.tolist(),
        'win_probabilities': win_probs.tolist(),
        'predictions': predictions.tolist(),
        'accuracy': float(accuracy_score(y, predictions)),
        'predicted_next_game_win_prob': float(win_probs[-1][1]),
        'top_win_factors': [feature_names[i] for i in top_features_idx]
    }

def run_knn_analysis(X, y):
    """k-NN - Pattern matching"""
    logger.info("Running k-NN...")
    
    if len(X) < 5:
        return {'error': 'Insufficient data'}
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    k = min(3, len(X) - 1)
    knn = KNeighborsClassifier(n_neighbors=k)
    knn.fit(X_scaled[:-1], y[:-1])
    knn_pred = knn.predict(X_scaled[-1:])
    
    return {
        'k': k,
        'predicted_win': bool(knn_pred[0]),
        'actual_win': bool(y[-1]),
        'correct_prediction': bool(knn_pred[0] == y[-1])
    }

def run_decision_tree_analysis(X, y, feature_names):
    """Decision Tree - Interpretable classification"""
    logger.info("Running Decision Tree...")
    
    if len(np.unique(y)) < 2:
        return {'error': 'Insufficient class diversity'}
    
    dt = DecisionTreeClassifier(max_depth=4, random_state=42)
    dt.fit(X, y)
    
    feature_importance = dt.feature_importances_
    top_features_idx = np.argsort(feature_importance)[-5:][::-1]
    
    return {
        'feature_importance': feature_importance.tolist(),
        'top_features': [feature_names[i] for i in top_features_idx],
        'top_importance_scores': [float(feature_importance[i]) for i in top_features_idx],
        'accuracy': float(accuracy_score(y, dt.predict(X)))
    }

def compute_statistics(features, metadata):
    """Summary statistics"""
    wins = sum(f['win'] for f in features)
    total = len(features)
    
    # Champion stats
    champion_stats = {}
    for i, meta in enumerate(metadata):
        champ = meta['champion']
        if champ not in champion_stats:
            champion_stats[champ] = {'wins': 0, 'games': 0, 'total_kda': 0}
        
        champion_stats[champ]['games'] += 1
        champion_stats[champ]['total_kda'] += features[i]['kda']
        if meta['win']:
            champion_stats[champ]['wins'] += 1
    
    for champ in champion_stats:
        stats = champion_stats[champ]
        stats['winrate'] = stats['wins'] / stats['games']
        stats['avg_kda'] = stats['total_kda'] / stats['games']
    
    top_champions = sorted(champion_stats.items(), key=lambda x: x[1]['games'], reverse=True)[:5]
    
    return {
        'total_games': total,
        'wins': wins,
        'losses': total - wins,
        'win_rate': wins / total if total > 0 else 0,
        'avg_kda': float(np.mean([f['kda'] for f in features])),
        'avg_kills': float(np.mean([f['kills'] for f in features])),
        'avg_deaths': float(np.mean([f['deaths'] for f in features])),
        'avg_assists': float(np.mean([f['assists'] for f in features])),
        'avg_cs': float(np.mean([f['cs'] for f in features])),
        'avg_vision': float(np.mean([f['vision'] for f in features])),
        'top_champions': [
            {
                'champion': champ,
                'games': stats['games'],
                'wins': stats['wins'],
                'winrate': float(stats['winrate']),
                'avg_kda': float(stats['avg_kda'])
            }
            for champ, stats in top_champions
        ]
    }

def should_recompute_ml(raw_data, existing_ml):
    """Check if recomputation needed"""
    if not existing_ml:
        return True, "No existing results"
    
    new_ids = [m['metadata']['matchId'] for m in raw_data['matches']]
    old_ids = existing_ml.get('processed_match_ids', [])
    
    if set(new_ids) == set(old_ids):
        return False, "No new matches"
    
    new_count = len(set(new_ids) - set(old_ids))
    if new_count >= 3:
        return True, f"{new_count} new matches"
    
    return False, f"Only {new_count} new matches - using cache"

def call_bedrock(raw_data, ml_results):
    """Call Bedrock Llama for natural language analysis"""
    stats = ml_results.get('statistics', {})
    pca = ml_results.get('pca', {})
    log_reg = ml_results.get('logistic_regression', {})
    dt = ml_results.get('decision_tree', {})
    
    prompt = f"""Analyze this League of Legends player's performance:

Player: {raw_data['game_name']}#{raw_data['tag_line']}
Games Analyzed: {stats.get('total_games', 0)}
Win Rate: {stats.get('win_rate', 0):.1%}

=== STATS ===
Average KDA: {stats.get('avg_kda', 0):.2f}
Average CS: {stats.get('avg_cs', 0):.1f}
Average Vision Score: {stats.get('avg_vision', 0):.1f}

Top Champions:
{chr(10).join([f"- {c['champion']}: {c['games']} games, {c['winrate']:.1%} WR, {c['avg_kda']:.2f} KDA" for c in stats.get('top_champions', [])[:3]])}

=== ML INSIGHTS ===
1. PCA Analysis: Top performance factors are {', '.join(pca.get('top_features', [])[:3])}
2. Win Prediction: {log_reg.get('predicted_next_game_win_prob', 0):.1%} probability for next game
3. Key win factors: {', '.join(log_reg.get('top_win_factors', [])[:3])}
4. Decision Tree top factors: {', '.join(dt.get('top_features', [])[:3])}

Provide:
1. Brief playstyle summary (2 sentences)
2. Top 3 strengths
3. Top 2 specific, actionable improvements
Keep it concise and data-driven."""
    
    # Llama request format
    body = json.dumps({
        "prompt": prompt,
        "max_gen_len": 1000,
        "temperature": 0.7,
        "top_p": 0.9
    })
    
    model_id = os.environ.get('BEDROCK_MODEL_ID', 'meta.llama3-70b-instruct-v1:0')
    
    try:
        logger.info(f"Calling Bedrock model: {model_id}")
        response = bedrock.invoke_model(modelId=model_id, body=body)
        response_body = json.loads(response['body'].read())
        
        # Log the response for debugging
        logger.info(f"Bedrock response keys: {response_body.keys()}")
        
        # Llama response format - use 'generation' not 'content'
        analysis = response_body['generation']
        
        logger.info("Successfully received analysis from Bedrock")
        return analysis
        
    except KeyError as e:
        logger.error(f"KeyError in Bedrock response: {str(e)}")
        logger.error(f"Response body: {response_body}")
        # Return fallback
        return f"Analysis for {raw_data['game_name']}#{raw_data['tag_line']}: {stats.get('win_rate', 0):.1%} win rate across {stats.get('total_games', 0)} games."
        
    except Exception as e:
        logger.error(f"Bedrock error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        # Return fallback
        return f"Analysis for {raw_data['game_name']}#{raw_data['tag_line']}: {stats.get('win_rate', 0):.1%} win rate."

def read_data_from_s3(bucket, key):
    """Read from S3"""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return json.loads(response['Body'].read())

def get_existing_ml_results(bucket, key):
    """Get existing ML results"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(response['Body'].read())
    except:
        return None

def store_to_s3(bucket, key, data):
    """Store to S3"""
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2),
        ContentType='application/json'
    )

def store_final_analysis(bucket, key, data):
    """Store final analysis"""
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2),
        ContentType='application/json'
    )