"""
Test Performance Prediction on Real Match Data

This script loads a real match JSON file and runs predictions on all participants
to test the trained models.

Usage:
    python test_prediction.py --match-file NA1_5408720212.txt --model-dir models/
"""

import json
import argparse
import logging
from pathlib import Path
from performance_predictor import PerformancePredictor

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_match_data(match_file: str) -> dict:
    """Load match data from JSON file"""
    logger.info(f"Loading match data from {match_file}...")

    with open(match_file, 'r') as f:
        data = json.load(f)

    return data


def display_prediction(prediction: dict, participant: dict):
    """Display prediction results in a formatted way"""
    print(f"\n{'=' * 70}")
    print(f"Player: {participant.get('riotIdGameName', 'Unknown')}#{participant.get('riotIdTagline', '')}")
    print(f"Champion: {prediction['champion']}")
    print(f"Role: {prediction['role']}")
    print(f"Result: {'WIN' if prediction['win'] else 'LOSS'}")
    print(f"{'-' * 70}")
    print(f"Performance Score: {prediction['performance_score']:.2f}/100")
    print(f"Grade: {prediction['grade']}")
    print(f"Percentile: {prediction['percentile']:.1f}%")
    print(f"{'=' * 70}")

    # Display key stats
    print(f"KDA: {participant['kills']}/{participant['deaths']}/{participant['assists']}")
    duration_mins = participant.get('timePlayed', 0) / 60
    print(f"CS: {participant['totalMinionsKilled']} ({participant['totalMinionsKilled']/duration_mins:.1f} CS/min)")
    print(f"Damage: {participant['totalDamageDealtToChampions']:,} ({participant['totalDamageDealtToChampions']/duration_mins:.0f}/min)")
    print(f"Vision Score: {participant['visionScore']} ({participant['visionScore']/duration_mins:.2f}/min)")


def test_predictions(match_file: str, model_dir: str = 'models/', target_player: str = None):
    """
    Run predictions on all participants in a match

    Args:
        match_file: Path to match JSON file
        model_dir: Directory containing trained models
        target_player: Optional - only show predictions for this player name
    """
    # Load match data
    match_data = load_match_data(match_file)

    # Initialize predictor
    logger.info(f"Loading models from {model_dir}...")
    predictor = PerformancePredictor(model_dir=model_dir)

    # Get match info and participants
    info = match_data['info']
    participants = info['participants']

    logger.info(f"Match ID: {match_data['metadata']['matchId']}")
    logger.info(f"Game Duration: {info['gameDuration'] // 60}:{info['gameDuration'] % 60:02d}")
    logger.info(f"Analyzing {len(participants)} participants...")

    # Run predictions
    predictions = []
    for participant in participants:
        player_name = participant.get('riotIdGameName', 'Unknown')

        # Skip if we're filtering for a specific player
        if target_player and player_name.lower() != target_player.lower():
            continue

        prediction = predictor.predict_performance(participant, info)

        if prediction:
            predictions.append({
                'prediction': prediction,
                'participant': participant
            })

    # Sort by performance score (descending)
    predictions.sort(key=lambda x: x['prediction']['performance_score'], reverse=True)

    # Display results
    print("\n" + "=" * 70)
    print(f"PERFORMANCE ANALYSIS - {len(predictions)} Players")
    print("=" * 70)

    # Summary table
    print(f"\n{'Rank':<6}{'Player':<20}{'Champion':<15}{'Role':<10}{'Score':<8}{'Grade':<6}")
    print("-" * 70)

    for idx, pred_data in enumerate(predictions, 1):
        pred = pred_data['prediction']
        part = pred_data['participant']
        player_name = part.get('riotIdGameName', 'Unknown')

        result_symbol = "✓" if pred['win'] else "✗"

        print(f"{idx:<6}{player_name[:19]:<20}{pred['champion'][:14]:<15}"
              f"{pred['role'][:9]:<10}{pred['performance_score']:<8.1f}{pred['grade']:<6}{result_symbol}")

    # Detailed results
    print("\n\nDETAILED RESULTS:")
    for pred_data in predictions:
        display_prediction(pred_data['prediction'], pred_data['participant'])

    # Summary statistics
    avg_score = sum(p['prediction']['performance_score'] for p in predictions) / len(predictions)
    winning_team_avg = sum(p['prediction']['performance_score'] for p in predictions if p['prediction']['win']) / sum(1 for p in predictions if p['prediction']['win'])
    losing_team_avg = sum(p['prediction']['performance_score'] for p in predictions if not p['prediction']['win']) / sum(1 for p in predictions if not p['prediction']['win'])

    print(f"\n{'=' * 70}")
    print("SUMMARY STATISTICS")
    print(f"{'=' * 70}")
    print(f"Average Score: {avg_score:.2f}")
    print(f"Winning Team Average: {winning_team_avg:.2f}")
    print(f"Losing Team Average: {losing_team_avg:.2f}")
    print(f"Performance Gap: {abs(winning_team_avg - losing_team_avg):.2f}")
    print(f"{'=' * 70}\n")


def main():
    parser = argparse.ArgumentParser(description='Test performance predictions on real match data')
    parser.add_argument('--match-file', required=True, help='Path to match JSON file')
    parser.add_argument('--model-dir', default='models/', help='Directory containing trained models')
    parser.add_argument('--player', default=None, help='Only show predictions for this player name')

    args = parser.parse_args()

    # Check if files exist
    if not Path(args.match_file).exists():
        logger.error(f"Match file not found: {args.match_file}")
        return

    if not Path(args.model_dir).exists():
        logger.error(f"Model directory not found: {args.model_dir}")
        logger.error("Please train models first using: python train_models.py --input training_data.json --output-dir models/")
        return

    # Run predictions
    try:
        test_predictions(args.match_file, args.model_dir, args.player)
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)


if __name__ == '__main__':
    main()
