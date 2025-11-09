"""
Test Script for Performance Models

Quick test to verify models work correctly before deployment.

Usage:
    python test_models.py --models-dir models/
"""

import json
import argparse
import numpy as np
from performance_predictor import PerformancePredictor


def generate_test_participant():
    """Generate synthetic test participant data"""
    return {
        'puuid': 'test_puuid',
        'championName': 'Khazix',
        'individualPosition': 'JUNGLE',
        'kills': 7,
        'deaths': 2,
        'assists': 11,
        'totalMinionsKilled': 120,
        'neutralMinionsKilled': 110,
        'goldEarned': 12000,
        'totalDamageDealtToChampions': 18000,
        'totalDamageTaken': 15000,
        'damageSelfMitigated': 8000,
        'visionScore': 35,
        'wardsPlaced': 8,
        'wardsKilled': 3,
        'turretKills': 2,
        'dragonKills': 2,
        'baronKills': 0,
        'doubleKills': 1,
        'tripleKills': 0,
        'quadraKills': 0,
        'pentaKills': 0,
        'timeCCingOthers': 15,
        'totalHeal': 5000,
        'totalDamageShieldedOnTeammates': 0,
        'totalTimeSpentDead': 45,
        'longestTimeSpentLiving': 600,
        'firstBloodKill': False,
        'firstTowerKill': False,
        'win': True,
        'challenges': {
            'teamDamagePercentage': 0.28,
            'controlWardsPlaced': 2,
            'turretPlatesTaken': 1,
            'laneMinionsFirst10Minutes': 0,
            'jungleCsBefore10Minutes': 60,
            'maxCsAdvantageOnLaneOpponent': 15,
            'earlyLaningPhaseGoldExpAdvantage': 1,
            'killParticipation': 0.72,
            'soloKills': 2,
            'skillshotsHit': 25,
            'skillshotsDodged': 18
        }
    }


def generate_test_match_info():
    """Generate synthetic match info"""
    return {
        'gameDuration': 1800,  # 30 minutes
        'gameMode': 'CLASSIC'
    }


def test_all_roles(predictor):
    """Test predictions for all roles"""
    roles = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']

    print("\n" + "="*60)
    print("Testing All Roles")
    print("="*60)

    for role in roles:
        participant = generate_test_participant()
        participant['individualPosition'] = role

        # Adjust stats slightly for each role
        if role == 'BOTTOM':
            participant['totalMinionsKilled'] = 250
            participant['neutralMinionsKilled'] = 0
        elif role == 'UTILITY':
            participant['totalMinionsKilled'] = 25
            participant['visionScore'] = 60

        match_info = generate_test_match_info()

        prediction = predictor.predict_performance(participant, match_info)

        if prediction:
            print(f"\n{role}:")
            print(f"  Score: {prediction['performance_score']:.2f}")
            print(f"  Grade: {prediction['grade']}")
            print(f"  Percentile: {prediction['percentile']:.1f}%")
        else:
            print(f"\n{role}: ❌ FAILED")


def test_edge_cases(predictor):
    """Test edge cases"""
    print("\n" + "="*60)
    print("Testing Edge Cases")
    print("="*60)

    # Test 1: Perfect game
    print("\n1. Perfect Game (10/0/10):")
    participant = generate_test_participant()
    participant['kills'] = 10
    participant['deaths'] = 0
    participant['assists'] = 10
    match_info = generate_test_match_info()

    prediction = predictor.predict_performance(participant, match_info)
    if prediction:
        print(f"   Score: {prediction['performance_score']:.2f} (Grade: {prediction['grade']})")

    # Test 2: Bad game
    print("\n2. Bad Game (0/10/2):")
    participant = generate_test_participant()
    participant['kills'] = 0
    participant['deaths'] = 10
    participant['assists'] = 2
    participant['win'] = False
    participant['totalDamageDealtToChampions'] = 5000

    prediction = predictor.predict_performance(participant, match_info)
    if prediction:
        print(f"   Score: {prediction['performance_score']:.2f} (Grade: {prediction['grade']})")

    # Test 3: Short game
    print("\n3. Short Game (10 minutes):")
    participant = generate_test_participant()
    match_info = generate_test_match_info()
    match_info['gameDuration'] = 600

    prediction = predictor.predict_performance(participant, match_info)
    if prediction:
        print(f"   Score: {prediction['performance_score']:.2f} (Grade: {prediction['grade']})")


def test_batch_prediction(predictor):
    """Test batch prediction"""
    print("\n" + "="*60)
    print("Testing Batch Prediction")
    print("="*60)

    participants = []
    for i, role in enumerate(['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']):
        p = generate_test_participant()
        p['individualPosition'] = role
        p['puuid'] = f'player_{i}'
        participants.append(p)

    match_info = generate_test_match_info()

    predictions = predictor.predict_batch(participants, match_info)

    print(f"\nPredicted {len(predictions)} out of {len(participants)} participants:")
    for puuid, pred in predictions.items():
        print(f"  {pred['role']}: {pred['performance_score']:.1f} ({pred['grade']})")


def main():
    parser = argparse.ArgumentParser(description='Test performance models')
    parser.add_argument('--models-dir', default='models/', help='Directory containing trained models')

    args = parser.parse_args()

    print("Loading models...")
    try:
        predictor = PerformancePredictor(model_dir=args.models_dir)
        print(f"✅ Loaded {len(predictor.models)} models")
        print(f"   Roles: {list(predictor.models.keys())}")
        print(f"   Features: {len(predictor.feature_columns)}")
    except Exception as e:
        print(f"❌ Failed to load models: {e}")
        return

    # Run tests
    test_all_roles(predictor)
    test_edge_cases(predictor)
    test_batch_prediction(predictor)

    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)


if __name__ == '__main__':
    main()
