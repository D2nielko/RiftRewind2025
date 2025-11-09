"""
Performance Predictor - Inference Module for Lambda

This module loads trained performance models and predicts scores for new matches.
Designed to be imported into Lambda functions.

Usage:
    from performance_predictor import PerformancePredictor

    predictor = PerformancePredictor(model_dir='models/')
    score = predictor.predict_performance(participant_data, match_info)
"""

import pickle
import json
import logging
from pathlib import Path
from typing import Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)


class PerformancePredictor:
    """Predicts player performance scores using trained models"""

    def __init__(self, model_dir: str = 'models/', s3_client=None, bucket: str = None):
        """
        Initialize predictor with models

        Args:
            model_dir: Local directory containing model files
            s3_client: Optional boto3 S3 client for loading from S3
            bucket: S3 bucket name if loading from S3
        """
        self.model_dir = Path(model_dir)
        self.s3_client = s3_client
        self.bucket = bucket
        self.models = {}
        self.metadata = {}
        self.feature_columns = []

        self._load_models()

    def _load_from_s3(self, key: str) -> bytes:
        """Load file from S3"""
        if not self.s3_client or not self.bucket:
            raise ValueError("S3 client and bucket required for S3 loading")

        response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
        return response['Body'].read()

    def _load_models(self):
        """Load all trained models"""
        roles = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']

        for role in roles:
            model_file = f"performance_model_{role.lower()}.pkl"

            try:
                if self.s3_client:
                    # Load from S3
                    model_data = self._load_from_s3(f"models/{model_file}")
                    self.models[role] = pickle.loads(model_data)
                    logger.info(f"Loaded {role} model from S3")
                else:
                    # Load from local file
                    model_path = self.model_dir / model_file
                    with open(model_path, 'rb') as f:
                        self.models[role] = pickle.load(f)
                    logger.info(f"Loaded {role} model from {model_path}")

            except Exception as e:
                logger.warning(f"Could not load model for {role}: {e}")

        # Load metadata
        try:
            if self.s3_client:
                metadata_data = self._load_from_s3("models/model_metadata.json")
                self.metadata = json.loads(metadata_data)
                features_data = self._load_from_s3("models/features.json")
                self.feature_columns = json.loads(features_data)['features']
            else:
                with open(self.model_dir / "model_metadata.json", 'r') as f:
                    self.metadata = json.load(f)
                with open(self.model_dir / "features.json", 'r') as f:
                    self.feature_columns = json.load(f)['features']

            logger.info(f"Loaded metadata and {len(self.feature_columns)} features")

        except Exception as e:
            logger.error(f"Could not load metadata: {e}")

    def extract_features(self, participant: Dict, match_info: Dict) -> Dict:
        """
        Extract features from participant data

        Args:
            participant: Participant data from match
            match_info: Match info object

        Returns:
            Dictionary of features
        """
        duration_mins = match_info['gameDuration'] / 60
        challenges = participant.get('challenges', {})

        features = {
            # Core stats
            'kills': participant['kills'],
            'deaths': participant['deaths'],
            'assists': participant['assists'],
            'kda': (participant['kills'] + participant['assists']) / max(participant['deaths'], 1),

            # Farm & Economy
            'cs_per_min': participant['totalMinionsKilled'] / duration_mins,
            'jungle_cs': participant.get('neutralMinionsKilled', 0),
            'gold_per_min': participant['goldEarned'] / duration_mins,

            # Damage
            'damage_per_min': participant['totalDamageDealtToChampions'] / duration_mins,
            'damage_taken_per_min': participant['totalDamageTaken'] / duration_mins,
            'damage_mitigated': participant['damageSelfMitigated'],
            'damage_share': challenges.get('teamDamagePercentage', 0),

            # Vision
            'vision_per_min': participant['visionScore'] / duration_mins,
            'wards_placed': participant['wardsPlaced'],
            'wards_killed': participant['wardsKilled'],
            'control_wards': challenges.get('controlWardsPlaced', 0),

            # Objectives
            'turret_plates': challenges.get('turretPlatesTaken', 0),
            'turrets': participant.get('turretKills', 0),
            'dragons': participant.get('dragonKills', 0),
            'barons': participant.get('baronKills', 0),

            # Early game
            'cs_at_10': challenges.get('laneMinionsFirst10Minutes', 0) or
                       challenges.get('jungleCsBefore10Minutes', 0),
            'cs_advantage': challenges.get('maxCsAdvantageOnLaneOpponent', 0),
            'gold_advantage': 1 if challenges.get('earlyLaningPhaseGoldExpAdvantage', 0) > 0 else 0,

            # Combat
            'kill_participation': challenges.get('killParticipation', 0),
            'solo_kills': challenges.get('soloKills', 0),
            'multikills': participant['doubleKills'] + participant['tripleKills'] * 2 +
                         participant['quadraKills'] * 3 + participant['pentaKills'] * 4,

            # Utility
            'cc_time': participant['timeCCingOthers'],
            'healing': participant['totalHeal'],
            'shielding': participant['totalDamageShieldedOnTeammates'],

            # Time management
            'time_dead_pct': participant['totalTimeSpentDead'] / match_info['gameDuration'],
            'longest_living': participant['longestTimeSpentLiving'],

            # Mechanics
            'skillshots_hit': challenges.get('skillshotsHit', 0),
            'skillshots_dodged': challenges.get('skillshotsDodged', 0),

            # First actions
            'first_blood': int(participant.get('firstBloodKill', False)),
            'first_tower': int(participant.get('firstTowerKill', False)),

            # Game context
            'game_duration': duration_mins
        }

        return features

    def predict_performance(self, participant: Dict, match_info: Dict) -> Optional[Dict]:
        """
        Predict performance score for a player

        Args:
            participant: Participant data from match
            match_info: Match info object

        Returns:
            Dictionary with prediction results:
            {
                'performance_score': float (0-100),
                'role': str,
                'grade': str (S, A, B, C, D, F),
                'percentile': float
            }
        """
        # Get role
        role = participant.get('individualPosition', '')

        if not role or role not in self.models:
            logger.warning(f"No model available for role: {role}")
            return None

        # Extract features
        features = self.extract_features(participant, match_info)

        # Create feature vector in correct order
        feature_vector = []
        for col in self.feature_columns:
            feature_vector.append(features.get(col, 0))

        feature_vector = np.array(feature_vector).reshape(1, -1)

        # Predict
        try:
            model = self.models[role]
            score = float(model.predict(feature_vector)[0])

            # Ensure bounds
            score = np.clip(score, 0, 100)

            # Calculate grade
            grade = self._score_to_grade(score)

            # Calculate percentile (approximate)
            percentile = self._score_to_percentile(score)

            return {
                'performance_score': round(score, 2),
                'role': role,
                'grade': grade,
                'percentile': round(percentile, 1),
                'champion': participant['championName'],
                'win': participant['win']
            }

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return None

    def _score_to_grade(self, score: float) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return 'S'
        elif score >= 80:
            return 'A'
        elif score >= 70:
            return 'B'
        elif score >= 60:
            return 'C'
        elif score >= 50:
            return 'D'
        else:
            return 'F'

    def _score_to_percentile(self, score: float) -> float:
        """
        Approximate percentile based on score
        Assumes normal distribution centered at 50
        """
        # Rough approximation: score 50 = 50th percentile
        # Each 10 points = ~15 percentile points
        percentile = 50 + (score - 50) * 1.5
        return np.clip(percentile, 0, 100)

    def predict_batch(self, participants: list, match_info: Dict) -> Dict[str, Dict]:
        """
        Predict performance for all participants in a match

        Args:
            participants: List of participant data
            match_info: Match info object

        Returns:
            Dictionary mapping puuid to prediction results
        """
        predictions = {}

        for participant in participants:
            puuid = participant['puuid']
            prediction = self.predict_performance(participant, match_info)

            if prediction:
                predictions[puuid] = prediction

        return predictions
