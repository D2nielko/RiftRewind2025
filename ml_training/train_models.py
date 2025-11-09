"""
Train Role-Specific Performance Models

This script trains 5 separate XGBoost models (one per role) to predict
player performance scores (0-100) based on in-game statistics.

Usage:
    python train_models.py --input training_data.json --output-dir models/
"""

import json
import argparse
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import xgboost as xgb
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Feature columns for model training
FEATURE_COLUMNS = [
    # Core stats
    'kills', 'deaths', 'assists', 'kda',

    # Farm & Economy
    'cs_per_min', 'jungle_cs', 'gold_per_min',

    # Damage
    'damage_per_min', 'damage_taken_per_min', 'damage_mitigated',
    'damage_share',

    # Vision
    'vision_per_min', 'wards_placed', 'wards_killed', 'control_wards',

    # Objectives
    'turret_plates', 'turrets', 'dragons', 'barons',

    # Early game
    'cs_at_10', 'cs_advantage', 'gold_advantage',

    # Combat
    'kill_participation', 'solo_kills', 'multikills',

    # Utility
    'cc_time', 'healing', 'shielding',

    # Time management
    'time_dead_pct', 'longest_living',

    # Mechanics
    'skillshots_hit', 'skillshots_dodged',

    # First actions
    'first_blood', 'first_tower',

    # Game context
    'game_duration'
]


class PerformanceScoreCalculator:
    """Calculate ground truth performance scores for training"""

    def __init__(self, samples: List[Dict]):
        self.samples = samples
        self.role_stats = self._calculate_role_statistics()

    def _calculate_role_statistics(self) -> Dict:
        """Calculate mean and std for each stat per role"""
        df = pd.DataFrame(self.samples)

        role_stats = {}
        for role in df['role'].unique():
            role_data = df[df['role'] == role]

            stats = {}
            for col in FEATURE_COLUMNS:
                if col in role_data.columns and col != 'game_duration':
                    stats[col] = {
                        'mean': role_data[col].mean(),
                        'std': role_data[col].std() + 1e-6  # Avoid division by zero
                    }

            role_stats[role] = stats

        return role_stats

    def calculate_performance_score(self, sample: Dict) -> float:
        """
        Calculate performance score (0-100) based on:
        1. Win/loss outcome (30%)
        2. Statistical performance vs role average (50%)
        3. Impact metrics (20%)
        """
        role = sample['role']
        role_stats = self.role_stats[role]

        # Component 1: Win/Loss (30 points)
        win_score = 25 if sample['win'] else 5

        # Component 2: Statistical Performance (50 points)
        stat_scores = []
        key_stats = {
            'kda': 2.0,  # Weight
            'cs_per_min': 1.5,
            'damage_per_min': 2.0,
            'vision_per_min': 1.0,
            'kill_participation': 1.5,
            'damage_share': 1.5,
            'time_dead_pct': -2.0,  # Negative weight (less is better)
        }

        for stat, weight in key_stats.items():
            if stat in role_stats and stat in sample:
                value = sample[stat]
                mean = role_stats[stat]['mean']
                std = role_stats[stat]['std']

                # Z-score normalized
                z_score = (value - mean) / std

                # Convert to 0-10 scale with weight
                normalized = np.clip(5 + z_score, 0, 10) * abs(weight)
                stat_scores.append(normalized)

        stat_score = np.mean(stat_scores) if stat_scores else 25
        stat_score = np.clip(stat_score * (50 / 10), 0, 50)  # Scale to 50 points

        # Component 3: Impact Metrics (20 points)
        impact_score = 0

        # Objectives
        impact_score += min(sample.get('turrets', 0) * 2, 5)
        impact_score += min(sample.get('dragons', 0) * 2, 5)
        impact_score += min(sample.get('barons', 0) * 5, 5)

        # Combat excellence
        if sample.get('solo_kills', 0) >= 2:
            impact_score += 3
        if sample.get('multikills', 0) >= 1:
            impact_score += 2

        impact_score = min(impact_score, 20)

        # Final score
        performance_score = win_score + stat_score + impact_score

        # Ensure within bounds
        return np.clip(performance_score, 0, 100)

    def calculate_all_scores(self) -> List[float]:
        """Calculate scores for all samples"""
        return [self.calculate_performance_score(s) for s in self.samples]


def prepare_training_data(samples: List[Dict]) -> Tuple[pd.DataFrame, Dict]:
    """Prepare features and labels for training"""
    logger.info("Calculating performance scores...")

    calculator = PerformanceScoreCalculator(samples)
    performance_scores = calculator.calculate_all_scores()

    # Create DataFrame
    df = pd.DataFrame(samples)
    df['performance_score'] = performance_scores

    logger.info(f"Performance score statistics:")
    logger.info(f"  Mean: {df['performance_score'].mean():.2f}")
    logger.info(f"  Std: {df['performance_score'].std():.2f}")
    logger.info(f"  Min: {df['performance_score'].min():.2f}")
    logger.info(f"  Max: {df['performance_score'].max():.2f}")

    # Split by role
    role_data = {}
    for role in df['role'].unique():
        role_df = df[df['role'] == role].copy()

        # Ensure all feature columns exist
        for col in FEATURE_COLUMNS:
            if col not in role_df.columns:
                role_df[col] = 0

        X = role_df[FEATURE_COLUMNS]
        y = role_df['performance_score']

        role_data[role] = {
            'X': X,
            'y': y,
            'samples': len(X)
        }

        logger.info(f"{role}: {len(X)} samples, avg score: {y.mean():.2f}")

    return df, role_data


def train_role_model(X: pd.DataFrame, y: pd.Series, role: str) -> Tuple[xgb.XGBRegressor, Dict]:
    """Train XGBoost model for a specific role"""
    logger.info(f"\nTraining model for {role}...")

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Train XGBoost model
    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        objective='reg:squarederror'
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False
    )

    # Evaluate
    y_pred = model.predict(X_test)

    metrics = {
        'rmse': np.sqrt(mean_squared_error(y_test, y_pred)),
        'mae': mean_absolute_error(y_test, y_pred),
        'r2': r2_score(y_test, y_pred),
        'samples_train': len(X_train),
        'samples_test': len(X_test)
    }

    logger.info(f"  RMSE: {metrics['rmse']:.2f}")
    logger.info(f"  MAE: {metrics['mae']:.2f}")
    logger.info(f"  R²: {metrics['r2']:.3f}")

    # Feature importance
    feature_importance = pd.DataFrame({
        'feature': FEATURE_COLUMNS,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)

    logger.info(f"  Top 5 features:")
    for idx, row in feature_importance.head(5).iterrows():
        logger.info(f"    {row['feature']}: {row['importance']:.3f}")

    metrics['feature_importance'] = feature_importance.to_dict('records')

    return model, metrics


def save_models(models: Dict, output_dir: str, metadata: Dict):
    """Save trained models and metadata"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Save each model
    for role, model_data in models.items():
        model_file = output_path / f"performance_model_{role.lower()}.pkl"

        with open(model_file, 'wb') as f:
            pickle.dump(model_data['model'], f)

        logger.info(f"Saved {role} model to {model_file}")

    # Save metadata
    metadata_file = output_path / "model_metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Saved metadata to {metadata_file}")

    # Save feature list
    features_file = output_path / "features.json"
    with open(features_file, 'w') as f:
        json.dump({'features': FEATURE_COLUMNS}, f, indent=2)

    logger.info(f"Saved features to {features_file}")


def main():
    parser = argparse.ArgumentParser(description='Train performance prediction models')
    parser.add_argument('--input', required=True, help='Input training data JSON')
    parser.add_argument('--output-dir', default='models/', help='Output directory for models')

    args = parser.parse_args()

    # Load training data
    logger.info(f"Loading training data from {args.input}...")
    with open(args.input, 'r') as f:
        data = json.load(f)

    samples = data['samples']
    logger.info(f"Loaded {len(samples)} training samples from {data['num_matches']} matches")

    # Prepare data
    df, role_data = prepare_training_data(samples)

    # Train models for each role
    models = {}
    all_metrics = {}

    for role, data in role_data.items():
        if data['samples'] < 100:
            logger.warning(f"Skipping {role}: insufficient samples ({data['samples']})")
            continue

        model, metrics = train_role_model(data['X'], data['y'], role)

        models[role] = {
            'model': model,
            'metrics': metrics
        }

        all_metrics[role] = metrics

    # Create metadata
    metadata = {
        'training_date': pd.Timestamp.now().isoformat(),
        'num_samples': len(samples),
        'num_matches': data['num_matches'],
        'roles': list(models.keys()),
        'feature_columns': FEATURE_COLUMNS,
        'metrics': all_metrics
    }

    # Save models
    save_models(models, args.output_dir, metadata)

    logger.info(f"\n✅ Training complete! Models saved to {args.output_dir}")
    logger.info(f"Trained {len(models)} role-specific models")


if __name__ == '__main__':
    main()
